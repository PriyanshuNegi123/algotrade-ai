"""Finite operator-authorized read-only observation pilot; never starts Docker or trading."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from backend.app.market_data.calendar import load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.coverage import CoverageRequest
from backend.app.market_data.initial_report import render_initial_observation
from backend.app.market_data.observation_budget import STANDARD_POLICY, BudgetRequest
from backend.app.market_data.session_readiness import market_session_readiness
from scripts.backup_job import health, system_uses_ist
from scripts.backup_postgres import export_dump, local_database
from scripts.bootstrap_local import ROOT, bootstrap_lock, private_read, private_write
from scripts.capture_local import RUN_SOURCE, local_container
from scripts.initial_observation import local_report

PLAN = BudgetRequest(from_date=date(2026, 11, 11), to_date=date(2026, 11, 17))
KEY = "NSE_FO|45406"
TIMES = (time(9, 45), time(12, 15), time(14, 45))
FINGERPRINT_FILES = (
    "scripts/observation_job.py",
    "scripts/observation_schedule.py",
    "scripts/capture_local.py",
    "scripts/supervise_capture.py",
    "scripts/sync_instruments.py",
    "scripts/initial_observation.py",
    "backend/app/market_data/observation_budget.py",
    "backend/app/market_data/calendar_data/nse_fo_2026.json",
)
INSPECT_SOURCE = """
import json
from datetime import UTC,datetime,time,timedelta
from sqlalchemy import select,func,text
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.instruments.models import InstrumentSnapshot
from backend.app.instruments.service import catalog_status
from backend.app.market_data.contracts import IST
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.observation_budget import BudgetRequest,pilot_budget,STANDARD_POLICY
from backend.app.market_data.preflight import capture_preflight
s=Settings();e=build_engine(s)
try:
 assert s.trading_mode=='OBSERVATION' and s.live_enabled is False
 now=datetime.now(UTC);day=now.astimezone(IST).date()
 start=datetime.combine(day,time.min,IST).astimezone(UTC)
 with e.begin() as c:
  c.execute(text('SET TRANSACTION READ ONLY'))
  c.execute(text("SET LOCAL statement_timeout='2000ms'"))
  size=c.scalar(text('SELECT pg_database_size(current_database())'))
  imported=c.scalar(select(func.count()).select_from(InstrumentSnapshot).where(InstrumentSnapshot.imported_at>=start,InstrumentSnapshot.imported_at<start+timedelta(days=1)))
 print(json.dumps({'db_bytes':size,'metadata_imports_today':imported,'catalog':catalog_status(e),'budget':pilot_budget(e,BudgetRequest(from_date='2026-11-11',to_date='2026-11-17')),'preflight':capture_preflight(e,s,FeedRequest(instrument_keys=('NSE_FO|45406',)),STANDARD_POLICY)},default=str))
finally:e.dispose()
"""


class ObservationJobError(Exception):
    pass


def directory(root: Path) -> Path:
    current = root
    for part in (".local", "observation-job"):
        current /= part
        if current.is_symlink():
            raise ObservationJobError("UNSAFE_JOB_DIRECTORY")
        current.mkdir(mode=0o700, exist_ok=True)
        if (
            not current.is_dir()
            or current.stat().st_uid != os.getuid()
            or current.stat().st_mode & 0o022
        ):
            raise ObservationJobError("UNSAFE_JOB_DIRECTORY")
    os.chmod(current, 0o700)
    return current


def read_json(path: Path) -> dict:
    raw = private_read(path)
    if raw is None:
        return {}
    if path.stat().st_mode & 0o077:
        raise ObservationJobError("PRIVATE_JOB_FILE_REQUIRED")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ObservationJobError("INVALID_JOB_STATE")
    return data


@contextmanager
def job_lock(path: Path):
    fd = os.open(path / "job.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ObservationJobError("UNSAFE_JOB_LOCK")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def fingerprints(root: Path) -> dict:
    return {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FINGERPRINT_FILES
    }


def remote(root: Path, source: str, arguments=(), timeout=30) -> dict:
    exe, container = local_container(root)
    response = subprocess.run(
        [exe, "exec", "-i", "--workdir", "/app", container, "python", "-c", RUN_SOURCE, *arguments],
        input=source,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if response.returncode not in (0, 2) or len(response.stdout) > 1024 * 1024:
        raise ObservationJobError("OBSERVER_RUNTIME_UNAVAILABLE")
    result = json.loads(response.stdout)
    if not isinstance(result, dict):
        raise ObservationJobError("OBSERVER_RESPONSE_INVALID")
    return result


def arm(root: Path) -> dict:
    path = directory(root)
    with job_lock(path), bootstrap_lock(root):
        info = remote(root, INSPECT_SOURCE)
        old = read_json(path / "armed.json")
        config = {
            "version": 1,
            "from_date": str(PLAN.from_date),
            "to_date": str(PLAN.to_date),
            "instrument_key": KEY,
            "policy": STANDARD_POLICY.model_dump(),
            "baseline_db_bytes": min(
                info["db_bytes"], old.get("baseline_db_bytes", info["db_bytes"])
            ),
            "code_sha256": fingerprints(root),
            "armed_at": datetime.now(UTC).isoformat(),
        }
        check_storage(root, config, info)
        report = save_reports(root, path)
        config["baseline_frame_reasons"] = report["unusable_frame_reasons"]
        private_write(path / "armed.json", json.dumps(config) + "\n")
        return {"state": "ARMED_FINITE_PILOT", "recording_started": False, "live_enabled": False}


def slot_at(now: datetime) -> str | None:
    if now.tzinfo is None:
        raise ObservationJobError("AWARE_JOB_TIME_REQUIRED")
    local = now.astimezone(IST)
    if not date(2026, 11, 12) <= local.date() <= PLAN.to_date:
        return None
    if load_calendar().day(local.date())["state"] not in {"REGULAR_BASELINE", "SPECIAL_SESSION"}:
        return None
    for checkpoint in TIMES:
        start = datetime.combine(local.date(), checkpoint, IST)
        if start <= local < start + timedelta(minutes=5):
            return start.isoformat()
    return None


def check_storage(root: Path, config: dict, info: dict) -> None:
    if shutil.disk_usage(root).free < 2 * 1024**3:
        raise ObservationJobError("HOST_DISK_BUDGET")
    if info["db_bytes"] >= min(64 * 1024**2, config["baseline_db_bytes"] + 32 * 1024**2):
        raise ObservationJobError("DATABASE_DISK_BUDGET")
    exe, db, _ = local_database(root)
    result = subprocess.run(
        [exe, "exec", db, "df", "-Pk", "/var/lib/postgresql/data"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode or int(result.stdout.splitlines()[-1].split()[3]) * 1024 < 2 * 1024**3:
        raise ObservationJobError("DOCKER_DISK_BUDGET")


def notify() -> None:
    # Fixed local-user message only; never includes untrusted errors, IDs or secrets.
    response = subprocess.run(
        [
            "/usr/bin/osascript",
            "-e",
            'display notification "Check private observation status. Trading remains disabled." '
            'with title "AlgoTrade AI needs review"',
        ],
        capture_output=True,
        timeout=10,
    )
    if response.returncode:
        raise ObservationJobError("LOCAL_NOTIFICATION_UNAVAILABLE")


def validate_capture(captured: dict) -> dict:
    parent = captured.get("capture")
    children = captured.get("sessions", [])
    if (
        not parent
        or parent.get("source") != "UPSTOX_V3"
        or parent.get("requested_keys") != [KEY]
        or parent.get("policy") != STANDARD_POLICY.model_dump()
        or parent.get("live_enabled") is not False
        or parent.get("status") != "CLOSED"
        or parent.get("reason") != "SESSION_LIMIT"
        or parent.get("session_count") != 1
        or len(children) != 1
        or children[0].get("status") != "CLOSED"
        or not 0 <= parent["event_count"] <= STANDARD_POLICY.max_events
        or not 0 <= parent["payload_bytes"] <= STANDARD_POLICY.max_payload_bytes
        or children[0]["event_count"] != parent["event_count"]
        or children[0]["payload_bytes"] != parent["payload_bytes"]
    ):
        raise ObservationJobError("CAPTURE_REVIEW_REQUIRED")
    return parent


def save_reports(root: Path, path: Path) -> dict:
    report = local_report(
        CoverageRequest(
            from_date=PLAN.from_date, to_date=PLAN.to_date, instrument_keys=("NSE_FO|35050", KEY)
        )
    )
    private_write(path / "report.json", json.dumps(report, default=str) + "\n")
    private_write(path / "INITIAL_OBSERVATION.md", render_initial_observation(report) + "\n")
    return report


def run(root: Path, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    path = directory(root)
    result = {
        "checked_at": now.isoformat(),
        "state": "SKIPPED_NOT_CHECKPOINT",
        "recording_started": False,
        "phase2_complete": False,
        "live_enabled": False,
    }
    capture_invoked = False
    with job_lock(path):
        state = read_json(path / "ledger.json") or {
            "slots": {},
            "metadata_attempts": {},
            "dump_checks": {},
        }
        try:
            if any(
                not isinstance(state.get(key), dict)
                for key in ("slots", "metadata_attempts", "dump_checks")
            ):
                raise ObservationJobError("INVALID_JOB_STATE")
            if state.get("paused"):
                raise ObservationJobError("PREVIOUS_CAPTURE_REQUIRES_REVIEW")
            if not system_uses_ist():
                raise ObservationJobError("SYSTEM_TIMEZONE_CHANGED")
            config = read_json(path / "armed.json")
            if (
                config.get("version") != 1
                or config.get("code_sha256") != fingerprints(root)
                or config.get("instrument_key") != KEY
                or config.get("policy") != STANDARD_POLICY.model_dump()
                or config.get("from_date") != str(PLAN.from_date)
                or config.get("to_date") != str(PLAN.to_date)
            ):
                raise ObservationJobError("ARMING_OR_SOURCE_REVIEW_REQUIRED")
            if state.get("last_started_at") and datetime.fromisoformat(
                state["last_started_at"]
            ) > now + timedelta(seconds=2):
                raise ObservationJobError("JOB_CLOCK_ROLLBACK")
            if now.astimezone(IST).date() > PLAN.to_date:
                if not state.get("end_report_saved"):
                    save_reports(root, path)
                    state["end_report_saved"] = True
                result["state"] = "WINDOW_ENDED_REVIEW_REQUIRED"
            else:
                slot = slot_at(now)
                if slot is None or slot in state["slots"]:
                    if slot in state["slots"]:
                        result["state"] = "SKIPPED_ALREADY_ATTEMPTED"
                    return result
                # Persist once before any I/O; crashes never replay this checkpoint.
                state["slots"][slot] = "ATTEMPTED"
                state["last_started_at"] = now.isoformat()
                private_write(path / "ledger.json", json.dumps(state) + "\n")
                backup = health(root)
                if (
                    backup["warnings"]
                    or not backup["last_verified_at"]
                    or (
                        backup["due"]
                        and backup["next_due_ist_date"] < str(now.astimezone(IST).date())
                    )
                ):
                    raise ObservationJobError("BACKUP_REVIEW_REQUIRED")
                with bootstrap_lock(root):
                    info = remote(root, INSPECT_SOURCE)
                    if info["budget"]["blockers"]:
                        raise ObservationJobError("PILOT_BUDGET_BLOCKED")
                    check_storage(root, config, info)
                    today = str(now.astimezone(IST).date())
                    if info["catalog"]["state"] != "CURRENT_METADATA":
                        if today in state["metadata_attempts"] or info["metadata_imports_today"]:
                            raise ObservationJobError("METADATA_REVIEW_REQUIRED")
                        state["metadata_attempts"][today] = True
                        private_write(path / "ledger.json", json.dumps(state) + "\n")
                        remote(root, (root / "scripts/sync_instruments.py").read_text(), timeout=90)
                        info = remote(root, INSPECT_SOURCE)
                        check_storage(root, config, info)
                    if today not in state["dump_checks"]:
                        exe, db, _ = local_database(root)
                        size = len(export_dump(exe, db))  # Bounded RAM only; no local dump file.
                        state["dump_checks"][today] = size
                        private_write(path / "ledger.json", json.dumps(state) + "\n")
                    if state["dump_checks"][today] >= 24 * 1024**2:
                        raise ObservationJobError("BACKUP_SIZE_BUDGET")
                    info = remote(root, INSPECT_SOURCE)
                    if info["budget"]["blockers"]:
                        raise ObservationJobError("PILOT_BUDGET_BLOCKED")
                    check_storage(root, config, info)
                    ready = market_session_readiness(info["preflight"])
                    if not ready["can_attempt_market_hours_capture"]:
                        raise ObservationJobError("SESSION_PREFLIGHT_BLOCKED")
                    arguments = ["--instrument-key", KEY]
                    for name, value in STANDARD_POLICY.model_dump().items():
                        arguments.extend(["--" + name.replace("_", "-"), str(value)])
                    capture_invoked = True
                    result["recording_started"] = None
                    captured = remote(
                        root,
                        (root / "scripts/supervise_capture.py").read_text(),
                        arguments,
                        timeout=STANDARD_POLICY.total_seconds + 120,
                    )
                    parent = validate_capture(captured)
                    capture_invoked = False
                    result.update(
                        state="BOUNDED_CAPTURE_CLOSED",
                        capture_id=parent["id"],
                        events=parent["event_count"],
                        payload_bytes=parent["payload_bytes"],
                        recording_started=True,
                    )
                report = save_reports(root, path)
                if any(
                    report["unusable_frame_reasons"][reason]
                    > config["baseline_frame_reasons"][reason]
                    for reason in ("GENERATION_AFTER_RECEIPT", "GENERATION_TOO_OLD")
                ):
                    state["paused"] = True
                    raise ObservationJobError("NEW_FRAME_CLOCK_ANOMALY_REQUIRES_REVIEW")
                state["slots"][slot] = result["state"]
        except Exception as error:
            if result["recording_started"] is True:
                state["paused"] = True
            if capture_invoked:
                state["paused"] = True
                result["recording_started"] = None
                result["remote_state_verified"] = False
            result["state"] = "NEEDS_ATTENTION"
            result["reason"] = (
                str(error) if isinstance(error, ObservationJobError) else "OBSERVER_UNAVAILABLE"
            )
        finally:
            if result["state"] in {"NEEDS_ATTENTION", "WINDOW_ENDED_REVIEW_REQUIRED"}:
                marker = result.get("reason", result["state"])
                if state.get("last_notification") != marker:
                    try:
                        notify()
                        state["last_notification"] = marker
                        result["notification_submitted"] = True
                    except Exception:
                        result["notification_submitted"] = False
            private_write(path / "ledger.json", json.dumps(state) + "\n")
            private_write(path / "status.json", json.dumps(result) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "status"))
    args = parser.parse_args()
    result = run(ROOT) if args.action == "run" else read_json(directory(ROOT) / "status.json")
    print(json.dumps(result), flush=True)
    return 2 if result.get("state") == "NEEDS_ATTENTION" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("OBSERVATION_JOB_UNAVAILABLE: sensitive details withheld") from None
