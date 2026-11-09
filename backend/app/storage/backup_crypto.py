"""Versioned authenticated encryption for bounded PostgreSQL custom dumps."""

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.app.database import SCHEMA_REVISION

MAGIC = b"ALGOTRADE-PG-BACKUP\x01"
MAX_DUMP = 32 * 1024 * 1024
MAX_ENCRYPTED = MAX_DUMP + 4096


class BackupError(Exception):
    """Safe fixed backup error codes."""


def encrypted_envelope(value: bytes) -> None:
    if not value.startswith(MAGIC) or not len(MAGIC) + 28 < len(value) <= MAX_ENCRYPTED:
        raise BackupError("BACKUP_ENCRYPTED_ENVELOPE_REQUIRED")


def encrypt_dump(dump: bytes, key: bytes) -> bytes:
    if len(key) != 32 or not dump.startswith(b"PGDMP") or not 5 < len(dump) <= MAX_DUMP:
        raise BackupError("BACKUP_INVALID_KEY_OR_DUMP")
    manifest = {
        "format": "POSTGRES_CUSTOM_DUMP",
        "schema_revision": SCHEMA_REVISION,
        "created_at": datetime.now(UTC).isoformat(),
        "dump_sha256": hashlib.sha256(dump).hexdigest(),
        "bytes": len(dump),
        "admin_sessions_excluded": True,
    }
    plaintext = json.dumps(manifest, sort_keys=True).encode() + b"\n" + dump
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def decrypt_dump(value: bytes, key: bytes) -> tuple[bytes, dict[str, Any]]:
    encrypted_envelope(value)
    if len(key) != 32:
        raise BackupError("BACKUP_INVALID_RECOVERY_KEY")
    nonce = value[len(MAGIC) : len(MAGIC) + 12]
    try:
        plaintext = AESGCM(key).decrypt(nonce, value[len(MAGIC) + 12 :], MAGIC)
        header, dump = plaintext.split(b"\n", 1)
        if len(header) > 2048:
            raise ValueError
        manifest = json.loads(header)
        if (
            not isinstance(manifest, dict)
            or manifest.get("format") != "POSTGRES_CUSTOM_DUMP"
            or manifest.get("schema_revision") != SCHEMA_REVISION
            or manifest.get("admin_sessions_excluded") is not True
            or manifest.get("bytes") != len(dump)
            or not 5 < len(dump) <= MAX_DUMP
            or not dump.startswith(b"PGDMP")
            or manifest.get("dump_sha256") != hashlib.sha256(dump).hexdigest()
        ):
            raise ValueError
    except (InvalidTag, ValueError, TypeError):
        raise BackupError("BACKUP_AUTHENTICATION_OR_MANIFEST_FAILED") from None
    return dump, manifest
