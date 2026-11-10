import base64
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import BackupError, encrypt_dump
from backend.app.storage.drive_recovery import DriveRecovery
from backend.app.storage.recovery_kit import MAGIC, MAX_KIT, decrypt_kit, encrypt_kit
from scripts import recovery_kit as cli

KEY = bytes(range(32))
PASSWORD = "synthetic recovery phrase only"
DUMP = b"PGDMPsynthetic-dump"


@pytest.fixture
def receipt():
    return {
        "state": "RESTORE_VERIFIED",
        "file_id": "backup1",
        "folder_id": "folder1",
        "cipher_sha256": "a" * 64,
        "encrypted_bytes": 1000,
        "file_name": "algotrade-pg-backup-" + "b" * 32 + ".atbackup",
        "postgres_image": "sha256:" + "c" * 64,
        "verified_at": datetime.now(UTC).isoformat(),
        "manifest": {
            "format": "POSTGRES_CUSTOM_DUMP",
            "schema_revision": SCHEMA_REVISION,
            "created_at": datetime.now(UTC).isoformat(),
            "admin_sessions_excluded": True,
        },
        "restore": {
            "restore_verified": True,
            "network": "none",
            "superuser": False,
            "admin_sessions": 0,
        },
    }


def test_passphrase_wrapping_roundtrip_excludes_credentials_and_randomizes(receipt):
    receipt["access_token"] = "synthetic-private-token"
    receipt["manifest"]["client_secret"] = "synthetic-private-client"
    first, second = encrypt_kit(KEY, receipt, PASSWORD), encrypt_kit(KEY, receipt, PASSWORD)
    assert first != second and first.startswith(MAGIC)
    assert KEY not in first and base64.b64encode(KEY) not in first
    assert PASSWORD.encode() not in first and b"synthetic-private-token" not in first
    recovered, clean = decrypt_kit(first, PASSWORD)
    assert recovered == KEY and "access_token" not in clean
    assert "client_secret" not in clean["manifest"]


@pytest.mark.parametrize("kind", ["password", "header", "salt", "nonce", "ciphertext", "truncate"])
def test_wrong_password_and_tampering_fail_closed(receipt, kind):
    value = bytearray(encrypt_kit(KEY, receipt, PASSWORD))
    password = PASSWORD
    if kind == "password":
        password = "different synthetic passphrase"
    elif kind == "truncate":
        value = value[:-1]
    else:
        value[
            {"header": 0, "salt": len(MAGIC), "nonce": len(MAGIC) + 16, "ciphertext": -1}[kind]
        ] ^= 1
    with pytest.raises(BackupError):
        decrypt_kit(bytes(value), password)


@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_passphrase_bounds(receipt, password):
    with pytest.raises(BackupError, match="LENGTH"):
        encrypt_kit(KEY, receipt, password)


def test_no_unverified_receipt_or_invalid_material(receipt):
    receipt["state"] = "UPLOADED_NOT_VERIFIED"
    with pytest.raises(BackupError, match="VERIFIED_BACKUP"):
        encrypt_kit(KEY, receipt, PASSWORD)
    with pytest.raises(BackupError):
        decrypt_kit(b"not encrypted", PASSWORD)
    with pytest.raises(BackupError):
        decrypt_kit(MAGIC + b"x" * MAX_KIT, PASSWORD)


def test_hidden_dialog_confirmation_keeps_secret_out_of_argv_and_output(monkeypatch, capsys):
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout=PASSWORD + "\n"))
    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.prompt_passphrase(dialog=True, confirm=True) == PASSWORD
    assert run.call_count == 2
    assert all(PASSWORD not in str(c.args) for c in run.call_args_list)
    assert PASSWORD not in capsys.readouterr().out
    assert "with hidden answer" in run.call_args.args[0][-1]


def test_dialog_mismatch_and_cancel_never_return_secret(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout=PASSWORD + "\n"),
                SimpleNamespace(returncode=0, stdout="different response\n"),
            ]
        ),
    )
    with pytest.raises(BackupError, match="MISMATCH"):
        cli.prompt_passphrase(dialog=True, confirm=True)
    monkeypatch.setattr(
        cli.subprocess, "run", Mock(return_value=SimpleNamespace(returncode=1, stdout=""))
    )
    with pytest.raises(BackupError, match="CANCELLED"):
        cli.prompt_passphrase(dialog=True, confirm=False)


def test_recovered_key_is_sufficient_for_real_dump_verifier(receipt, monkeypatch):
    kit = encrypt_kit(KEY, receipt, PASSWORD)
    encrypted = encrypt_dump(DUMP, KEY)
    drive = SimpleNamespace(download=Mock(return_value=encrypted))
    monkeypatch.setattr(
        cli, "recovery_key", Mock(side_effect=AssertionError("No original key access"))
    )
    verify = Mock(return_value={"restore_verified": True})
    monkeypatch.setattr(cli, "verify_dump", verify)
    key, restored = cli.verify_cloud_material(kit, PASSWORD, drive)
    assert key == KEY and restored["restore_verified"]
    assert verify.call_args.args[0] == DUMP


def test_encrypted_kit_cloud_roundtrip_only_gets_and_creates(receipt, monkeypatch):
    from email.parser import BytesParser

    value = encrypt_kit(KEY, receipt, PASSWORD)
    digest = hashlib.sha256(value).hexdigest()
    methods = []

    def handler(request):
        methods.append(request.method)
        assert KEY not in request.content and PASSWORD.encode() not in request.content
        if request.method == "POST":
            message = BytesParser().parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
                + request.content
            )
            assert message.get_payload()[1].get_payload(decode=True) == value
            return httpx.Response(200, json={"id": "kit1"})
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=value)
        return httpx.Response(
            200,
            json={
                "parents": ["folder1"],
                "mimeType": "application/octet-stream",
                "size": str(len(value)),
                "appProperties": {"algotrade_recovery_kit": "v1", "cipher_sha256": digest},
                "sha256Checksum": digest,
                "capabilities": {"canDownload": True},
            },
        )

    drive = DriveRecovery("synthetic-access", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(drive, "archive_folder", lambda: ("folder1", False))
    try:
        result = drive.upload(value)
        assert drive.download(result) == value
    finally:
        drive.close()
    assert set(methods) == {"POST", "GET"}


def test_input_file_rejects_symlinks_and_excessive_size(tmp_path):
    target = tmp_path / "kit"
    target.write_bytes(b"x" * 20)
    with pytest.raises(BackupError, match="INVALID"):
        cli.read_ciphertext(target, 10)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(OSError):
        cli.read_ciphertext(link, 100)


def test_downloaded_recovery_needs_no_original_key_or_google_credentials(
    tmp_path, monkeypatch, receipt, capsys
):
    kit, archive = tmp_path / "kit.atrecovery", tmp_path / "backup.atbackup"
    kit.write_bytes(encrypt_kit(KEY, receipt, PASSWORD))
    archive.write_bytes(encrypt_dump(DUMP, KEY))
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["recovery-kit", "recover-local", "--kit-file", str(kit), "--archive-file", str(archive)],
    )
    monkeypatch.setattr(cli, "prompt_passphrase", lambda **kwargs: PASSWORD)
    for name in ("recovery_key", "authorize", "client_config", "directory"):
        monkeypatch.setattr(
            cli, name, Mock(side_effect=AssertionError("original secret consulted"))
        )
    verify = Mock(return_value={"restore_verified": True})
    monkeypatch.setattr(cli, "verify_dump", verify)
    assert cli.main() == 0
    verify.assert_called_once()
    assert verify.call_args.args[0] == DUMP
    output = capsys.readouterr().out
    assert "LOCAL_RECOVERY_RESTORE_VERIFIED" in output
    assert PASSWORD not in output and base64.b64encode(KEY).decode() not in output


def test_native_prompt_timeout_returns_only_safe_code(monkeypatch):
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        Mock(side_effect=cli.subprocess.TimeoutExpired("synthetic", 300, output=PASSWORD)),
    )
    with pytest.raises(BackupError, match="^RECOVERY_LOCAL_PROMPT_TIMED_OUT$"):
        cli.prompt_passphrase(dialog=True, confirm=True)
