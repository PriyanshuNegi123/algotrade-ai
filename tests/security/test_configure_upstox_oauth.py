import os
import pty
import select
import stat
import subprocess
import sys
import time
import warnings
from getpass import GetPassWarning
from unittest.mock import Mock

import pytest
from dotenv import dotenv_values
from pydantic import SecretStr

from scripts import configure_upstox_oauth as setup
from scripts.bootstrap_local import BootstrapError, assignments, bootstrap_lock

CLIENT = "synthetic-setup-client"
SECRET = SecretStr("synthetic-setup-private-value")
CALLBACK = "http://127.0.0.1:8000/auth/upstox/callback"
ORIGINAL = (
    "# preserved configuration\r\nTRADING_MODE=OBSERVATION\r\nLIVE_ENABLED=false\r\n"
    "ALLOWED_ORIGINS='[\"http://127.0.0.1:8000\"]'\r\n"
    "UPSTOX_ANALYTICS_TOKEN='synthetic-existing-analytics'\r\n"
    "export CUSTOM_SETTING='first line\r\nsecond line' # preserve\r\n"
)


@pytest.fixture
def workspace(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(ORIGINAL.encode())
    path.chmod(0o600)
    return tmp_path


def save(root, **kwargs):
    return setup.save_oauth_settings(root, CLIENT, SECRET, CALLBACK, **kwargs)


def test_save_preserves_unrelated_bytes_and_secure_mode(workspace, capsys):
    result = save(workspace)
    path = workspace / ".env"
    assert path.read_bytes().startswith(ORIGINAL.encode())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    values = dotenv_values(path)
    assert values["UPSTOX_CLIENT_SECRET"] == SECRET.get_secret_value()
    assert values["UPSTOX_REDIRECT_URI"] == CALLBACK
    assert result["saved"] and not result["registration_verified"]
    assert not result["browser_authorization_started"] and not result["live_enabled"]
    assert not list(workspace.glob(".algotrade-secret-*"))
    assert not (workspace / ".local/upstox").exists()
    assert SECRET.get_secret_value() not in capsys.readouterr().out


def test_repeated_identical_settings_do_not_rewrite(workspace):
    save(workspace)
    before = (workspace / ".env").stat()
    assert save(workspace)["saved"] is False
    assert (workspace / ".env").stat().st_ino == before.st_ino


def test_replacement_requires_explicit_flag_and_preserves_analytics(workspace):
    save(workspace)
    before = (workspace / ".env").read_bytes()
    replacement = SecretStr("synthetic-replacement-private-value")
    with pytest.raises(setup.OAuthSetupError, match="REPLACEMENT_REQUIRES_FLAG"):
        setup.save_oauth_settings(workspace, CLIENT, replacement, CALLBACK)
    assert (workspace / ".env").read_bytes() == before
    setup.save_oauth_settings(workspace, CLIENT, replacement, CALLBACK, replace=True)
    assert (workspace / ".env").read_bytes().startswith(ORIGINAL.encode())
    assert dotenv_values(workspace / ".env")["UPSTOX_CLIENT_SECRET"] == (
        replacement.get_secret_value()
    )


@pytest.mark.parametrize(
    "secret", ["literal$dollar#hash=equals", "quote'and\"double", "braces{ok}"]
)
def test_literal_characters_roundtrip_without_interpolation(workspace, secret, monkeypatch):
    monkeypatch.setenv("dollar", "must-not-expand")
    setup.save_oauth_settings(workspace, CLIENT, SecretStr(secret), CALLBACK)
    assert dotenv_values(workspace / ".env")["UPSTOX_CLIENT_SECRET"] == secret


@pytest.mark.parametrize(
    ("client", "secret", "callback"),
    [
        ("invalid client", SECRET, CALLBACK),
        (CLIENT, SecretStr("bad\nvalue"), CALLBACK),
        (CLIENT, SecretStr("bad\\value"), CALLBACK),
        (CLIENT, SecretStr("${HOME}"), CALLBACK),
        (CLIENT, SecretStr(""), CALLBACK),
        (CLIENT, SECRET, "http://example.com/callback"),
        (CLIENT, SECRET, "http://localhost:8000/auth/upstox/callback"),
        (CLIENT, SECRET, "http://127.0.0.1:8000/api/auth/login"),
        (CLIENT, SECRET, CALLBACK + "?value=1"),
        (CLIENT, SECRET, CALLBACK + "/"),
    ],
)
def test_invalid_or_incompatible_inputs_leave_environment_unchanged(
    workspace, client, secret, callback
):
    before = (workspace / ".env").read_bytes()
    with pytest.raises(setup.OAuthSetupError) as error:
        setup.save_oauth_settings(workspace, client, secret, callback)
    assert secret.get_secret_value() not in str(error.value) if secret.get_secret_value() else True
    assert (workspace / ".env").read_bytes() == before


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "mode", "directory", "large", "fifo"])
def test_unsafe_existing_environment_refused(workspace, kind):
    path = workspace / ".env"
    if kind == "symlink":
        path.rename(workspace / "original")
        path.symlink_to(workspace / "original")
    elif kind == "hardlink":
        os.link(path, workspace / "alias")
    elif kind == "mode":
        path.chmod(0o644)
    elif kind == "large":
        path.write_bytes(b"x" * (1024 * 1024 + 1))
    else:
        path.unlink()
        if kind == "directory":
            path.mkdir()
        else:
            os.mkfifo(path, 0o600)
    with pytest.raises(setup.OAuthSetupError):
        save(workspace)
    assert not (workspace / ".local").exists()


def test_missing_environment_requires_bootstrap(tmp_path):
    with pytest.raises(setup.OAuthSetupError, match="BOOTSTRAP_REQUIRED"):
        save(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "extra",
    [
        "LIVE_ENABLED=true\n",  # Duplicate settings must fail, too.
        "UPSTOX_CLIENT_ID=x\nUPSTOX_CLIENT_ID=y\n",
        "upstox_client_id=x\nUPSTOX_CLIENT_ID=y\n",
        "BROKEN='unterminated\n",
    ],
)
def test_ambiguous_environment_refused(workspace, extra):
    path = workspace / ".env"
    with path.open("a") as stream:
        stream.write(extra)
    before = path.read_bytes()
    with pytest.raises((setup.OAuthSetupError, BootstrapError)):
        save(workspace)
    assert path.read_bytes() == before


def test_live_configuration_not_rewritten(workspace):
    path = workspace / ".env"
    path.write_bytes(path.read_bytes().replace(b"LIVE_ENABLED=false", b"LIVE_ENABLED=true"))
    before = path.read_bytes()
    with pytest.raises(setup.OAuthSetupError, match="OBSERVATION_REQUIRED"):
        save(workspace)
    assert path.read_bytes() == before


def test_shared_bootstrap_lock_blocks_simultaneous_edit(workspace):
    with bootstrap_lock(workspace):
        with pytest.raises(BootstrapError, match="ALREADY_RUNNING"):
            save(workspace)
    assert (workspace / ".env").read_bytes() == ORIGINAL.encode()


def test_atomic_write_failure_preserves_original_and_removes_temp(workspace, monkeypatch):
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("synthetic failure")))
    with pytest.raises(OSError):
        save(workspace)
    assert (workspace / ".env").read_bytes() == ORIGINAL.encode()
    assert not list(workspace.glob(".algotrade-secret-*"))


def test_cli_refuses_noninteractive_secret_entry(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["configure_upstox_oauth"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    prompt = Mock(side_effect=AssertionError("Prompt must not run"))
    monkeypatch.setattr(setup, "getpass", prompt)
    with pytest.raises(setup.OAuthSetupError, match="INTERACTIVE_TERMINAL_REQUIRED"):
        setup.main()
    prompt.assert_not_called()


def test_cli_hidden_prompt_and_metadata_only_output(workspace, monkeypatch, capsys):
    monkeypatch.setattr(setup, "ROOT", workspace)
    monkeypatch.setattr(sys, "argv", ["configure_upstox_oauth"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    inputs = iter([CLIENT, CALLBACK])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(setup, "getpass", lambda _: SECRET.get_secret_value())
    assert setup.main() == 0
    output = capsys.readouterr().out
    assert (
        SECRET.get_secret_value() not in output and CLIENT not in output and CALLBACK not in output
    )
    assert assignments((workspace / ".env").read_text())["UPSTOX_CLIENT_ID"] == CLIENT


@pytest.mark.parametrize(
    "arguments", [["--client-secret", "synthetic-argument"], ["--replace=synthetic-argument"]]
)
def test_unknown_arguments_never_echo_potential_secrets(monkeypatch, capsys, arguments):
    monkeypatch.setattr(sys, "argv", ["configure_upstox_oauth", *arguments])
    with pytest.raises(setup.OAuthSetupError, match="ARGUMENTS_INVALID"):
        setup.main()
    assert "synthetic-argument" not in str(capsys.readouterr())


def test_hidden_prompt_never_falls_back_to_echo(workspace, monkeypatch):
    monkeypatch.setattr(setup, "ROOT", workspace)
    monkeypatch.setattr(sys, "argv", ["configure_upstox_oauth"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: CLIENT)

    def unavailable(_):
        warnings.warn("synthetic terminal unavailable", GetPassWarning, stacklevel=1)
        pytest.fail("Echo fallback must not run")

    monkeypatch.setattr(setup, "getpass", unavailable)
    with pytest.raises(GetPassWarning):
        setup.main()
    assert (workspace / ".env").read_bytes() == ORIGINAL.encode()


def test_concurrent_external_edit_detected_before_replace(workspace, monkeypatch):
    read = setup.read_environment
    count = 0

    def changed(path):
        nonlocal count
        count += 1
        if count == 3:
            path.write_bytes(ORIGINAL.encode() + b"CUSTOM_ADDITION=preserve\n")
        return read(path)

    monkeypatch.setattr(setup, "read_environment", changed)
    with pytest.raises(setup.OAuthSetupError, match="CHANGED_DURING_SETUP"):
        save(workspace)
    assert (workspace / ".env").read_bytes() == ORIGINAL.encode() + b"CUSTOM_ADDITION=preserve\n"


def test_directory_sync_failure_reports_uncertain_published_settings(workspace, monkeypatch):
    sync = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("synthetic directory sync failure")
        sync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(setup.OAuthSetupError, match="SAVE_UNCERTAIN"):
        save(workspace)
    assert dotenv_values(workspace / ".env")["UPSTOX_CLIENT_SECRET"] == SECRET.get_secret_value()
    assert not list(workspace.glob(".algotrade-secret-*"))


def test_actual_terminal_prompt_does_not_echo_secret(workspace):
    master, slave = pty.openpty()
    program = (
        "import runpy,sys; from pathlib import Path; from scripts import bootstrap_local; "
        "bootstrap_local.ROOT=Path(sys.argv[1]); sys.argv=['configure_upstox_oauth']; "
        "runpy.run_module('scripts.configure_upstox_oauth',run_name='__main__')"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(workspace)],
        cwd=setup.ROOT,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    transcript = bytearray()

    def receive_until(marker):
        deadline = time.monotonic() + 5
        while marker not in transcript:
            assert time.monotonic() < deadline, "Synthetic terminal prompt timed out"
            if select.select([master], [], [], 0.1)[0]:
                transcript.extend(os.read(master, 8192))

    try:
        receive_until(b"public client ID): ")
        os.write(master, (CLIENT + "\n").encode())
        receive_until(b"never paste into chat): ")
        os.write(master, (SECRET.get_secret_value() + "\n").encode())
        receive_until(b"Exact registered redirect URL: ")
        os.write(master, (CALLBACK + "\n").encode())
        receive_until(b'"registration_verified": false')
        assert process.wait(timeout=5) == 0
        assert SECRET.get_secret_value().encode() not in transcript
        assert dotenv_values(workspace / ".env")["UPSTOX_CLIENT_SECRET"] == (
            SECRET.get_secret_value()
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master)
