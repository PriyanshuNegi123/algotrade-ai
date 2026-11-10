import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app.brokers import oauth_store as vault
from backend.app.brokers.oauth import OAuthApp, OAuthToken, daily_cutoff

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
TOKEN = "synthetic-private-oauth-bearer"


@pytest.fixture
def app():
    return OAuthApp(
        client_id="synthetic-client",
        client_secret=SecretStr("synthetic-private-value"),
        redirect_uri="http://127.0.0.1:8000/auth/upstox/callback",
    )


@pytest.fixture
def token():
    return OAuthToken(SecretStr(TOKEN), NOW, NOW, daily_cutoff(NOW))


@pytest.fixture
def store(tmp_path):
    return vault.OAuthTokenStore(tmp_path / "oauth", clock=lambda: NOW)


def test_explicit_save_roundtrip_randomized_ciphertext_and_private_modes(app, token, store):
    path = store._directory
    assert not path.exists()
    store.save(app, token)
    first, key = (path / vault.TOKEN_FILE).read_bytes(), (path / vault.KEY_FILE).read_bytes()
    assert first.startswith(vault.MAGIC) and len(key) == 32
    assert TOKEN.encode() not in first and key not in first
    assert app.client_secret.get_secret_value().encode() not in first
    assert store.load(app) == token
    assert stat.S_IMODE(path.stat().st_mode) == 0o700
    for name in (vault.TOKEN_FILE, vault.KEY_FILE, vault.LOCK_FILE):
        assert stat.S_IMODE((path / name).stat().st_mode) == 0o600
    store.save(app, token)
    assert (path / vault.TOKEN_FILE).read_bytes() != first
    assert (path / vault.KEY_FILE).read_bytes() == key
    assert sorted(p.name for p in path.iterdir()) == sorted(
        [vault.TOKEN_FILE, vault.KEY_FILE, vault.LOCK_FILE]
    )
    assert TOKEN not in repr(store.load(app))


def test_missing_status_is_read_only_and_does_not_create_keys(app, store):
    status = store.status(app)
    assert status["state"] == "OAUTH_VAULT_NOT_INITIALIZED"
    assert not status["live_enabled"] and not status["broker_access_verified"]
    assert not store._directory.exists()


def test_ready_status_is_metadata_only_not_broker_or_trading_permission(app, token, store):
    store.save(app, token)
    status = store.status(app)
    assert status["state"] == "STORED_UNVERIFIED"
    assert TOKEN not in json.dumps(status) and app.client_id not in json.dumps(status)
    assert not status["broker_access_verified"] and not status["live_enabled"]


@pytest.mark.parametrize(
    "kind", ["expired", "naive", "future", "reversed", "late-cutoff", "bad-token"]
)
def test_invalid_input_never_initializes_vault(app, token, store, kind):
    changes = {
        "expired": {"expires_at": NOW},
        "naive": {"requested_at": NOW.replace(tzinfo=None)},
        "future": {"received_at": NOW + timedelta(microseconds=1)},
        "reversed": {"received_at": NOW - timedelta(seconds=1)},
        "late-cutoff": {"expires_at": token.expires_at + timedelta(seconds=1)},
        "bad-token": {"access_token": SecretStr("invalid\nvalue")},
    }
    with pytest.raises(vault.OAuthStoreError):
        store.save(app, replace(token, **changes[kind]))
    assert not store._directory.exists()


def test_expiry_is_rechecked_on_load_and_fresh_token_can_replace_expired(app, token, store):
    store.save(app, token)
    rollback = vault.OAuthTokenStore(
        store._directory, clock=lambda: NOW - timedelta(microseconds=1)
    )
    assert rollback.status(app)["state"] == "OAUTH_VAULT_INVALID_METADATA"
    later = vault.OAuthTokenStore(store._directory, clock=lambda: token.expires_at)
    assert later.status(app)["state"] == "OAUTH_VAULT_TOKEN_EXPIRED"
    fresh = OAuthToken(
        SecretStr("synthetic-fresh-bearer"),
        token.expires_at,
        token.expires_at,
        daily_cutoff(token.expires_at),
    )
    later.save(app, fresh)
    assert later.load(app) == fresh


@pytest.mark.parametrize("kind", ["client", "secret", "callback"])
def test_changed_app_cannot_read_or_overwrite_existing_vault(app, token, store, kind):
    store.save(app, token)
    before = (store._directory / vault.TOKEN_FILE).read_bytes()
    altered = app.model_copy(
        update={
            "client": {"client_id": "different-client"},
            "secret": {"client_secret": SecretStr("different-secret")},
            "callback": {"redirect_uri": "https://example.test/different-callback"},
        }[kind]
    )
    with pytest.raises(vault.OAuthStoreError, match="AUTHENTICATION_FAILED"):
        store.load(altered)
    with pytest.raises(vault.OAuthStoreError, match="AUTHENTICATION_FAILED"):
        store.save(altered, token)
    assert (store._directory / vault.TOKEN_FILE).read_bytes() == before


@pytest.mark.parametrize("kind", ["header", "nonce", "ciphertext", "oversized"])
def test_corruption_never_returns_a_token_or_overwrites_old_data(app, token, store, kind):
    store.save(app, token)
    path = store._directory / vault.TOKEN_FILE
    value = bytearray(path.read_bytes())
    if kind == "oversized":
        value = b"x" * (vault.MAX_ENCRYPTED + 1)
    else:
        value[{"header": 0, "nonce": len(vault.MAGIC), "ciphertext": -1}[kind]] ^= 1
    path.write_bytes(value)
    for action in (lambda: store.load(app), lambda: store.save(app, token)):
        with pytest.raises(vault.OAuthStoreError):
            action()
    assert path.read_bytes() == value


def test_missing_or_corrupt_key_is_never_silently_replaced(app, token, store):
    store.save(app, token)
    path = store._directory / vault.KEY_FILE
    path.unlink()
    for action in (lambda: store.load(app), lambda: store.save(app, token)):
        with pytest.raises(vault.OAuthStoreError, match="KEY_REQUIRED"):
            action()
    assert not path.exists()
    path.write_bytes(b"bad-key")
    path.chmod(0o600)
    with pytest.raises(vault.OAuthStoreError, match="KEY_INVALID"):
        store.save(app, token)
    assert path.read_bytes() == b"bad-key"


@pytest.mark.parametrize("name", [vault.TOKEN_FILE, vault.KEY_FILE, vault.LOCK_FILE])
@pytest.mark.parametrize("kind", ["permissions", "symlink", "hardlink"])
def test_unsafe_private_files_are_rejected_and_external_target_preserved(
    app, token, store, tmp_path, name, kind
):
    store.save(app, token)
    path = store._directory / name
    if kind == "permissions":
        path.chmod(0o644)
    else:
        target = tmp_path / "unrelated"
        target.write_bytes(b"unrelated-private-content")
        target.chmod(0o600)
        path.unlink()
        if kind == "symlink":
            path.symlink_to(target)
        else:
            os.link(target, path)
    for action in (lambda: store.load(app), lambda: store.save(app, token)):
        with pytest.raises(vault.OAuthStoreError):
            action()
    if kind != "permissions":
        assert target.read_bytes() == b"unrelated-private-content"


def test_symlink_ancestor_and_insecure_directory_are_rejected(app, token, tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(vault.OAuthStoreError, match="UNSAFE_DIRECTORY"):
        vault.OAuthTokenStore(alias / "nested", clock=lambda: NOW).save(app, token)
    assert not (target / "nested").exists()
    target.chmod(0o755)
    with pytest.raises(vault.OAuthStoreError, match="UNSAFE_DIRECTORY"):
        vault.OAuthTokenStore(target, clock=lambda: NOW).save(app, token)
    assert not list(target.iterdir())


def test_exclusive_lock_rejects_overlapping_access(app, token, store):
    store.save(app, token)
    with store._open(create=False) as directory, store._lock(directory, create=False):
        for action in (lambda: store.load(app), lambda: store.save(app, token)):
            with pytest.raises(vault.OAuthStoreError, match="BUSY"):
                action()
    assert store.load(app) == token


def test_atomic_replace_failure_preserves_previous_token_and_cleans_own_temp(
    app, token, store, monkeypatch
):
    store.save(app, token)
    before = (store._directory / vault.TOKEN_FILE).read_bytes()
    monkeypatch.setattr(vault.os, "replace", Mock(side_effect=OSError("synthetic-private-error")))
    with pytest.raises(
        vault.OAuthStoreError, match="^OAUTH_VAULT_FILESYSTEM_UNAVAILABLE$"
    ) as error:
        store.save(app, token)
    assert "synthetic-private-error" not in str(error.value)
    assert (store._directory / vault.TOKEN_FILE).read_bytes() == before
    assert not list(store._directory.glob(".token-*.tmp"))


def test_temp_name_collision_never_deletes_existing_unrelated_file(app, token, store, monkeypatch):
    store.save(app, token)
    name = ".token-" + ("a" * 32) + ".tmp"
    path = store._directory / name
    path.write_bytes(b"preserve-this-file")
    path.chmod(0o600)
    monkeypatch.setattr(vault.secrets, "token_hex", lambda count: "a" * 32)
    with pytest.raises(vault.OAuthStoreError):
        store.save(app, token)
    assert path.read_bytes() == b"preserve-this-file"


def test_older_token_cannot_replace_newer_and_no_unknown_artifact_key_reset(
    app, token, store, tmp_path
):
    store.save(app, token)
    old = replace(token, requested_at=NOW - timedelta(seconds=1))
    with pytest.raises(vault.OAuthStoreError, match="OLDER_TOKEN_REJECTED"):
        store.save(app, old)
    orphan = tmp_path / "orphan"
    orphan.mkdir(mode=0o700)
    (orphan / "unexpected.enc").write_bytes(b"preserve-unknown-artifact")
    with pytest.raises(vault.OAuthStoreError, match="KEY_REQUIRED"):
        vault.OAuthTokenStore(orphan, clock=lambda: NOW).save(app, token)
    assert not (orphan / vault.KEY_FILE).exists()


def test_directory_sync_error_reports_failure_even_if_new_token_is_already_published(
    app, token, store, monkeypatch
):
    store.save(app, token)
    fresh = replace(token, access_token=SecretStr("synthetic-replacement-bearer"))
    original = vault.os.fsync

    def fail_directory_sync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("synthetic-directory-sync-failure")
        original(descriptor)

    monkeypatch.setattr(vault.os, "fsync", fail_directory_sync)
    with pytest.raises(vault.OAuthStoreError, match="^OAUTH_VAULT_FILESYSTEM_UNAVAILABLE$"):
        store.save(app, fresh)
    # Atomic publication preceded the failed durability check; do not claim rollback.
    assert store.load(app) == fresh
    assert not list(store._directory.glob(".token-*.tmp"))
