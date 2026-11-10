"""Three-IST-calendar-day backup policy, safe job results and read-only local health."""

import argparse
import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import BackupError
from scripts.backup_postgres import backup_directory, recovery_key
from scripts.bootstrap_local import ROOT, private_write
from scripts.google_drive import secure_json

IST = ZoneInfo("Asia/Kolkata")
INTERVAL_DAYS = 3


def system_uses_ist() -> bool:
    return datetime.now().astimezone().utcoffset() == timedelta(hours=5, minutes=30)


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise BackupError("BACKUP_STATUS_TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise BackupError("BACKUP_STATUS_TIMESTAMP_INVALID")
    return parsed.astimezone(UTC)


def health(root: Path, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise BackupError("BACKUP_STATUS_TIMESTAMP_INVALID")
    path = root / ".local/backups"
    if (root / ".local").is_symlink() or path.is_symlink():
        raise BackupError("BACKUP_UNSAFE_DIRECTORY")
    key_ready = False
    key_digest = None
    try:
        key_digest = hashlib.sha256(recovery_key(path)).hexdigest()
        key_ready = True
    except Exception:
        pass
    receipt = secure_json(path / "latest.json")
    result = {
        "state": "DUE",
        "due": True,
        "interval_days": INTERVAL_DAYS,
        "timezone": "Asia/Kolkata",
        "checked_at": now.isoformat(),
        "last_verified_at": None,
        "last_backup_at": None,
        "next_due_ist_date": None,
        "recovery_key_ready": key_ready,
        "remote_access_checked": False,
        "offline_recovery_copy": "NOT_CONFIRMED",
        "cloud_recovery_kit": "NOT_CONFIRMED",
        "warnings": ["OFF_DEVICE_RECOVERY_COPY_NOT_CONFIRMED"],
    }
    try:
        kit = secure_json(path / "recovery-kit.json")
        if kit:
            restored = kit.get("restore", {})
            if (
                kit.get("state") == "RECOVERY_VERIFIED"
                and key_digest is not None
                and kit.get("protected_key_sha256") == key_digest
                and kit.get("schema_revision") == SCHEMA_REVISION
                and kit.get("original_key_required_for_verification") is False
                and restored.get("restore_verified") is True
                and restored.get("superuser") is False
                and restored.get("admin_sessions") == 0
                and restored.get("network") == "none"
                and timestamp(kit.get("verified_at")) <= now + timedelta(minutes=5)
            ):
                result["cloud_recovery_kit"] = "PASSPHRASE_PROTECTED_RESTORE_VERIFIED"
                result["warnings"] = []
    except Exception:
        pass  # An invalid optional kit receipt must not stop scheduled backups.
    if receipt:
        restore = receipt.get("restore")
        if (
            receipt.get("state") != "RESTORE_VERIFIED"
            or not isinstance(restore, dict)
            or restore.get("restore_verified") is not True
            or restore.get("superuser") is not False
            or restore.get("admin_sessions") != 0
            or restore.get("network") != "none"
        ):
            raise BackupError("BACKUP_VERIFIED_RECEIPT_INVALID")
        verified = timestamp(receipt.get("verified_at"))
        manifest = receipt.get("manifest")
        if not isinstance(manifest, dict):
            raise BackupError("BACKUP_VERIFIED_RECEIPT_INVALID")
        created = timestamp(manifest.get("created_at"))
        if verified > now + timedelta(minutes=5) or created > verified + timedelta(minutes=5):
            raise BackupError("BACKUP_STATUS_FUTURE_RECEIPT")
        due_date = created.astimezone(IST).date() + timedelta(days=INTERVAL_DAYS)
        due = now.astimezone(IST).date() >= due_date
        result.update(
            state="DUE" if due else "LOCAL_CHECKS_PASSED",
            due=due,
            last_verified_at=verified.isoformat(),
            last_backup_at=created.isoformat(),
            next_due_ist_date=due_date.isoformat(),
        )
    if not key_ready:
        result.update(state="RECOVERY_KEY_REQUIRED")
    job = secure_json(path / "job-status.json")
    allowed = {"RUNNING", "VERIFIED", "FAILED", "TIMED_OUT", "CLEANUP_PENDING"}
    result["last_job_state"] = job.get("state") if job and job.get("state") in allowed else None
    if job and result["last_job_state"] in {"FAILED", "TIMED_OUT", "CLEANUP_PENDING"}:
        last = timestamp(job.get("started_at"))
        if not receipt or last > timestamp(result["last_backup_at"]):
            result["warnings"].append("LAST_JOB_DID_NOT_VERIFY_BACKUP")
    check = secure_json(path / "job-check.json")
    if check and check.get("state") == "BLOCKED_TIMEZONE_CHANGED":
        result["warnings"].append("SYSTEM_TIMEZONE_CHANGED")
    return result


@contextmanager
def job_lock(path: Path):
    descriptor = os.open(path / "job.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise BackupError("BACKUP_UNSAFE_JOB_LOCK")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError("BACKUP_JOB_ALREADY_RUNNING") from None
        yield
    finally:
        os.close(descriptor)


def run_job(root: Path, *, force: bool = False) -> dict:
    path = backup_directory(root)
    with job_lock(path):
        before = health(root)
        if not before["recovery_key_ready"]:
            raise BackupError("BACKUP_EXISTING_RECOVERY_KEY_REQUIRED")
        if not before["due"] and not force:
            check = {
                "state": "SKIPPED_NOT_DUE",
                "checked_at": datetime.now(UTC).isoformat(),
                "next_due_ist_date": before["next_due_ist_date"],
            }
            private_write(path / "job-check.json", json.dumps(check) + "\n")
            return check
        job = {"state": "RUNNING", "started_at": datetime.now(UTC).isoformat()}
        private_write(path / "job-status.json", json.dumps(job) + "\n")
        try:
            process = subprocess.Popen(
                [str(root / ".venv/bin/python"), "-m", "scripts.backup_postgres", "backup"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception:
            job.update(state="FAILED", finished_at=datetime.now(UTC).isoformat())
            private_write(path / "job-status.json", json.dumps(job) + "\n")
            return job
        try:
            output, _ = process.communicate(timeout=900)
            if process.returncode != 0 or len(output) > 65_536:
                job["state"] = "FAILED"
            else:
                report = json.loads(output)
                after = health(root)
                if (
                    not isinstance(report, dict)
                    or report.get("state") != "RESTORE_VERIFIED"
                    or not after["last_verified_at"]
                    or timestamp(after["last_verified_at"]) < timestamp(job["started_at"])
                    or not after["last_backup_at"]
                    or timestamp(after["last_backup_at"]) < timestamp(job["started_at"])
                ):
                    raise BackupError("BACKUP_JOB_RECEIPT_NOT_UPDATED")
                job["state"] = "VERIFIED"
        except subprocess.TimeoutExpired:
            process.send_signal(signal.SIGINT)  # Only our child; allow restore cleanup to unwind.
            try:
                process.communicate(timeout=60)
                job["state"] = "TIMED_OUT"
            except subprocess.TimeoutExpired:
                job["state"] = (
                    "CLEANUP_PENDING"  # Do not kill a child still cleaning its resources.
                )
        except Exception:
            job["state"] = "FAILED"
        job["finished_at"] = datetime.now(UTC).isoformat()
        private_write(path / "job-status.json", json.dumps(job) + "\n")
        return job


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "run"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.force and args.action != "run":
        raise BackupError("BACKUP_JOB_FORCE_REQUIRES_RUN")
    if (
        args.action == "run"
        and os.environ.get("ALGOTRADE_BACKUP_SCHEDULED") == "1"
        and not system_uses_ist()
    ):
        result = {"state": "BLOCKED_TIMEZONE_CHANGED", "checked_at": datetime.now(UTC).isoformat()}
        private_write(backup_directory(ROOT) / "job-check.json", json.dumps(result) + "\n")
        print(json.dumps(result), flush=True)
        return 2
    result = health(ROOT) if args.action == "status" else run_job(ROOT, force=args.force)
    print(json.dumps(result), flush=True)
    return 0 if result["state"] in {"LOCAL_CHECKS_PASSED", "VERIFIED", "SKIPPED_NOT_DUE"} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(
            "BACKUP_JOB_UNAVAILABLE: inspect local configuration; details withheld"
        ) from None
