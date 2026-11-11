"""Synthetic schedule tests: no subprocess, broker, operational DB or clock changes."""

import json
import plistlib
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.market_data.contracts import IST
from scripts import observation_job as job
from scripts import observation_schedule as scheduler
from scripts.bootstrap_local import BootstrapError, private_write

NOW = datetime(2026, 11, 12, 9, 45, tzinfo=IST)


def capture():
    return {
        "capture": {
            "id": "a" * 32,
            "source": "UPSTOX_V3",
            "requested_keys": [job.KEY],
            "policy": job.STANDARD_POLICY.model_dump(),
            "status": "CLOSED",
            "reason": "SESSION_LIMIT",
            "session_count": 1,
            "event_count": 2,
            "payload_bytes": 80,
            "live_enabled": False,
        },
        "sessions": [{"status": "CLOSED", "event_count": 2, "payload_bytes": 80}],
    }


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "scripts").mkdir()
    for name in ("sync_instruments.py", "supervise_capture.py"):
        (tmp_path / "scripts" / name).write_text("# synthetic trusted CLI")
    monkeypatch.setattr(job, "fingerprints", lambda root: {"synthetic": "digest"})
    monkeypatch.setattr(job, "bootstrap_lock", lambda root: nullcontext())
    monkeypatch.setattr(job, "system_uses_ist", lambda: True)
    monkeypatch.setattr(job, "check_storage", Mock())
    monkeypatch.setattr(
        job,
        "health",
        lambda root: {
            "warnings": [],
            "last_verified_at": "verified",
            "due": False,
            "next_due_ist_date": "2026-11-12",
        },
    )
    monkeypatch.setattr(job, "local_database", lambda root: ("docker", "synthetic-db", None))
    monkeypatch.setattr(job, "export_dump", Mock(return_value=b"PGDMPsynthetic"))
    monkeypatch.setattr(
        job,
        "market_session_readiness",
        lambda preflight: {"can_attempt_market_hours_capture": True},
    )
    monkeypatch.setattr(job, "notify", Mock())
    monkeypatch.setattr(
        job,
        "save_reports",
        Mock(
            return_value={
                "phase2_complete": False,
                "unusable_frame_reasons": {"GENERATION_AFTER_RECEIPT": 0, "GENERATION_TOO_OLD": 0},
            }
        ),
    )
    info = {
        "db_bytes": 1024,
        "metadata_imports_today": 0,
        "catalog": {"state": "CURRENT_METADATA"},
        "budget": {"blockers": []},
        "preflight": {},
    }
    remote = Mock(
        side_effect=lambda root, source, *args, **kwargs: (
            deepcopy(info) if source == job.INSPECT_SOURCE else capture()
        )
    )
    monkeypatch.setattr(job, "remote", remote)
    job.arm(tmp_path)
    remote.reset_mock()
    return tmp_path, info, remote


@pytest.mark.parametrize(
    "moment,expected",
    [
        ("2026-11-11T09:45:00+05:30", False),
        ("2026-11-12T09:44:59+05:30", False),
        ("2026-11-12T09:45:00+05:30", True),
        ("2026-11-12T09:49:59+05:30", True),
        ("2026-11-12T09:50:00+05:30", False),
        ("2026-11-14T09:45:00+05:30", False),
        ("2026-11-17T14:45:00+05:30", True),
        ("2026-11-18T09:45:00+05:30", False),
        ("2027-11-12T09:45:00+05:30", False),
    ],
)
def test_finite_checkpoint_window(moment, expected):
    assert bool(job.slot_at(datetime.fromisoformat(moment))) is expected


def test_naive_time_rejected():
    with pytest.raises(job.ObservationJobError, match="AWARE_JOB_TIME"):
        job.slot_at(datetime(2026, 11, 12))


def test_capture_is_once_only_fixed_policy_and_reports_not_certified(workspace):
    root, _, remote = workspace
    result = job.run(root, now=NOW)
    assert result["state"] == "BOUNDED_CAPTURE_CLOSED"
    assert result["recording_started"] and not result["phase2_complete"]
    calls = [c for c in remote.call_args_list if c.args[1] != job.INSPECT_SOURCE]
    assert len(calls) == 1
    assert calls[0].args[2] == [
        "--instrument-key",
        job.KEY,
        "--total-seconds",
        "120",
        "--session-seconds",
        "120",
        "--max-sessions",
        "1",
        "--max-payload-bytes",
        "262144",
        "--max-events",
        "300",
    ]
    remote.reset_mock()
    assert job.run(root, now=NOW)["state"] == "SKIPPED_ALREADY_ATTEMPTED"
    remote.assert_not_called()


def test_non_checkpoint_does_not_access_runtime(workspace):
    root, _, remote = workspace
    assert job.run(root, now=NOW.replace(hour=10))["state"] == "SKIPPED_NOT_CHECKPOINT"
    remote.assert_not_called()


def test_budget_blocks_all_capture_and_metadata(workspace):
    root, info, remote = workspace
    info["budget"]["blockers"] = ["DAILY_RUN_BUDGET_EXHAUSTED"]
    assert job.run(root, now=NOW)["reason"] == "PILOT_BUDGET_BLOCKED"
    assert remote.call_count == 1


def test_preflight_failure_has_no_capture(workspace, monkeypatch):
    root, _, remote = workspace
    monkeypatch.setattr(
        job, "market_session_readiness", lambda p: {"can_attempt_market_hours_capture": False}
    )
    assert job.run(root, now=NOW)["reason"] == "SESSION_PREFLIGHT_BLOCKED"
    assert all(c.args[1] == job.INSPECT_SOURCE for c in remote.call_args_list)


def test_clock_rollback_blocks(workspace):
    root, _, remote = workspace
    job.run(root, now=NOW)
    remote.reset_mock()
    assert job.run(root, now=NOW.replace(hour=8))["reason"] == "JOB_CLOCK_ROLLBACK"
    remote.assert_not_called()


def test_arming_tamper_and_timezone_fail_closed(workspace, monkeypatch):
    root, _, remote = workspace
    monkeypatch.setattr(job, "fingerprints", lambda root: {"synthetic": "changed"})
    assert job.run(root, now=NOW)["reason"] == "ARMING_OR_SOURCE_REVIEW_REQUIRED"
    monkeypatch.setattr(job, "system_uses_ist", lambda: False)
    assert job.run(root, now=NOW)["reason"] == "SYSTEM_TIMEZONE_CHANGED"
    remote.assert_not_called()


def test_uncertain_remote_capture_pauses_future_checkpoints(workspace):
    root, info, remote = workspace

    def execute(root, source, *args, **kwargs):
        if source == job.INSPECT_SOURCE:
            return info
        raise TimeoutError("sensitive upstream material")

    remote.side_effect = execute
    result = job.run(root, now=NOW)
    assert result["reason"] == "OBSERVER_UNAVAILABLE" and result["recording_started"] is None
    assert result["remote_state_verified"] is False
    assert "sensitive" not in json.dumps(result)
    remote.reset_mock()
    assert (
        job.run(root, now=NOW.replace(hour=12, minute=15))["reason"]
        == "PREVIOUS_CAPTURE_REQUIRES_REVIEW"
    )
    remote.assert_not_called()


def test_stale_metadata_import_at_most_once_per_date(workspace):
    root, info, remote = workspace
    info["catalog"]["state"] = "STALE_METADATA"
    job.run(root, now=NOW)
    remote.reset_mock()
    assert (
        job.run(root, now=NOW.replace(hour=12, minute=15))["reason"] == "METADATA_REVIEW_REQUIRED"
    )
    assert remote.call_count == 1


def test_end_window_reads_once_and_only_requests_review(workspace):
    root, _, remote = workspace
    result = job.run(root, now=NOW.replace(day=18))
    assert result["state"] == "WINDOW_ENDED_REVIEW_REQUIRED"
    assert result["phase2_complete"] is False and result["recording_started"] is False
    job.run(root, now=NOW.replace(year=2027, day=18))
    assert job.save_reports.call_count == 2  # Arming baseline and one end-of-window report.
    job.notify.assert_called_once()
    remote.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "SYNTHETIC"),
        ("live_enabled", True),
        ("status", "ABANDONED"),
        ("session_count", 2),
        ("event_count", 301),
        ("payload_bytes", 262145),
        ("requested_keys", ["NSE_FO|other"]),
        ("reason", "PROTOCOL_ERROR"),
    ],
)
def test_closed_capture_validation_rejects_unexpected_results(field, value):
    result = capture()
    result["capture"][field] = value
    with pytest.raises(job.ObservationJobError, match="CAPTURE_REVIEW_REQUIRED"):
        job.validate_capture(result)


def test_private_state_symlink_and_permissions_rejected(workspace):
    root, _, _ = workspace
    path = root / ".local/observation-job/armed.json"
    path.chmod(0o644)
    with pytest.raises(job.ObservationJobError, match="PRIVATE_JOB_FILE"):
        job.read_json(path)
    path.unlink()
    path.symlink_to(root / "unrelated")
    with pytest.raises(BootstrapError, match="SYMLINKED_SECRET_FILE"):
        job.read_json(path)


def test_failed_notification_is_reported_and_not_marked_delivered(workspace, monkeypatch):
    root, _, _ = workspace
    monkeypatch.setattr(job, "system_uses_ist", lambda: False)
    monkeypatch.setattr(job, "notify", Mock(side_effect=RuntimeError))
    result = job.run(root, now=NOW)
    assert result["notification_submitted"] is False
    assert "last_notification" not in job.read_json(root / ".local/observation-job/ledger.json")


def test_storage_limits_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(job.shutil, "disk_usage", lambda root: SimpleNamespace(free=1))
    with pytest.raises(job.ObservationJobError, match="HOST_DISK_BUDGET"):
        job.check_storage(tmp_path, {"baseline_db_bytes": 1}, {"db_bytes": 1})
    monkeypatch.setattr(job.shutil, "disk_usage", lambda root: SimpleNamespace(free=3 * 1024**3))
    with pytest.raises(job.ObservationJobError, match="DATABASE_DISK_BUDGET"):
        job.check_storage(tmp_path, {"baseline_db_bytes": 1}, {"db_bytes": 64 * 1024**2})
    monkeypatch.setattr(job, "local_database", lambda root: ("docker", "synthetic-db", None))
    monkeypatch.setattr(
        job.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout="Filesystem Blocks Used Available\nx 1 1 1"
        ),
    )
    with pytest.raises(job.ObservationJobError, match="DOCKER_DISK_BUDGET"):
        job.check_storage(tmp_path, {"baseline_db_bytes": 1}, {"db_bytes": 1})


def test_schedule_has_only_finite_checkpoints_and_no_secrets(tmp_path):
    result = plistlib.loads(plistlib.dumps(scheduler.schedule(tmp_path)))
    assert len(result["StartCalendarInterval"]) == 13
    assert {c["Day"] for c in result["StartCalendarInterval"]} == {12, 13, 16, 17, 18}
    assert not result["RunAtLoad"] and not result["KeepAlive"]
    assert result["StandardOutPath"] == result["StandardErrorPath"] == "/dev/null"
    assert set(result["EnvironmentVariables"]) == {"PATH"}


def test_install_conflict_never_overwrites_existing_job(workspace, monkeypatch):
    root, _, _ = workspace
    home = root / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").write_text("synthetic")
    target = agents / (scheduler.LABEL + ".plist")
    private_write(target, "unrelated job")
    monkeypatch.setattr(scheduler, "system_uses_ist", lambda: True)
    monkeypatch.setattr(scheduler, "launchctl", lambda *args: 1)
    monkeypatch.setattr(scheduler.sys, "platform", "darwin")
    with pytest.raises(job.ObservationJobError, match="JOB_LABEL_CONFLICT"):
        scheduler.install(root, home, now=NOW)
    assert target.read_text() == "unrelated job"


@pytest.mark.parametrize("problem", ["warnings", "missing_receipt", "overdue"])
def test_backup_gates_prevent_capture(workspace, monkeypatch, problem):
    root, _, remote = workspace
    backup = {
        "warnings": [],
        "last_verified_at": "verified",
        "due": False,
        "next_due_ist_date": "2026-11-12",
    }
    if problem == "warnings":
        backup["warnings"] = ["LAST_JOB_DID_NOT_VERIFY_BACKUP"]
    elif problem == "missing_receipt":
        backup["last_verified_at"] = None
    else:
        backup.update(due=True, next_due_ist_date="2026-11-11")
    monkeypatch.setattr(job, "health", lambda root: backup)
    assert job.run(root, now=NOW)["reason"] == "BACKUP_REVIEW_REQUIRED"
    remote.assert_not_called()


def test_fresh_inspection_occurs_after_dump_and_before_capture(workspace, monkeypatch):
    root, info, remote = workspace

    def dump(*args):
        info["budget"]["blockers"] = ["ACTIVE_OR_UNRESOLVED_RECORDING_PRESENT"]
        return b"PGDMPsynthetic"

    monkeypatch.setattr(job, "export_dump", dump)
    assert job.run(root, now=NOW)["reason"] == "PILOT_BUDGET_BLOCKED"
    assert remote.call_count == 2
    assert all(c.args[1] == job.INSPECT_SOURCE for c in remote.call_args_list)


def test_oversize_backup_blocks_capture(workspace, monkeypatch):
    root, _, remote = workspace
    monkeypatch.setattr(job, "export_dump", lambda *a: b"x" * (24 * 1024**2))
    assert job.run(root, now=NOW)["reason"] == "BACKUP_SIZE_BUDGET"
    assert remote.call_count == 1


def test_claim_is_durable_before_remote_capture(workspace):
    root, info, remote = workspace

    def execute(root, source, *args, **kwargs):
        if source == job.INSPECT_SOURCE:
            return info
        ledger = job.read_json(root / ".local/observation-job/ledger.json")
        assert ledger["slots"][NOW.isoformat()] == "ATTEMPTED"
        return capture()

    remote.side_effect = execute
    assert job.run(root, now=NOW)["state"] == "BOUNDED_CAPTURE_CLOSED"


def test_invalid_capture_pauses_job_and_requires_review(workspace):
    root, info, remote = workspace
    remote.side_effect = lambda root, source, *a, **kw: info if source == job.INSPECT_SOURCE else {}
    result = job.run(root, now=NOW)
    assert result["reason"] == "CAPTURE_REVIEW_REQUIRED"
    assert job.read_json(root / ".local/observation-job/ledger.json")["paused"]


def test_install_and_disable_only_exact_inactive_agent(workspace, monkeypatch):
    root, _, _ = workspace
    home = root / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python").write_text("synthetic")
    monkeypatch.setattr(scheduler, "system_uses_ist", lambda: True)
    monkeypatch.setattr(scheduler, "arm", Mock())
    monkeypatch.setattr(scheduler.sys, "platform", "darwin")
    calls = []

    def launchctl(*args):
        calls.append(args)
        return 1 if args[0] == "print" else 0

    monkeypatch.setattr(scheduler, "launchctl", launchctl)
    assert scheduler.install(root, home, now=NOW)["state"] == "INSTALLED"
    target = agents / (scheduler.LABEL + ".plist")
    assert target.stat().st_mode & 0o077 == 0
    assert any(c[0] == "bootstrap" for c in calls)
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="state = running\n"),
    )
    with pytest.raises(job.ObservationJobError, match="JOB_ACTIVE_WAIT_FOR_FINISH"):
        scheduler.disable(root, home)
    assert target.exists()
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="state = not running\n"),
    )
    assert scheduler.disable(root, home)["state"] == "DISABLED"
    assert not target.exists()


def test_notification_subprocess_failure_is_detected(monkeypatch):
    monkeypatch.setattr(job.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(job.ObservationJobError, match="LOCAL_NOTIFICATION_UNAVAILABLE"):
        job.notify()


@pytest.mark.parametrize("reason", ["GENERATION_AFTER_RECEIPT", "GENERATION_TOO_OLD"])
def test_new_frame_clock_anomaly_pauses_collection(workspace, reason):
    root, _, remote = workspace
    report = {"unusable_frame_reasons": {"GENERATION_AFTER_RECEIPT": 0, "GENERATION_TOO_OLD": 0}}
    report["unusable_frame_reasons"][reason] = 1
    job.save_reports.return_value = report
    result = job.run(root, now=NOW)
    assert result["reason"] == "NEW_FRAME_CLOCK_ANOMALY_REQUIRES_REVIEW"
    assert result["recording_started"] is True
    assert job.read_json(root / ".local/observation-job/ledger.json")["paused"]
    remote.reset_mock()
    assert job.run(root, now=NOW.replace(hour=12, minute=15))["reason"] == (
        "PREVIOUS_CAPTURE_REQUIRES_REVIEW"
    )
    remote.assert_not_called()
