"""Explicit encrypted local PostgreSQL backup and network-isolated restore verification."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import selectors
import stat
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.app.database import SCHEMA_REVISION
from backend.app.storage.backup_crypto import MAX_DUMP, BackupError, decrypt_dump, encrypt_dump
from backend.app.storage.drive_backup import DriveBackup
from scripts.bootstrap_local import (
    ROOT,
    assignments,
    bootstrap_lock,
    docker_binary,
    invoke,
    local_engine,
    private_read,
    private_write,
    project_name,
)
from scripts.capture_local import local_container
from scripts.google_drive import (
    authorize,
    client_config,
    directory,
    quiet_oauth_logs,
    secure_json,
    storage_lock,
)


def backup_directory(root: Path) -> Path:
    path = root / ".local"
    if (
        path.is_symlink()
        or not path.is_dir()
        or path.stat().st_uid != os.getuid()
        or path.stat().st_mode & 0o022
    ):
        raise BackupError("BACKUP_UNSAFE_DIRECTORY")
    path = path / "backups"
    if path.is_symlink():
        raise BackupError("BACKUP_UNSAFE_DIRECTORY")
    path.mkdir(mode=0o700, exist_ok=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
        raise BackupError("BACKUP_UNSAFE_DIRECTORY")
    os.chmod(path, 0o700)
    return path


def recovery_key(path: Path, *, create: bool = False) -> bytes:
    target = path / "recovery.key"
    value = private_read(target)
    if value is None:
        if not create or (path / "latest.json").exists() or any(path.glob("*.atbackup*")):
            raise BackupError("BACKUP_EXISTING_RECOVERY_KEY_REQUIRED")
        value = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        private_write(target, value + "\n")
    if target.stat().st_mode & 0o077:
        raise BackupError("BACKUP_PRIVATE_KEY_PERMISSIONS_REQUIRED")
    try:
        key = base64.b64decode(value.strip(), altchars=b"-_", validate=True)
    except ValueError:
        raise BackupError("BACKUP_INVALID_RECOVERY_KEY") from None
    if len(key) != 32:
        raise BackupError("BACKUP_INVALID_RECOVERY_KEY")
    return key


def bounded_output(command: list[str], *, data: bytes | None = None, limit=MAX_DUMP, timeout=90):
    with subprocess.Popen(
        command,
        stdin=subprocess.PIPE if data else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            if data:
                if len(data) > 8192:
                    raise BackupError("BACKUP_QUERY_INPUT_LIMIT")
                process.stdin.write(data)
                process.stdin.close()
            result = bytearray()
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise BackupError("BACKUP_COMMAND_TIMEOUT")
                    if not selector.select(min(remaining, 1)):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65_536)
                    if not chunk:
                        break
                    result.extend(chunk)
                    if len(result) > limit:
                        raise BackupError("BACKUP_OUTPUT_LIMIT")
            if process.wait(timeout=max(0.1, deadline - time.monotonic())):
                raise BackupError("BACKUP_COMMAND_FAILED")
            return bytes(result)
        finally:
            if process.poll() is None:
                process.kill()  # Only the child command created above; never another service.
                process.wait(timeout=5)


def local_database(root: Path) -> tuple[str, str, str]:
    executable, _ = local_container(root)
    project = project_name(assignments(private_read(root / ".env")))
    container = invoke(
        [
            executable,
            "ps",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=db",
            "--format",
            "{{.ID}}",
        ]
    ).strip()
    if re.fullmatch(r"[0-9a-f]{12,64}", container) is None:
        raise BackupError("BACKUP_DATABASE_NOT_UNIQUE")
    workdir = invoke(
        [
            executable,
            "inspect",
            "--format",
            '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}',
            container,
        ]
    ).strip()
    image = invoke([executable, "inspect", "--format", "{{.Image}}", container]).strip()
    if workdir != str(root.resolve()) or re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise BackupError("BACKUP_DATABASE_PROJECT_MISMATCH")
    return executable, container, image


def export_dump(executable: str, container: str) -> bytes:
    command = (
        'export PGPASSWORD="$POSTGRES_PASSWORD"; '
        'export PGOPTIONS="-c statement_timeout=60000"; '
        'exec pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" '
        "--format=custom --no-owner --no-acl --no-password --lock-wait-timeout=5s "
        "--exclude-table-data=public.admin_sessions"
    )
    value = bounded_output([executable, "exec", container, "sh", "-c", command])
    if not value.startswith(b"PGDMP"):
        raise BackupError("BACKUP_CUSTOM_DUMP_REQUIRED")
    return value


def restore_drill(executable: str, image: str, dump: bytes) -> dict:
    if not dump.startswith(b"PGDMP") or len(dump) > MAX_DUMP:
        raise BackupError("RESTORE_INVALID_DUMP")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise BackupError("RESTORE_MATCHING_POSTGRES_IMAGE_REQUIRED")
    identity = uuid4().hex
    name = "algotrade-restore-" + identity
    environment = {**os.environ, "POSTGRES_PASSWORD": secrets.token_hex(32)}
    password = secrets.token_hex(32)
    try:
        invoke(
            [
                executable,
                "run",
                "--detach",
                "--pull=never",
                "--name",
                name,
                "--network",
                "none",
                "--label",
                "algotrade.restore-drill=" + identity,
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=32m",
                "--tmpfs",
                "/var/run/postgresql:rw,noexec,nosuid,size=16m",
                "--tmpfs",
                "/var/lib/postgresql/data:rw,noexec,nosuid,size=256m",
                "--memory",
                "512m",
                "--cpus",
                "1",
                "--pids-limit",
                "128",
                "--env",
                "POSTGRES_PASSWORD",
                image,
            ],
            environment=environment,
        )
        for _ in range(60):
            ready = subprocess.run(
                [executable, "exec", name, "pg_isready", "--host=127.0.0.1", "-U", "postgres"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise BackupError("RESTORE_DATABASE_NOT_READY")
        setup = (
            f"CREATE ROLE algotrade_restore LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"NOBYPASSRLS PASSWORD '{password}';\n"
            "CREATE DATABASE algotrade_restore OWNER algotrade_restore;\n"
        )
        bounded_output(
            [
                executable,
                "exec",
                "-i",
                name,
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
            ],
            data=setup.encode(),
            limit=1024,
        )
        base = [executable, "exec", "-i", name, "sh", "-c"]
        prefix = "IFS= read -r PGPASSWORD; export PGPASSWORD; exec "
        restored = subprocess.run(
            base
            + [
                prefix + "pg_restore --host=127.0.0.1 --username=algotrade_restore "
                "--dbname=algotrade_restore --no-owner --no-acl --exit-on-error "
                "--single-transaction"
            ],
            input=password.encode() + b"\n" + dump,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        if restored.returncode:
            raise BackupError("RESTORE_CUSTOM_DUMP_FAILED")
        query = (
            "SELECT json_build_object("
            + ",".join(
                [
                    "'schema_revision',(SELECT version_num FROM alembic_version)",
                    "'superuser',(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)",
                    *[
                        f"'{table}',(SELECT count(*) FROM {table})"
                        for table in (
                            "admin_sessions",
                            "instrument_snapshots",
                            "instruments",
                            "candle_imports",
                            "candles",
                            "option_chain_snapshots",
                            "option_chain_legs",
                            "capture_runs",
                            "observation_sessions",
                            "observation_events",
                        )
                    ],
                    "'catalog_hash_errors',(SELECT count(*) FROM instrument_snapshots "
                    "WHERE encode(sha256(raw_gzip),'hex')<>sha256)",
                    "'history_hash_errors',(SELECT count(*) FROM candle_imports "
                    "WHERE encode(sha256(canonical_payload),'hex')<>canonical_sha256)",
                    "'chain_hash_errors',(SELECT count(*) FROM option_chain_snapshots "
                    "WHERE encode(sha256(canonical_payload),'hex')<>canonical_sha256)",
                ]
            )
            + ");\n"
        )
        sql_command = base + [
            prefix + "psql -X -t -A -v ON_ERROR_STOP=1 "
            "--host=127.0.0.1 --username=algotrade_restore --dbname=algotrade_restore"
        ]
        result = json.loads(
            bounded_output(sql_command, data=(password + "\n" + query).encode(), limit=4096)
        )
        if (
            result["schema_revision"] != SCHEMA_REVISION
            or result["superuser"]
            or result["admin_sessions"]
            or any(
                result[k]
                for k in ("catalog_hash_errors", "history_hash_errors", "chain_hash_errors")
            )
        ):
            raise BackupError("RESTORE_SCHEMA_OR_INTEGRITY_FAILED")
        events = bounded_output(
            sql_command,
            data=(
                password + "\nSELECT json_build_object("
                "'payload',payload,'sha256',payload_sha256) FROM observation_events;\n"
            ).encode(),
        )
        checked = 0
        for line in events.splitlines():
            row = json.loads(line)
            canonical = json.dumps(
                row["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            if hashlib.sha256(canonical).hexdigest() != row["sha256"]:
                raise BackupError("RESTORE_EVENT_HASH_FAILED")
            checked += 1
        if checked != result["observation_events"]:
            raise BackupError("RESTORE_EVENT_COUNT_FAILED")
        return {
            **result,
            "event_hashes_verified": checked,
            "network": "none",
            "restore_verified": True,
        }
    finally:
        # Remove only this generated drill's labelled container and its temporary volumes.
        owned = invoke(
            [executable, "ps", "-aq", "--filter", "label=algotrade.restore-drill=" + identity]
        ).strip()
        if owned:
            if re.fullmatch(r"[0-9a-f]{12,64}", owned) is None:
                raise BackupError("RESTORE_CLEANUP_UNCONFIRMED")
            invoke([executable, "rm", "--force", "--volumes", owned])


def prune_verified_cache(path: Path, drive: DriveBackup, key: bytes) -> dict:
    removed, reclaimed = 0, 0
    for target in path.glob("algotrade-pg-backup-*.atbackup"):
        if removed >= 8:
            break
        if re.fullmatch(r"algotrade-pg-backup-[0-9a-f]{32}\.atbackup", target.name) is None:
            continue
        receipt = secure_json(path / (target.name + ".json"))
        if (
            not receipt
            or receipt.get("state") != "RESTORE_VERIFIED"
            or receipt.get("file_name") != target.name
        ):
            continue  # Never remove an unverified/unknown archive or recovery material.
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_nlink != 1
                or before.st_size > MAX_DUMP + 4096
            ):
                raise BackupError("BACKUP_UNSAFE_CACHE_FILE")
            local = stream.read(MAX_DUMP + 4097)
        remote = drive.download(receipt)
        decrypt_dump(remote, key)  # Cloud copy and recovery key must still work now.
        if hashlib.sha256(local).digest() != hashlib.sha256(remote).digest():
            raise BackupError("BACKUP_CACHE_CLOUD_MISMATCH")
        after = target.lstat()
        if (before.st_ino, before.st_dev, before.st_mtime_ns, before.st_size) != (
            after.st_ino,
            after.st_dev,
            after.st_mtime_ns,
            after.st_size,
        ):
            raise BackupError("BACKUP_CACHE_CHANGED")
        target.unlink()  # Only the exact app-owned ciphertext just verified against Drive.
        removed += 1
        reclaimed += len(local)
    return {"state": "LOCAL_CACHE_CHECKED", "files_removed": removed, "bytes_reclaimed": reclaimed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "verify-latest", "prune-local"))
    args = parser.parse_args()
    quiet_oauth_logs()
    google = directory(ROOT)
    with bootstrap_lock(ROOT), storage_lock(google):
        path = backup_directory(ROOT)
        key = recovery_key(path, create=args.action == "backup")
        credentials = authorize(
            google, client_config(google / "credentials.json"), interactive=False
        )
        if args.action == "backup":
            executable, container, image = local_database(ROOT)
        elif args.action == "verify-latest":
            executable = docker_binary()
            local_engine(executable)
        drive = DriveBackup(credentials.token)
        try:
            if args.action == "prune-local":
                print(json.dumps(prune_verified_cache(path, drive, key)))
                return 0
            if args.action == "backup":
                dump = export_dump(executable, container)
                value = encrypt_dump(dump, key)
                name = "algotrade-pg-backup-" + uuid4().hex + ".atbackup"
                # Cloud-first: ciphertext stays in bounded RAM, not a growing local cache.
                receipt = drive.upload(value, name)
                receipt["postgres_image"] = image
                private_write(path / (name + ".json"), json.dumps(receipt, indent=2) + "\n")
            else:
                receipt = secure_json(path / "latest.json")
                if not receipt:
                    raise BackupError("BACKUP_VERIFIED_RECEIPT_REQUIRED")
                image = receipt.get("postgres_image", "")
                if re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
                    raise BackupError("RESTORE_MATCHING_POSTGRES_IMAGE_REQUIRED")
            restored, manifest = decrypt_dump(drive.download(receipt), key)
            verified = restore_drill(executable, image, restored)
            receipt.update(
                {
                    "state": "RESTORE_VERIFIED",
                    "verified_at": datetime.now(UTC).isoformat(),
                    "manifest": manifest,
                    "restore": verified,
                    "live_enabled": False,
                }
            )
            filename = receipt.get("file_name", "")
            if re.fullmatch(r"algotrade-pg-backup-[0-9a-f]{32}\.atbackup", filename) is None:
                raise BackupError("BACKUP_INVALID_RECEIPT_NAME")
            encoded = json.dumps(receipt, indent=2) + "\n"
            private_write(path / (filename + ".json"), encoded)
            private_write(path / "latest.json", encoded)
            print(
                json.dumps(
                    {
                        "state": receipt["state"],
                        "encrypted_bytes": receipt["encrypted_bytes"],
                        "cipher_sha256": receipt["cipher_sha256"],
                        "restore": verified,
                        "live_enabled": False,
                    }
                )
            )
        finally:
            drive.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackupError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit("BACKUP_OPERATION_FAILED: sensitive details withheld") from None
