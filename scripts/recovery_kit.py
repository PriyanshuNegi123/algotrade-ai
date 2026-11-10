"""Explicit passphrase-protected recovery material; no plaintext secret export or live restore."""

import argparse
import getpass
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import MAX_ENCRYPTED, BackupError, decrypt_dump
from backend.app.storage.drive_backup import DriveBackup
from backend.app.storage.drive_recovery import DriveRecovery
from backend.app.storage.recovery_kit import MAX_KIT, clean_receipt, decrypt_kit, encrypt_kit
from scripts.backup_postgres import backup_directory, recovery_key, restore_drill
from scripts.bootstrap_local import ROOT, bootstrap_lock, docker_binary, local_engine, private_write
from scripts.google_drive import (
    authorize,
    client_config,
    directory,
    quiet_oauth_logs,
    secure_json,
    storage_lock,
)


def prompt_passphrase(*, dialog: bool, confirm: bool) -> str:
    def read(message: str) -> str:
        if dialog:
            # No secret enters argv/AppleScript source. The hidden answer is captured only in RAM.
            script = (
                "activate\ntext returned of (display dialog "
                + json.dumps(message)
                + (
                    ' with title "AlgoTrade AI Recovery" default answer "" '
                    'with hidden answer buttons {"Cancel", "Continue"} '
                    'default button "Continue")'
                )
            )
            try:
                response = subprocess.run(
                    ["/usr/bin/osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                raise BackupError("RECOVERY_LOCAL_PROMPT_TIMED_OUT") from None
            if response.returncode or len(response.stdout) > 4097:
                raise BackupError("RECOVERY_LOCAL_PROMPT_CANCELLED")
            return response.stdout.removesuffix("\n")
        if not sys.stdin.isatty():
            raise BackupError("RECOVERY_LOCAL_INTERACTIVE_PROMPT_REQUIRED")
        return getpass.getpass(message + ": ")

    print("RECOVERY_PASSPHRASE_WAITING: enter it only in the local hidden prompt.", flush=True)
    message = (
        "Create a NEW AlgoTrade recovery passphrase (16+ characters). "
        "Keep it separately; do not use your Google password."
        if confirm
        else "Enter the SAME recovery passphrase used when creating this kit."
    )
    value = read(message)
    if not 16 <= len(value) <= 1024:
        raise BackupError("RECOVERY_PASSPHRASE_LENGTH_REQUIRED")
    if confirm and not secrets.compare_digest(
        value.encode(), read("Confirm the recovery passphrase").encode()
    ):
        raise BackupError("RECOVERY_PASSPHRASE_CONFIRMATION_MISMATCH")
    return value


def read_ciphertext(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > limit:
            raise BackupError("RECOVERY_INPUT_FILE_INVALID")
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise BackupError("RECOVERY_INPUT_FILE_TOO_LARGE")
    return value


def verify_dump(dump: bytes, receipt: dict) -> dict:
    executable = docker_binary()
    local_engine(executable)
    return restore_drill(executable, receipt["postgres_image"], dump)


def verify_cloud_material(value: bytes, passphrase: str, drive: DriveBackup) -> tuple[bytes, dict]:
    key, receipt = decrypt_kit(value, passphrase)
    dump, _ = decrypt_dump(drive.download(receipt), key)
    restored = verify_dump(dump, receipt)
    if not restored.get("restore_verified"):
        raise BackupError("RECOVERY_DATABASE_RESTORE_NOT_VERIFIED")
    return key, restored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("create", "verify-cloud", "verify-pending", "recover-local")
    )
    parser.add_argument("--dialog", action="store_true")
    parser.add_argument("--kit-file", type=Path)
    parser.add_argument("--archive-file", type=Path)
    args = parser.parse_args()
    quiet_oauth_logs()
    if args.action == "recover-local":
        if args.kit_file is None or args.archive_file is None:
            raise BackupError("RECOVERY_DOWNLOADED_FILES_REQUIRED")
        value = read_ciphertext(args.kit_file, MAX_KIT)
        archive = read_ciphertext(args.archive_file, MAX_ENCRYPTED)
        password = prompt_passphrase(dialog=args.dialog, confirm=False)
        key, receipt = decrypt_kit(value, password)
        dump, _ = decrypt_dump(archive, key)  # Also supports newer same-key authenticated backups.
        restored = verify_dump(dump, receipt)
        if not restored.get("restore_verified"):
            raise BackupError("RECOVERY_DATABASE_RESTORE_NOT_VERIFIED")
        print(
            json.dumps(
                {
                    "state": "LOCAL_RECOVERY_RESTORE_VERIFIED",
                    "restore": restored,
                    "original_key_file_used": False,
                    "live_enabled": False,
                }
            )
        )
        return 0
    if args.kit_file is not None or args.archive_file is not None:
        raise BackupError("RECOVERY_FILE_ARGUMENTS_REQUIRE_LOCAL_ACTION")
    google = directory(ROOT)
    config = client_config(google / "credentials.json")
    password = prompt_passphrase(dialog=args.dialog, confirm=args.action == "create")
    with bootstrap_lock(ROOT), storage_lock(google):
        path = backup_directory(ROOT)
        credentials = authorize(google, config, interactive=False)
        kits, backups = DriveRecovery(credentials.token), DriveBackup(credentials.token)
        try:
            if args.action == "create":
                original = recovery_key(path)  # Existing key only; never create/replace it here.
                receipt = secure_json(path / "latest.json")
                if not receipt:
                    raise BackupError("RECOVERY_VERIFIED_BACKUP_RECEIPT_REQUIRED")
                value = encrypt_kit(original, clean_receipt(receipt), password)
                kit_receipt = kits.upload(value)
                private_write(path / "recovery-kit-pending.json", json.dumps(kit_receipt) + "\n")
            else:
                name = (
                    "recovery-kit-pending.json"
                    if args.action == "verify-pending"
                    else "recovery-kit.json"
                )
                kit_receipt = secure_json(path / name)
                if not kit_receipt:
                    raise BackupError("RECOVERY_KIT_RECEIPT_REQUIRED")
            downloaded = kits.download(kit_receipt)
            recovered, restored = verify_cloud_material(downloaded, password, backups)
            if args.action == "create" and not secrets.compare_digest(original, recovered):
                raise BackupError("RECOVERY_DATA_KEY_MISMATCH")
            kit_receipt.update(
                {
                    "state": "RECOVERY_VERIFIED",
                    "verified_at": datetime.now(UTC).isoformat(),
                    "protected_key_sha256": hashlib.sha256(recovered).hexdigest(),
                    "schema_revision": SCHEMA_REVISION,
                    "restore": restored,
                    "original_key_required_for_verification": False,
                }
            )
            private_write(path / "recovery-kit.json", json.dumps(kit_receipt, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        "state": "RECOVERY_VERIFIED",
                        "encrypted_bytes": kit_receipt["encrypted_bytes"],
                        "original_key_required_for_verification": False,
                        "passphrase_saved": False,
                        "restore": restored,
                        "live_enabled": False,
                    }
                )
            )
        finally:
            kits.close()
            backups.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupError as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        raise SystemExit("RECOVERY_OPERATION_CANCELLED") from None
    except Exception:
        raise SystemExit("RECOVERY_OPERATION_FAILED: sensitive details withheld") from None
