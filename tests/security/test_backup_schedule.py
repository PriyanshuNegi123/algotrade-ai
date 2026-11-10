import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.storage.backup_crypto import BackupError, encrypt_dump
from scripts import backup_job as job
from scripts import backup_postgres as backup
from scripts import backup_schedule as schedule
from scripts.bootstrap_local import private_write
from scripts.google_drive import directory, secure_json

NOW = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
KEY = bytes(range(32))
DUMP = b"PGDMPsynthetic-only-dump"
NAME = "algotrade-pg-backup-" + "a" * 32 + ".atbackup"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz or UTC)

    monkeypatch.setattr(job, "datetime", FixedClock)
    directory(tmp_path)
    path = backup.backup_directory(tmp_path)
    backup.recovery_key(path, create=True)
    receipt = {
        "state": "RESTORE_VERIFIED",
        "verified_at": NOW.isoformat(),
        "manifest": {"created_at": NOW.isoformat()},
        "restore": {
            "restore_verified": True,
            "network": "none",
            "superuser": False,
            "admin_sessions": 0,
        },
    }
    private_write(path / "latest.json", json.dumps(receipt))
    (tmp_path / ".venv/bin").mkdir(parents=True)
    (tmp_path / ".venv/bin/python").write_text("synthetic-runtime")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/backup_job.py").write_text("# synthetic job")
    monkeypatch.setattr(schedule, "system_uses_ist", lambda: True)
    monkeypatch.setattr(schedule.sys, "platform", "darwin")
    return tmp_path


@pytest.mark.parametrize("elapsed,due", [(0, False), (2, False), (3, True), (7, True)])
def test_three_calendar_day_policy(workspace, elapsed, due):
    state = job.health(workspace, now=NOW + timedelta(days=elapsed))
    assert state["due"] is due and state["interval_days"] == 3
    assert state["next_due_ist_date"] == "2026-11-12"
    assert not state["remote_access_checked"]
    assert state["offline_recovery_copy"] == "NOT_CONFIRMED"


@pytest.mark.parametrize(
    "moment,due",
    [
        (datetime(2026, 11, 11, 18, 29, 59, tzinfo=UTC), False),
        (datetime(2026, 11, 11, 18, 30, tzinfo=UTC), True),
    ],
)
def test_due_date_changes_at_ist_midnight_not_utc(workspace, moment, due):
    assert job.health(workspace, now=moment)["due"] is due


def test_missing_key_is_reported_without_creating_one(workspace):
    target = workspace / ".local/backups/recovery.key"
    target.unlink()
    assert job.health(workspace)["state"] == "RECOVERY_KEY_REQUIRED"
    assert not target.exists()


def test_restore_verification_does_not_postpone_next_backup(workspace):
    path = workspace / ".local/backups/latest.json"
    receipt = secure_json(path)
    receipt["verified_at"] = (NOW + timedelta(days=3)).isoformat()
    private_write(path, json.dumps(receipt))
    state = job.health(workspace, now=NOW + timedelta(days=3))
    assert state["due"] and state["next_due_ist_date"] == "2026-11-12"


def test_success_cannot_be_claimed_by_reverifying_an_old_backup(workspace, monkeypatch):
    path = workspace / ".local/backups/latest.json"
    receipt = secure_json(path)
    receipt["manifest"]["created_at"] = (NOW - timedelta(days=4)).isoformat()
    private_write(path, json.dumps(receipt))
    process = SimpleNamespace(
        communicate=Mock(return_value=(b'{"state":"RESTORE_VERIFIED"}', b"")), returncode=0
    )
    monkeypatch.setattr(job.subprocess, "Popen", Mock(return_value=process))
    assert job.run_job(workspace)["state"] == "FAILED"


def test_new_backups_do_not_create_a_local_ciphertext_cache(workspace, monkeypatch):
    import sys

    captured = {}

    def upload(value, name):
        captured["value"] = value
        return {
            "file_name": name,
            "file_id": "file1",
            "folder_id": "folder1",
            "encrypted_bytes": len(value),
            "cipher_sha256": "0" * 64,
        }

    drive = SimpleNamespace(upload=upload, download=lambda receipt: captured["value"], close=Mock())
    monkeypatch.setattr(backup, "ROOT", workspace)
    monkeypatch.setattr(
        backup, "authorize", lambda *args, **kwargs: SimpleNamespace(token="synthetic")
    )
    monkeypatch.setattr(backup, "client_config", lambda path: {})
    monkeypatch.setattr(
        backup, "local_database", lambda root: ("docker", "db", "sha256:" + "a" * 64)
    )
    monkeypatch.setattr(backup, "export_dump", lambda *args: DUMP)
    monkeypatch.setattr(backup, "DriveBackup", lambda token: drive)
    monkeypatch.setattr(backup, "restore_drill", lambda *args: {"restore_verified": True})
    monkeypatch.setattr(sys, "argv", ["backup_postgres", "backup"])
    assert backup.main() == 0
    assert list((workspace / ".local/backups").glob("*.atbackup")) == []
    assert (workspace / ".local/backups/recovery.key").exists()


def test_not_due_does_not_upload_or_mask_previous_failure(workspace, monkeypatch):
    path = workspace / ".local/backups"
    previous = {"state": "FAILED", "started_at": NOW.isoformat()}
    private_write(path / "job-status.json", json.dumps(previous))
    launch = Mock(side_effect=AssertionError("No subprocess expected"))
    monkeypatch.setattr(job.subprocess, "Popen", launch)
    assert job.run_job(workspace)["state"] == "SKIPPED_NOT_DUE"
    assert secure_json(path / "job-status.json") == previous
    launch.assert_not_called()


def test_failed_child_does_not_leak_output_or_tokens(workspace, monkeypatch):
    process = SimpleNamespace(
        communicate=Mock(return_value=(b"synthetic-private-token", b"secret")), returncode=1
    )
    monkeypatch.setattr(job.subprocess, "Popen", Mock(return_value=process))
    result = job.run_job(workspace, force=True)
    assert result["state"] == "FAILED"
    assert "synthetic-private-token" not in json.dumps(result)
    assert "secret" not in (workspace / ".local/backups/job-status.json").read_text()


@pytest.mark.parametrize("pending", [False, True])
def test_timeout_requests_only_child_interrupt_and_records_cleanup(workspace, monkeypatch, pending):
    import signal
    import subprocess

    timeout = subprocess.TimeoutExpired("synthetic backup", 900)
    process = SimpleNamespace(
        communicate=Mock(side_effect=[timeout, timeout if pending else (b"", b"")]),
        send_signal=Mock(),
    )
    monkeypatch.setattr(job.subprocess, "Popen", Mock(return_value=process))
    result = job.run_job(workspace, force=True)
    assert result["state"] == ("CLEANUP_PENDING" if pending else "TIMED_OUT")
    process.send_signal.assert_called_once_with(signal.SIGINT)


def test_system_timezone_change_is_recorded_without_backup(workspace, monkeypatch):
    import sys

    monkeypatch.setattr(job, "ROOT", workspace)
    monkeypatch.setattr(job, "system_uses_ist", lambda: False)
    monkeypatch.setenv("ALGOTRADE_BACKUP_SCHEDULED", "1")
    monkeypatch.setattr(sys, "argv", ["backup_job", "run"])
    start = Mock(side_effect=AssertionError("No backup expected"))
    monkeypatch.setattr(job, "run_job", start)
    assert job.main() == 2
    assert (
        secure_json(workspace / ".local/backups/job-check.json")["state"]
        == "BLOCKED_TIMEZONE_CHANGED"
    )
    start.assert_not_called()


def test_launch_failure_is_persisted(workspace, monkeypatch):
    monkeypatch.setattr(job.subprocess, "Popen", Mock(side_effect=OSError("private detail")))
    assert job.run_job(workspace, force=True)["state"] == "FAILED"


def test_success_requires_new_verified_receipt(workspace, monkeypatch):
    def communicate(**kwargs):
        return json.dumps({"state": "RESTORE_VERIFIED"}).encode(), b""

    process = SimpleNamespace(communicate=communicate, returncode=0)
    monkeypatch.setattr(job.subprocess, "Popen", Mock(return_value=process))
    assert job.run_job(workspace, force=True)["state"] == "VERIFIED"


def test_job_lock_prevents_overlap(workspace):
    path = workspace / ".local/backups"
    with job.job_lock(path), pytest.raises(BackupError, match="ALREADY_RUNNING"):
        job.run_job(workspace, force=True)


def test_plist_has_no_startup_run_no_retry_and_no_log_growth(workspace):
    data = schedule.schedule(workspace)
    assert data["ProgramArguments"] == [
        str(workspace / ".venv/bin/python"),
        "-m",
        "scripts.backup_job",
        "run",
    ]
    assert data["StartCalendarInterval"] == {"Hour": 21, "Minute": 30}
    assert data["KeepAlive"] is False and data["RunAtLoad"] is False
    assert data["StandardOutPath"] == data["StandardErrorPath"] == "/dev/null"
    assert not {"GOOGLE_TOKEN", "POSTGRES_PASSWORD"} & set(data["EnvironmentVariables"])


def test_timezone_mismatch_rejected(workspace, monkeypatch):
    monkeypatch.setattr(schedule, "system_uses_ist", lambda: False)
    with pytest.raises(BackupError, match="TIMEZONE"):
        schedule.prepare(workspace)


def test_install_owns_only_expected_agent(workspace, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Library").mkdir(parents=True)
    calls = []

    def launchctl(*args):
        calls.append(args)
        return 1 if args[0] == "print" else 0

    monkeypatch.setattr(schedule, "launchctl", launchctl)
    assert schedule.install(workspace, home)["interval_days"] == 3
    target = home / "Library/LaunchAgents" / (schedule.LABEL + ".plist")
    assert target.stat().st_mode & 0o777 == 0o600
    assert calls[-1][0] == "bootstrap" and "gui/" in calls[-1][1]


def test_conflicting_agent_is_never_overwritten(workspace, tmp_path, monkeypatch):
    home = tmp_path / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    target = agents / (schedule.LABEL + ".plist")
    private_write(target, "an unrelated existing job")
    monkeypatch.setattr(schedule, "launchctl", lambda *args: 1)
    with pytest.raises(BackupError, match="LABEL_CONFLICT"):
        schedule.install(workspace, home)
    assert target.read_text() == "an unrelated existing job"


def test_disable_refuses_an_active_job(workspace, tmp_path, monkeypatch):
    import plistlib

    home = tmp_path / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    target = agents / (schedule.LABEL + ".plist")
    private_write(target, plistlib.dumps(schedule.schedule(workspace)).decode())
    monkeypatch.setattr(
        schedule.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="state = running\n"),
    )
    with pytest.raises(BackupError, match="ACTIVE_RETRY"):
        schedule.disable(workspace, home)
    assert target.exists()


def test_disable_removes_only_matching_inactive_agent(workspace, tmp_path, monkeypatch):
    import plistlib

    home = tmp_path / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    target = agents / (schedule.LABEL + ".plist")
    private_write(target, plistlib.dumps(schedule.schedule(workspace)).decode())
    other = agents / "unrelated.plist"
    other.write_text("untouched")
    monkeypatch.setattr(
        schedule.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="state = not running\n"),
    )
    calls = Mock(return_value=0)
    monkeypatch.setattr(schedule, "launchctl", calls)
    assert schedule.disable(workspace, home)["state"] == "DISABLED"
    assert not target.exists() and other.read_text() == "untouched"
    assert calls.call_args.args[0] == "bootout"


@pytest.mark.parametrize("remote_ok", [True, False])
def test_prune_only_removes_currently_cloud_verified_cache(workspace, remote_ok):
    path = workspace / ".local/backups"
    value = encrypt_dump(DUMP, KEY)
    target = path / NAME
    target.write_bytes(value)
    private_write(
        path / (NAME + ".json"), json.dumps({"state": "RESTORE_VERIFIED", "file_name": NAME})
    )
    drive = SimpleNamespace(
        download=Mock(
            return_value=value, side_effect=None if remote_ok else BackupError("CLOUD_FAILED")
        )
    )
    if remote_ok:
        assert backup.prune_verified_cache(path, drive, KEY)["bytes_reclaimed"] == len(value)
        assert not target.exists()
    else:
        with pytest.raises(BackupError):
            backup.prune_verified_cache(path, drive, KEY)
        assert target.exists()
    assert (path / "recovery.key").exists() and (path / "latest.json").exists()


def test_prune_preserves_unverified_cache_and_symlink(workspace):
    path = workspace / ".local/backups"
    target = path / NAME
    target.write_bytes(b"unverified")
    drive = SimpleNamespace(download=Mock(side_effect=AssertionError("No network expected")))
    assert backup.prune_verified_cache(path, drive, KEY)["files_removed"] == 0
    assert target.exists()
    target.unlink()
    target.symlink_to(path / "recovery.key")
    private_write(
        path / (NAME + ".json"), json.dumps({"state": "RESTORE_VERIFIED", "file_name": NAME})
    )
    with pytest.raises(OSError):
        backup.prune_verified_cache(path, drive, KEY)
    assert target.is_symlink() and (path / "recovery.key").exists()


@pytest.mark.parametrize("variant", ["valid", "wrong-key", "future", "malformed"])
def test_cloud_recovery_status_requires_matching_verified_key(workspace, variant):
    import hashlib

    from backend.app.database import SCHEMA_REVISION

    path = workspace / ".local/backups"
    kit = {
        "state": "RECOVERY_VERIFIED",
        "protected_key_sha256": hashlib.sha256(backup.recovery_key(path)).hexdigest(),
        "schema_revision": SCHEMA_REVISION,
        "original_key_required_for_verification": False,
        "verified_at": NOW.isoformat(),
        "restore": {
            "restore_verified": True,
            "superuser": False,
            "admin_sessions": 0,
            "network": "none",
        },
    }
    if variant == "wrong-key":
        kit["protected_key_sha256"] = "0" * 64
    if variant == "future":
        kit["verified_at"] = (NOW + timedelta(days=1)).isoformat()
    if variant == "malformed":
        kit["restore"] = None
    private_write(path / "recovery-kit.json", json.dumps(kit))
    state = job.health(workspace)
    assert state["state"] == "LOCAL_CHECKS_PASSED"
    assert state["offline_recovery_copy"] == "NOT_CONFIRMED"
    assert not state["remote_access_checked"]
    assert (state["cloud_recovery_kit"] != "NOT_CONFIRMED") is (variant == "valid")
    assert ("OFF_DEVICE_RECOVERY_COPY_NOT_CONFIRMED" in state["warnings"]) is (variant != "valid")
