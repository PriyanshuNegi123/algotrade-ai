import os
import stat
from pathlib import Path

import pytest
from argon2 import PasswordHasher

from scripts.bootstrap_local import (
    BootstrapError,
    assignments,
    bootstrap_lock,
    prepare_runtime,
    private_read,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / ".env.example").write_text((ROOT / ".env.example").read_text())
    return tmp_path


def test_new_configuration_private_credentials_and_repeat_preserves(workspace):
    first = prepare_runtime(workspace, existing_volume=False)
    env = workspace / ".env"
    password = workspace / ".local/runtime/admin-password.txt"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE(password.stat().st_mode) == 0o600
    assert stat.S_IMODE(password.parent.stat().st_mode) == 0o700
    assert PasswordHasher().verify(
        first["values"]["ADMIN_PASSWORD_HASH"], password.read_text().strip()
    )
    assert len(first["values"]["POSTGRES_PASSWORD"]) >= 32
    assert first["values"]["DATABASE_URL"].startswith("postgresql+psycopg://algotrade:")
    before = env.read_text()
    second = prepare_runtime(workspace, existing_volume=True)
    assert env.read_text() == before and second["values"] == first["values"]
    assert second["admin_password"] == first["admin_password"]
    assert not list(workspace.glob(".algotrade-secret-*"))


def test_existing_secrets_and_unknown_lines_preserved(workspace):
    first = prepare_runtime(workspace, existing_volume=False)
    env = workspace / ".env"
    with env.open("a") as stream:
        stream.write(
            "CUSTOM_SETTING='preserve exactly'\n"
            "UPSTOX_ANALYTICS_EXPIRES_AT='2027-01-01T00:00:00Z'\n"
        )
    content = env.read_text().replace(
        "UPSTOX_ANALYTICS_TOKEN=", "UPSTOX_ANALYTICS_TOKEN='synthetic-existing-token'"
    )
    env.write_text(content)
    before = env.read_text()
    repeated = prepare_runtime(workspace, existing_volume=True)
    assert env.read_text() == before
    assert repeated["values"]["POSTGRES_PASSWORD"] == first["values"]["POSTGRES_PASSWORD"]


def test_existing_volume_without_password_never_generates_replacement(workspace):
    with pytest.raises(BootstrapError, match="EXISTING_VOLUME_PASSWORD_REQUIRED"):
        prepare_runtime(workspace, existing_volume=True)
    assert (
        not (workspace / ".env").exists()
        and not (workspace / ".local/runtime/admin-password.txt").exists()
    )


@pytest.mark.parametrize(
    "line",
    ["TRADING_MODE=PAPER\n", "LIVE_ENABLED=true\n", "APP_ENV=production\n", "COOKIE_SECURE=true\n"],
)
def test_conflicting_mode_preserved_without_secrets(workspace, line):
    env = workspace / ".env"
    env.write_text(line)
    with pytest.raises(BootstrapError, match="LOCAL_MODE_CONFLICT"):
        prepare_runtime(workspace, existing_volume=False)
    assert (
        env.read_text() == line and not (workspace / ".local/runtime/admin-password.txt").exists()
    )


def test_external_database_and_conflicting_credentials_are_not_reset(workspace):
    env = workspace / ".env"
    text = "DATABASE_URL='postgresql+psycopg://user:keep@external.example/db'\n"
    env.write_text(text)
    with pytest.raises(BootstrapError, match="EXISTING_DATABASE_NOT_LOCAL_COMPOSE"):
        prepare_runtime(workspace, existing_volume=False)
    assert env.read_text() == text
    text = "DATABASE_URL='postgresql+psycopg://algotrade:keep@db/algotrade'\nPOSTGRES_PASSWORD='different'\n"
    env.write_text(text)
    with pytest.raises(BootstrapError, match="DATABASE_CREDENTIAL_CONFLICT"):
        prepare_runtime(workspace, existing_volume=False)
    assert env.read_text() == text


def test_symlinks_hardlinks_and_duplicate_keys_fail_closed(workspace):
    target = workspace / "secret"
    target.write_text("UNCHANGED=yes\n")
    env = workspace / ".env"
    env.symlink_to(target)
    with pytest.raises(BootstrapError, match="SYMLINK"):
        prepare_runtime(workspace, existing_volume=False)
    env.unlink()
    os.link(target, env)
    with pytest.raises(BootstrapError, match="UNSAFE_SECRET_FILE"):
        private_read(env)
    env.unlink()
    env.write_text("POSTGRES_PASSWORD=one\nPOSTGRES_PASSWORD=two\n")
    with pytest.raises(BootstrapError, match="DUPLICATE_ENV_KEY"):
        prepare_runtime(workspace, existing_volume=False)
    assert target.read_text() == "UNCHANGED=yes\n"


def test_existing_admin_hash_without_raw_password_kept(workspace):
    first = prepare_runtime(workspace, existing_volume=False)
    (workspace / ".local/runtime/admin-password.txt").unlink()
    before = (workspace / ".env").read_text()
    result = prepare_runtime(workspace, existing_volume=True)
    assert result["admin_password"] is None and result["admin_password_file"] is None
    assert result["values"]["ADMIN_PASSWORD_HASH"] == first["values"]["ADMIN_PASSWORD_HASH"]
    assert (workspace / ".env").read_text() == before


def test_port_origin_conflicts_and_bootstrap_lock(workspace):
    first = prepare_runtime(workspace, existing_volume=False)
    with pytest.raises(BootstrapError, match="LOCAL_PORT_CONFLICT"):
        prepare_runtime(workspace, existing_volume=True, port=8001)
    with bootstrap_lock(workspace):
        with pytest.raises(BootstrapError, match="ALREADY_RUNNING"):
            with bootstrap_lock(workspace):
                pass
    assert assignments((workspace / ".env").read_text())["APP_BIND_PORT"] == str(first["port"])


def test_secret_directory_symlink_rejected(workspace):
    (workspace / ".local").symlink_to(workspace / "outside", target_is_directory=True)
    with pytest.raises(BootstrapError, match="SYMLINKED_SECRET_DIRECTORY"):
        prepare_runtime(workspace, existing_volume=False)
    assert not (workspace / ".env").exists()


def test_new_custom_port_updates_local_origins(workspace):
    result = prepare_runtime(workspace, existing_volume=False, port=8001)
    assert result["origin"] == "http://127.0.0.1:8001"
    assert "http://127.0.0.1:8001" in result["values"]["ALLOWED_ORIGINS"]
