import json
import subprocess
from unittest.mock import patch

import pytest

from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.supervision_store import CapturePolicy
from scripts.bootstrap_local import bootstrap_lock
from scripts.capture_local import LocalCaptureError, capture_local, control_local, main

KEY = "NSE_INDEX|Synthetic local capture"


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".env").write_text("COMPOSE_PROJECT_NAME=verify-local\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/supervise_capture.py").write_text("# trusted supervisor source\n")
    (tmp_path / "scripts/control_capture.py").write_text("# trusted control source\n")
    return tmp_path


@pytest.mark.parametrize("preflight_only", [True, False])
def test_private_container_forwarding_and_preflight_flag(workspace, preflight_only):
    response = {"state": "LOCAL_CHECKS_PASSED"} if preflight_only else {"capture": {"id": "a" * 32}}
    with (
        patch("scripts.capture_local.docker_binary", return_value="/docker"),
        patch("scripts.capture_local.local_engine"),
        patch("scripts.capture_local.invoke", side_effect=["container-id", str(workspace)]),
        patch(
            "scripts.capture_local.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, json.dumps(response), ""),
        ) as run,
    ):
        code, result = capture_local(
            workspace,
            FeedRequest(instrument_keys=(KEY,)),
            CapturePolicy(),
            preflight_only=preflight_only,
        )
    assert code == 0 and result == response
    command = run.call_args.args[0]
    assert "exec" in command and "-i" in command and "--workdir" in command
    assert "--preflight-only" in command if preflight_only else "--preflight-only" not in command
    assert command[command.index("--instrument-key") + 1] == KEY
    assert "--env" not in command and "--env-file" not in command
    assert run.call_args.kwargs["input"] == "# trusted supervisor source\n"


@pytest.mark.parametrize("containers", ["", "first\nsecond"])
def test_missing_or_ambiguous_container_never_starts(workspace, containers):
    with (
        patch("scripts.capture_local.docker_binary", return_value="/docker"),
        patch("scripts.capture_local.local_engine"),
        patch("scripts.capture_local.invoke", return_value=containers),
        patch("scripts.capture_local.subprocess.run") as run,
        pytest.raises(LocalCaptureError, match="NOT_UNIQUE_OR_RUNNING"),
    ):
        capture_local(
            workspace, FeedRequest(instrument_keys=(KEY,)), CapturePolicy(), preflight_only=False
        )
    run.assert_not_called()


def test_wrong_workspace_container_never_starts(workspace):
    with (
        patch("scripts.capture_local.docker_binary", return_value="/docker"),
        patch("scripts.capture_local.local_engine"),
        patch("scripts.capture_local.invoke", side_effect=["container", "/other/project"]),
        patch("scripts.capture_local.subprocess.run") as run,
        pytest.raises(LocalCaptureError, match="DIRECTORY_MISMATCH"),
    ):
        capture_local(
            workspace, FeedRequest(instrument_keys=(KEY,)), CapturePolicy(), preflight_only=False
        )
    run.assert_not_called()


def test_blocked_preflight_preserves_nonzero_exit(workspace):
    payload = {"state": "BLOCKED", "blockers": ["CREDENTIAL_MISSING"]}
    with (
        patch("scripts.capture_local.docker_binary", return_value="/docker"),
        patch("scripts.capture_local.local_engine"),
        patch("scripts.capture_local.invoke", side_effect=["container", str(workspace)]),
        patch(
            "scripts.capture_local.subprocess.run",
            return_value=subprocess.CompletedProcess([], 2, json.dumps(payload), ""),
        ),
    ):
        code, report = capture_local(
            workspace, FeedRequest(instrument_keys=(KEY,)), CapturePolicy(), preflight_only=False
        )
    assert code == 2 and report == payload


def test_cli_errors_never_echo_sensitive_exception(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["capture_local", "--instrument-key", KEY])
    marker = "synthetic-private-error-marker"
    with patch("scripts.capture_local.capture_local", side_effect=RuntimeError(marker)):
        assert main() == 2
    output = capsys.readouterr()
    assert marker not in output.out + output.err
    assert "sensitive details withheld" in output.out


def test_invalid_quota_never_invokes_docker(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["capture_local", "--instrument-key", KEY, "--max-events", "0"])
    with patch("scripts.capture_local.capture_local") as run:
        assert main() == 2
    run.assert_not_called()
    assert "LOCAL_CAPTURE_FAILED" in capsys.readouterr().out


def test_stop_control_works_while_capture_holds_workspace_lock(workspace):
    with (
        bootstrap_lock(workspace),
        patch("scripts.capture_local.docker_binary", return_value="/docker"),
        patch("scripts.capture_local.local_engine"),
        patch("scripts.capture_local.invoke", side_effect=["container", str(workspace)]),
        patch(
            "scripts.capture_local.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, '{"stop_requested":true}', ""),
        ) as run,
    ):
        code, report = control_local(workspace, "stop", "a" * 32)
    assert code == 0 and report["stop_requested"]
    assert "kill" not in run.call_args.args[0]
    assert "--capture-id" in run.call_args.args[0]
    assert run.call_args.kwargs["input"] == "# trusted control source\n"


@pytest.mark.parametrize("identity", [None, "other; kill -9 1"])
def test_invalid_stop_request_never_invokes_docker(workspace, identity):
    with patch("scripts.capture_local.local_container") as target, pytest.raises(LocalCaptureError):
        control_local(workspace, "stop", identity)
    target.assert_not_called()


def test_status_cli_does_not_start_capture(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["capture_local", "--status"])
    with (
        patch("scripts.capture_local.control_local", return_value=(0, {"captures": []})),
        patch("scripts.capture_local.capture_local") as start,
    ):
        assert main() == 0
    start.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {"captures": []}
