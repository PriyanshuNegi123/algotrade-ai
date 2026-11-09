"""Explicit macOS user-agent installation; checks daily, backs up every three IST dates."""

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from backend.app.storage.backup_crypto import BackupError
from scripts.backup_job import health, system_uses_ist
from scripts.backup_postgres import backup_directory
from scripts.bootstrap_local import ROOT, private_read, private_write

LABEL = "com.algotrade-ai.cloud-backup"


def schedule(root: Path) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(root / ".venv/bin/python"), "-m", "scripts.backup_job", "run"],
        "WorkingDirectory": str(root),
        "StartCalendarInterval": {"Hour": 21, "Minute": 30},
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "ALGOTRADE_BACKUP_SCHEDULED": "1",
        },
    }


def launchctl(*arguments: str) -> int:
    result = subprocess.run(["/bin/launchctl", *arguments], capture_output=True, timeout=20)
    return result.returncode  # Never echo launchctl environment dumps.


def prepare(root: Path) -> tuple[Path, str]:
    if not system_uses_ist():
        raise BackupError("BACKUP_SCHEDULE_REQUIRES_IST_SYSTEM_TIMEZONE")
    state = health(root)
    if not state["recovery_key_ready"] or not state["last_verified_at"]:
        raise BackupError("BACKUP_SCHEDULE_VERIFIED_BASELINE_REQUIRED")
    if not (root / ".venv/bin/python").is_file() or not (root / "scripts/backup_job.py").is_file():
        raise BackupError("BACKUP_SCHEDULE_RUNTIME_REQUIRED")
    path = backup_directory(root)
    contents = plistlib.dumps(schedule(root)).decode()
    private_write(path / (LABEL + ".plist"), contents)
    return path, contents


def install(root: Path, home: Path) -> dict:
    if sys.platform != "darwin":
        raise BackupError("BACKUP_SCHEDULE_MACOS_REQUIRED")
    path, contents = prepare(root)
    library = home / "Library"
    if library.is_symlink() or not library.is_dir() or library.stat().st_uid != os.getuid():
        raise BackupError("BACKUP_SCHEDULE_UNSAFE_LIBRARY")
    agents = library / "LaunchAgents"
    if agents.is_symlink():
        raise BackupError("BACKUP_SCHEDULE_UNSAFE_AGENT_DIRECTORY")
    agents.mkdir(mode=0o700, exist_ok=True)
    if agents.stat().st_uid != os.getuid() or agents.stat().st_mode & 0o022:
        raise BackupError("BACKUP_SCHEDULE_UNSAFE_AGENT_DIRECTORY")
    target = agents / (LABEL + ".plist")
    original = private_read(target)
    domain = f"gui/{os.getuid()}"
    registered = launchctl("print", domain + "/" + LABEL) == 0
    if (original is not None and original != contents) or (registered and original is None):
        raise BackupError("BACKUP_SCHEDULE_LABEL_CONFLICT")
    if not registered:
        private_write(target, contents)
        if launchctl("bootstrap", domain, str(target)) != 0:
            if original is None:
                target.unlink()  # Only our newly created file, never a pre-existing agent.
            raise BackupError("BACKUP_SCHEDULE_BOOTSTRAP_FAILED")
    settings = {
        "state": "INSTALLED",
        "label": LABEL,
        "interval_days": 3,
        "check_time_ist": "21:30",
        "timezone": "Asia/Kolkata",
        "next_due_ist_date": health(root)["next_due_ist_date"],
    }
    private_write(path / "schedule.json", json.dumps(settings) + "\n")
    return settings


def disable(root: Path, home: Path) -> dict:
    agents = home / "Library/LaunchAgents"
    if (home / "Library").is_symlink() or agents.is_symlink():
        raise BackupError("BACKUP_SCHEDULE_UNSAFE_AGENT_DIRECTORY")
    target = agents / (LABEL + ".plist")
    expected = plistlib.dumps(schedule(root)).decode()
    original = private_read(target)
    if original is None:
        return {"state": "NOT_INSTALLED"}
    if original != expected:
        raise BackupError("BACKUP_SCHEDULE_LABEL_CONFLICT")
    domain = f"gui/{os.getuid()}/" + LABEL
    info = subprocess.run(
        ["/bin/launchctl", "print", domain], capture_output=True, text=True, timeout=20
    )
    if re.search(r"^\s*state = running$", info.stdout, re.M):
        raise BackupError("BACKUP_SCHEDULE_ACTIVE_RETRY_AFTER_FINISH")
    if info.returncode == 0 and launchctl("bootout", domain) != 0:
        raise BackupError("BACKUP_SCHEDULE_DISABLE_FAILED")
    target.unlink()  # Only our exact, inactive generated LaunchAgent file.
    settings = {"state": "DISABLED", "label": LABEL, "interval_days": 3}
    private_write(backup_directory(root) / "schedule.json", json.dumps(settings) + "\n")
    return settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install", "status", "disable"))
    args = parser.parse_args()
    if args.action == "install":
        result = install(ROOT, Path.home())
    elif args.action == "disable":
        result = disable(ROOT, Path.home())
    elif args.action == "prepare":
        prepare(ROOT)
        result = {"state": "PREPARED_NOT_INSTALLED", "interval_days": 3, "check_time_ist": "21:30"}
    else:
        result = {
            "registered": launchctl("print", f"gui/{os.getuid()}/" + LABEL) == 0,
            "health": health(ROOT),
        }
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("BACKUP_SCHEDULE_UNAVAILABLE: details withheld") from None
