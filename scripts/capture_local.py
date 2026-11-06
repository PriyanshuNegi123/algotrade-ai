"""Explicit bounded recording inside the private local Compose app; never auto-started."""

import argparse
import json
import subprocess
from pathlib import Path

from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.supervision_store import CapturePolicy
from scripts.bootstrap_local import (
    ROOT,
    assignments,
    bootstrap_lock,
    docker_binary,
    invoke,
    local_engine,
    private_read,
    project_name,
)

# The trusted repository CLI is sent over stdin; tokens remain in container settings.
RUN_SOURCE = "import sys; exec(compile(sys.stdin.read(), 'supervise_capture.py', 'exec'))"


class LocalCaptureError(Exception):
    pass


def local_container(root: Path) -> tuple[str, str]:
    executable = docker_binary()
    local_engine(executable)
    original = private_read(root / ".env")
    if original is None:
        raise LocalCaptureError("LOCAL_CONFIGURATION_REQUIRED")
    project = project_name(assignments(original))
    container = invoke(
        [
            executable,
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=app",
            "--format",
            "{{.ID}}",
        ]
    ).strip()
    if not container or "\n" in container:
        raise LocalCaptureError("LOCAL_APP_NOT_UNIQUE_OR_RUNNING")
    directory = invoke(
        [
            executable,
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}',
            container,
        ]
    ).strip()
    if directory != str(root.resolve()):
        raise LocalCaptureError("LOCAL_PROJECT_DIRECTORY_MISMATCH")
    return executable, container


def capture_local(
    root: Path, request: FeedRequest, policy: CapturePolicy, *, preflight_only: bool
) -> tuple[int, dict]:
    with bootstrap_lock(root):
        executable, container = local_container(root)
        command = [
            executable,
            "exec",
            "-i",
            "--workdir",
            "/app",
            container,
            "python",
            "-c",
            RUN_SOURCE,
        ]
        for key in request.instrument_keys:
            command.extend(["--instrument-key", key])
        for name, value in policy.model_dump().items():
            command.extend(["--" + name.replace("_", "-"), str(value)])
        if preflight_only:
            command.append("--preflight-only")
        result = subprocess.run(
            command,
            input=(root / "scripts/supervise_capture.py").read_text(),
            capture_output=True,
            text=True,
            timeout=policy.total_seconds + 120,
        )
        if result.returncode not in (0, 2) or len(result.stdout) > 1024 * 1024:
            raise LocalCaptureError("LOCAL_CAPTURE_COMMAND_FAILED")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise LocalCaptureError("LOCAL_CAPTURE_RESPONSE_INVALID")
        if result.returncode == 2 and payload.get("state") != "BLOCKED":
            raise LocalCaptureError("LOCAL_CAPTURE_RESPONSE_INVALID")
        return result.returncode, payload


def control_local(root: Path, action: str, identity: str | None) -> tuple[int, dict]:
    # Do not take the capture/bootstrap lock: controls must work while capture holds it.
    import re

    if action not in {"status", "stop"} or (action == "stop" and identity is None):
        raise LocalCaptureError("INVALID_CONTROL_REQUEST")
    if identity is not None and re.fullmatch(r"[0-9a-f]{32}", identity) is None:
        raise LocalCaptureError("INVALID_CAPTURE_ID")
    executable, container = local_container(root)
    command = [
        executable,
        "exec",
        "-i",
        "--workdir",
        "/app",
        container,
        "python",
        "-c",
        RUN_SOURCE,
        action,
    ]
    if identity is not None:
        command.extend(["--capture-id", identity])
    result = subprocess.run(
        command,
        input=(root / "scripts/control_capture.py").read_text(),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise LocalCaptureError("LOCAL_CONTROL_FAILED")
    report = json.loads(result.stdout)
    if not isinstance(report, dict):
        raise LocalCaptureError("LOCAL_CONTROL_RESPONSE_INVALID")
    return 0, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", action="append")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--status", action="store_true")
    modes.add_argument("--stop", metavar="CAPTURE_ID")
    parser.add_argument("--capture-id")
    parser.add_argument("--total-seconds", type=int, default=20)
    parser.add_argument("--session-seconds", type=int, default=20)
    parser.add_argument("--max-sessions", type=int, default=1)
    parser.add_argument("--max-payload-bytes", type=int, default=65536)
    parser.add_argument("--max-events", type=int, default=20)
    args = parser.parse_args()
    try:
        if args.status or args.stop:
            if args.instrument_key or (args.stop and args.capture_id):
                raise LocalCaptureError("INVALID_CONTROL_REQUEST")
            code, report = control_local(
                ROOT, "stop" if args.stop else "status", args.stop or args.capture_id
            )
            print(json.dumps(report), flush=True)
            return code
        if not args.instrument_key or args.capture_id:
            raise LocalCaptureError("CAPTURE_KEYS_REQUIRED")
        request = FeedRequest(instrument_keys=tuple(args.instrument_key))
        policy = CapturePolicy(
            total_seconds=args.total_seconds,
            session_seconds=args.session_seconds,
            max_sessions=args.max_sessions,
            max_payload_bytes=args.max_payload_bytes,
            max_events=args.max_events,
        )
        code, report = capture_local(ROOT, request, policy, preflight_only=args.preflight_only)
        print(json.dumps(report), flush=True)
        return code
    except KeyboardInterrupt:
        print("LOCAL_CLIENT_INTERRUPTED: inspect capture status; remote run may reach its limit.")
        return 130
    except Exception:
        print("LOCAL_CAPTURE_FAILED: inspect readiness/capture status; sensitive details withheld.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
