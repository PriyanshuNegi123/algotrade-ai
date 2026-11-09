import hashlib
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import MAGIC, BackupError, decrypt_dump, encrypt_dump
from backend.app.storage.drive_backup import DriveBackup, upload_session
from scripts import backup_postgres as cli

KEY = bytes(range(32))
DUMP = b"PGDMP" + b"synthetic-dump-not-a-real-database" * 5


def test_encryption_roundtrip_random_nonce_and_hidden_dump():
    first, second = encrypt_dump(DUMP, KEY), encrypt_dump(DUMP, KEY)
    assert first != second and first.startswith(MAGIC)
    assert DUMP not in first and b"dump_sha256" not in first
    dump, manifest = decrypt_dump(first, KEY)
    assert dump == DUMP and manifest["dump_sha256"] == hashlib.sha256(DUMP).hexdigest()
    assert manifest["admin_sessions_excluded"] and manifest["schema_revision"] == SCHEMA_REVISION


@pytest.mark.parametrize("kind", ["key", "header", "nonce", "ciphertext", "truncated"])
def test_tampering_and_wrong_key_fail_before_restore(kind):
    value = bytearray(encrypt_dump(DUMP, KEY))
    key = KEY
    if kind == "key":
        key = bytes(reversed(KEY))
    elif kind == "truncated":
        value = value[:-1]
    else:
        value[{"header": 0, "nonce": len(MAGIC), "ciphertext": -1}[kind]] ^= 1
    with pytest.raises(BackupError):
        decrypt_dump(bytes(value), key)


def test_only_custom_dump_and_256bit_key_are_accepted():
    for dump, key in ((b"plaintext env file", KEY), (DUMP, b"short")):
        with pytest.raises(BackupError):
            encrypt_dump(dump, key)


@pytest.mark.parametrize(
    "url",
    [
        "https://untrusted.invalid/upload/drive/v3/files?uploadType=resumable&upload_id=x",
        "http://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=x",
        "https://www.googleapis.com@untrusted.invalid/upload/drive/v3/files?upload_id=x",
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
    ],
)
def test_upload_session_cannot_redirect_credentials(url):
    with pytest.raises(BackupError, match="SESSION_REJECTED"):
        upload_session(url)


def test_encrypted_cloud_upload_download_checks_ciphertext(monkeypatch):
    value = encrypt_dump(DUMP, KEY)
    digest = hashlib.sha256(value).hexdigest()
    methods = []

    def handler(request):
        methods.append(request.method)
        assert request.url.host == "www.googleapis.com"
        assert DUMP not in request.content and KEY not in request.content
        if request.method == "POST":
            assert json.loads(request.content)["appProperties"]["cipher_sha256"] == digest
            return httpx.Response(
                200,
                headers={
                    "Location": "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id=x"
                },
            )
        if request.method == "PUT":
            assert request.content == value
            return httpx.Response(200, json={"id": "backup1"})
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=value)
        return httpx.Response(
            200,
            json={
                "parents": ["folder1"],
                "mimeType": "application/octet-stream",
                "size": str(len(value)),
                "appProperties": {"algotrade_encrypted_backup": "v1", "cipher_sha256": digest},
                "capabilities": {"canDownload": True},
                "sha256Checksum": digest,
            },
        )

    drive = DriveBackup("synthetic-access", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(drive, "archive_folder", lambda: ("folder1", False))
    try:
        receipt = drive.upload(value, "algotrade-pg-backup-" + "a" * 32 + ".atbackup")
        assert receipt["state"] == "UPLOADED_NOT_VERIFIED" and drive.download(receipt) == value
    finally:
        drive.close()
    assert not set(methods) & {"DELETE", "PATCH"}


def test_plaintext_never_reaches_cloud():
    transport = Mock(side_effect=AssertionError("No network call expected"))
    drive = DriveBackup("synthetic-access", transport=httpx.MockTransport(transport))
    try:
        with pytest.raises(BackupError, match="ENVELOPE_REQUIRED"):
            drive.upload(b"plain secret", "algotrade-pg-backup-" + "a" * 32 + ".atbackup")
    finally:
        drive.close()
    transport.assert_not_called()


def test_private_recovery_key_is_never_silently_replaced(tmp_path):
    (tmp_path / ".local").mkdir(mode=0o700)
    path = cli.backup_directory(tmp_path)
    with pytest.raises(BackupError, match="EXISTING_RECOVERY_KEY"):
        cli.recovery_key(path)
    key = cli.recovery_key(path, create=True)
    assert len(key) == 32 and cli.recovery_key(path) == key
    assert (path / "recovery.key").stat().st_mode & 0o777 == 0o600
    (path / "recovery.key").unlink()
    (path / "old.atbackup").write_bytes(b"prior encrypted archive")
    with pytest.raises(BackupError, match="EXISTING_RECOVERY_KEY"):
        cli.recovery_key(path, create=True)


def test_dump_omits_login_sessions_and_credentials_from_arguments(monkeypatch):
    run = Mock(return_value=DUMP)
    monkeypatch.setattr(cli, "bounded_output", run)
    assert cli.export_dump("docker", "validated-source") == DUMP
    command = run.call_args.args[0]
    assert command[:3] == ["docker", "exec", "validated-source"]
    assert "--exclude-table-data=public.admin_sessions" in command[-1]
    assert "--no-owner" in command[-1] and "--no-acl" in command[-1]
    assert 'PGPASSWORD="$POSTGRES_PASSWORD"' in command[-1]


def test_command_output_limit_and_safe_errors():
    with pytest.raises(BackupError, match="OUTPUT_LIMIT"):
        cli.bounded_output([sys.executable, "-c", "print('x'*100)"], limit=10)
    with pytest.raises(BackupError, match="COMMAND_FAILED"):
        cli.bounded_output([sys.executable, "-c", "raise SystemExit(1)"])


@pytest.mark.parametrize("fails", [False, True])
def test_restore_is_isolated_and_cleanup_targets_only_owned_container(monkeypatch, fails):
    commands = []

    def invoke(command, **kwargs):
        commands.append(command)
        return "c" * 12 if "ps" in command else ""

    counts = {
        "schema_revision": SCHEMA_REVISION,
        "superuser": False,
        "admin_sessions": 0,
        "catalog_hash_errors": 0,
        "history_hash_errors": 0,
        "chain_hash_errors": 0,
        "observation_events": 0,
    }
    monkeypatch.setattr(cli, "invoke", invoke)
    monkeypatch.setattr(
        cli, "bounded_output", Mock(side_effect=[b"", json.dumps(counts).encode(), b""])
    )
    seen = []

    def run(command, **kwargs):
        seen.append(command)
        return SimpleNamespace(returncode=1 if fails and "pg_restore" in command[-1] else 0)

    monkeypatch.setattr(cli.subprocess, "run", run)
    if fails:
        with pytest.raises(BackupError, match="RESTORE_CUSTOM_DUMP_FAILED"):
            cli.restore_drill("docker", "sha256:" + "a" * 64, DUMP)
    else:
        assert cli.restore_drill("docker", "sha256:" + "a" * 64, DUMP)["restore_verified"]
    start = next(c for c in commands if "run" in c)
    assert start[start.index("--network") + 1] == "none" and "--read-only" in start
    assert "--publish" not in start and "--volume" not in start
    restore = next(c for c in seen if "pg_restore" in c[-1])
    assert "--username=algotrade_restore" in restore[-1]
    assert "--single-transaction" in restore[-1] and "--exit-on-error" in restore[-1]
    assert commands[-1] == ["docker", "rm", "--force", "--volumes", "c" * 12]


@pytest.mark.parametrize("fails", [False, True])
def test_verify_latest_needs_no_source_database_and_preserves_receipt_on_failure(
    tmp_path,
    monkeypatch,
    fails,
):
    from scripts.bootstrap_local import private_write
    from scripts.google_drive import directory

    directory(tmp_path)
    path = cli.backup_directory(tmp_path)
    cli.recovery_key(path, create=True)
    ciphertext = encrypt_dump(DUMP, cli.recovery_key(path))
    receipt = {
        "file_id": "file1",
        "file_name": "algotrade-pg-backup-" + "a" * 32 + ".atbackup",
        "folder_id": "folder1",
        "postgres_image": "sha256:" + "a" * 64,
        "encrypted_bytes": len(ciphertext),
        "cipher_sha256": hashlib.sha256(ciphertext).hexdigest(),
    }
    private_write(path / "latest.json", json.dumps(receipt))
    before = (path / "latest.json").read_text()
    source = Mock(side_effect=AssertionError("No source database access permitted"))
    drive = SimpleNamespace(download=Mock(return_value=ciphertext), close=Mock())
    restore = Mock(
        side_effect=BackupError("RESTORE_FAILED") if fails else None,
        return_value={"restore_verified": True},
    )
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "bootstrap_lock", lambda root: nullcontext())
    monkeypatch.setattr(cli, "client_config", lambda path: {})
    monkeypatch.setattr(
        cli, "authorize", lambda *args, **kwargs: SimpleNamespace(token="synthetic")
    )
    monkeypatch.setattr(cli, "docker_binary", lambda: "docker")
    monkeypatch.setattr(cli, "local_engine", lambda executable: None)
    monkeypatch.setattr(cli, "local_database", source)
    monkeypatch.setattr(cli, "DriveBackup", lambda token: drive)
    monkeypatch.setattr(cli, "restore_drill", restore)
    monkeypatch.setattr(sys, "argv", ["backup_postgres", "verify-latest"])
    if fails:
        with pytest.raises(BackupError, match="RESTORE_FAILED"):
            cli.main()
        assert (path / "latest.json").read_text() == before
    else:
        assert cli.main() == 0
        assert restore.call_args.args[2] == DUMP
    source.assert_not_called()
    drive.close.assert_called_once()
