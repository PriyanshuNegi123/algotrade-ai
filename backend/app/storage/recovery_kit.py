"""Passphrase-wrapped data key/receipt; fixed bounded Argon2id and authenticated encryption."""

import base64
import json
import re
import secrets
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import MAX_ENCRYPTED, BackupError
from backend.app.storage.google_drive import file_id

MAGIC = b"ALGOTRADE-RECOVERY-KIT\x01"
MAX_KIT = 65_536


def envelope(value: bytes) -> None:
    if not value.startswith(MAGIC) or not len(MAGIC) + 44 < len(value) <= MAX_KIT:
        raise BackupError("RECOVERY_KIT_ENCRYPTED_FORMAT_REQUIRED")


def clean_receipt(value: dict[str, Any]) -> dict[str, Any]:
    try:
        manifest, restored = value["manifest"], value["restore"]
        if (
            value["state"] != "RESTORE_VERIFIED"
            or restored["restore_verified"] is not True
            or restored["superuser"] is not False
            or restored["admin_sessions"] != 0
            or restored["network"] != "none"
            or manifest["schema_revision"] != SCHEMA_REVISION
            or manifest["format"] != "POSTGRES_CUSTOM_DUMP"
            or manifest["admin_sessions_excluded"] is not True
            or re.fullmatch(r"[0-9a-f]{64}", value["cipher_sha256"]) is None
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value["postgres_image"]) is None
            or re.fullmatch(r"algotrade-pg-backup-[0-9a-f]{32}\.atbackup", value["file_name"])
            is None
            or not isinstance(value["encrypted_bytes"], int)
            or not 0 < value["encrypted_bytes"] <= MAX_ENCRYPTED
            or datetime.fromisoformat(manifest["created_at"]).tzinfo is None
            or datetime.fromisoformat(value["verified_at"]).tzinfo is None
        ):
            raise ValueError
        result = {
            name: value[name]
            for name in (
                "state",
                "cipher_sha256",
                "postgres_image",
                "file_name",
                "encrypted_bytes",
                "verified_at",
            )
        }
        result.update(file_id=file_id(value["file_id"]), folder_id=file_id(value["folder_id"]))
        result["manifest"] = {
            name: manifest[name]
            for name in (
                "format",
                "schema_revision",
                "created_at",
                "admin_sessions_excluded",
            )
        }
        result["restore"] = {
            name: restored[name]
            for name in (
                "restore_verified",
                "superuser",
                "admin_sessions",
                "network",
            )
        }
        return result
    except (KeyError, TypeError, ValueError):
        raise BackupError("RECOVERY_VERIFIED_BACKUP_RECEIPT_REQUIRED") from None


def wrapping_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or not 16 <= len(passphrase) <= 1024:
        raise BackupError("RECOVERY_PASSPHRASE_LENGTH_REQUIRED")
    # Version 1 fixes parameters; an untrusted header cannot request arbitrary KDF resources.
    return Argon2id(salt=salt, length=32, iterations=3, lanes=4, memory_cost=64 * 1024).derive(
        passphrase.encode("utf-8")
    )


def encrypt_kit(key: bytes, receipt: dict[str, Any], passphrase: str) -> bytes:
    if len(key) != 32:
        raise BackupError("RECOVERY_DATA_KEY_INVALID")
    body = json.dumps(
        {
            "kind": "ALGOTRADE_RECOVERY_MATERIAL",
            "recovery_key": base64.b64encode(key).decode(),
            "backup": clean_receipt(receipt),
        },
        sort_keys=True,
    ).encode()
    if len(body) > MAX_KIT - 256:
        raise BackupError("RECOVERY_KIT_SIZE_LIMIT")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    ciphertext = AESGCM(wrapping_key(passphrase, salt)).encrypt(nonce, body, MAGIC + salt)
    return MAGIC + salt + nonce + ciphertext


def decrypt_kit(value: bytes, passphrase: str) -> tuple[bytes, dict[str, Any]]:
    envelope(value)
    salt = value[len(MAGIC) : len(MAGIC) + 16]
    nonce = value[len(MAGIC) + 16 : len(MAGIC) + 28]
    try:
        decoded = AESGCM(wrapping_key(passphrase, salt)).decrypt(
            nonce,
            value[len(MAGIC) + 28 :],
            MAGIC + salt,
        )
        material = json.loads(decoded)
        if material["kind"] != "ALGOTRADE_RECOVERY_MATERIAL":
            raise ValueError
        key = base64.b64decode(material["recovery_key"], validate=True)
        if len(key) != 32:
            raise ValueError
        return key, clean_receipt(material["backup"])
    except (InvalidTag, ValueError, KeyError, TypeError):
        raise BackupError("RECOVERY_KIT_AUTHENTICATION_FAILED") from None
