"""Finite macOS user schedule for the November 2026 read-only observation pilot."""

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from scripts.backup_job import system_uses_ist
from scripts.bootstrap_local import ROOT, private_read, private_write
from scripts.observation_job import TIMES, ObservationJobError, arm, directory, read_json

LABEL = "com.algotrade-ai.observation-pilot"


def schedule(root: Path) -> dict:
    checkpoints = [
        {"Month": 11, "Day": day, "Hour": checkpoint.hour, "Minute": checkpoint.minute}
        for day in (12, 13, 16, 17)
        for checkpoint in TIMES
    ]
    checkpoints.append({"Month": 11, "Day": 18, "Hour": 9, "Minute": 45})
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(root / ".venv/bin/python"),
            "-m",
            "scripts.observation_job",
            "run",
        ],
        "WorkingDirectory": str(root),
        "StartCalendarInterval": checkpoints,
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    }


def launchctl(*arguments: str) -> int:
    return subprocess.run(
        ["/bin/launchctl", *arguments], capture_output=True, timeout=20
    ).returncode


def install(root: Path, home: Path, *, now: datetime | None = None) -> dict:
    if sys.platform != "darwin" or not system_uses_ist():
        raise ObservationJobError("MACOS_IST_REQUIRED")
    from backend.app.market_data.contracts import IST

    if (now or datetime.now(IST)).astimezone(IST).date() > date(2026, 11, 17):
        raise ObservationJobError("PILOT_WINDOW_ENDED")
    if not (root / ".venv/bin/python").is_file():
        raise ObservationJobError("JOB_RUNTIME_REQUIRED")
    library = home / "Library"
    if library.is_symlink() or not library.is_dir() or library.stat().st_uid != os.getuid():
        raise ObservationJobError("UNSAFE_LIBRARY")
    agents = library / "LaunchAgents"
    if agents.is_symlink():
        raise ObservationJobError("UNSAFE_AGENT_DIRECTORY")
    agents.mkdir(mode=0o700, exist_ok=True)
    if agents.stat().st_uid != os.getuid() or agents.stat().st_mode & 0o022:
        raise ObservationJobError("UNSAFE_AGENT_DIRECTORY")
    target = agents / (LABEL + ".plist")
    contents = plistlib.dumps(schedule(root)).decode()
    original = private_read(target)
    domain = f"gui/{os.getuid()}"
    registered = launchctl("print", domain + "/" + LABEL) == 0
    if (original is not None and original != contents) or (registered and original is None):
        raise ObservationJobError("JOB_LABEL_CONFLICT")
    # Re-arming never clears an uncertain-capture pause or the once-only ledger.
    arm(root)
    if not registered:
        private_write(target, contents)
        if launchctl("bootstrap", domain, str(target)):
            if original is None:
                target.unlink()
            raise ObservationJobError("JOB_INSTALL_FAILED")
    result = {
        "state": "INSTALLED",
        "label": LABEL,
        "capture_checkpoints": 12,
        "window_end_ist": "2026-11-17",
        "phase2_complete": False,
        "live_enabled": False,
    }
    private_write(directory(root) / "schedule.json", json.dumps(result) + "\n")
    return result


def disable(root: Path, home: Path) -> dict:
    library = home / "Library"
    agents = library / "LaunchAgents"
    if library.is_symlink() or agents.is_symlink():
        raise ObservationJobError("UNSAFE_AGENT_DIRECTORY")
    target = agents / (LABEL + ".plist")
    original = private_read(target)
    if original is None:
        return {"state": "NOT_INSTALLED"}
    if original != plistlib.dumps(schedule(root)).decode():
        raise ObservationJobError("JOB_LABEL_CONFLICT")
    domain = f"gui/{os.getuid()}/" + LABEL
    result = subprocess.run(
        ["/bin/launchctl", "print", domain], capture_output=True, text=True, timeout=20
    )
    if re.search(r"^\s*state = running$", result.stdout, re.M):
        raise ObservationJobError("JOB_ACTIVE_WAIT_FOR_FINISH")
    if result.returncode == 0 and launchctl("bootout", domain):
        raise ObservationJobError("JOB_DISABLE_FAILED")
    target.unlink()
    result = {"state": "DISABLED", "label": LABEL}
    private_write(directory(root) / "schedule.json", json.dumps(result) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "disable", "status"))
    args = parser.parse_args()
    if args.action == "install":
        result = install(ROOT, Path.home())
    elif args.action == "disable":
        result = disable(ROOT, Path.home())
    else:
        result = {
            "registered": launchctl("print", f"gui/{os.getuid()}/" + LABEL) == 0,
            "last_check": read_json(directory(ROOT) / "status.json"),
        }
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("OBSERVATION_SCHEDULE_UNAVAILABLE: details withheld") from None
