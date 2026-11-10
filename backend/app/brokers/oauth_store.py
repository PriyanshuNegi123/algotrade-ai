"""Opt-in local OAuth token vault. No routes, broker requests, backup upload or activation."""

import fcntl
import json
import os
import re
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr

from backend.app.brokers.oauth import (
    OAuthApp,
    OAuthError,
    OAuthToken,
    app_digest,
    aware,
    daily_cutoff,
    unique_object,
    utc_now,
)

MAGIC = b"ALGOTRADE-OAUTH-VAULT\x01"
MAX_ENCRYPTED = 16_384
KEY_FILE = "vault.key"
TOKEN_FILE = "token.enc"
LOCK_FILE = "vault.lock"


class OAuthStoreError(Exception):
    """Fixed reason codes; never include a path, token, key or decrypted payload."""


def private_file(info: os.stat_result) -> None:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise OAuthStoreError("OAUTH_VAULT_UNSAFE_FILE")


def read_file(directory: int, name: str, limit: int) -> bytes | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        private_file(info)
        if info.st_size > limit:
            raise OAuthStoreError("OAUTH_VAULT_SIZE_LIMIT")
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise OAuthStoreError("OAUTH_VAULT_SIZE_LIMIT")
    return value


def validate_token(token: OAuthToken, now: datetime, *, allow_expired: bool = False) -> None:
    raw = token.access_token.get_secret_value()
    try:
        requested, received, expiry = map(
            aware, (token.requested_at, token.received_at, token.expires_at)
        )
    except OAuthError:
        raise OAuthStoreError("OAUTH_VAULT_INVALID_METADATA") from None
    if (
        not 1 <= len(raw) <= 8192
        or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", raw) is None
        or received < requested
        or received > now
        or expiry <= received
        or expiry > daily_cutoff(requested)
    ):
        raise OAuthStoreError("OAUTH_VAULT_INVALID_METADATA")
    if not allow_expired and expiry <= now:
        raise OAuthStoreError("OAUTH_VAULT_TOKEN_EXPIRED")


class OAuthTokenStore:
    def __init__(self, directory: Path, *, clock: Callable[[], datetime] = utc_now):
        # This path is trusted service configuration, never an HTTP/request argument.
        self._directory, self._clock = directory.absolute(), clock

    @contextmanager
    def _open(self, *, create: bool) -> Iterator[int]:
        descriptor = None
        try:
            if any(path.is_symlink() for path in (self._directory, *self._directory.parents)):
                raise OAuthStoreError("OAUTH_VAULT_UNSAFE_DIRECTORY")
            if create:
                try:
                    self._directory.mkdir(mode=0o700)
                except FileExistsError:
                    pass
            if not self._directory.exists():
                raise OAuthStoreError("OAUTH_VAULT_NOT_INITIALIZED")
            descriptor = os.open(self._directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise OAuthStoreError("OAUTH_VAULT_UNSAFE_DIRECTORY")
            yield descriptor
        except (OSError, ValueError):
            raise OAuthStoreError("OAUTH_VAULT_FILESYSTEM_UNAVAILABLE") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @contextmanager
    def _lock(self, directory: int, *, create: bool) -> Iterator[None]:
        try:
            descriptor = os.open(
                LOCK_FILE,
                os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | (os.O_CREAT if create else 0),
                0o600,
                dir_fd=directory,
            )
        except FileNotFoundError:
            raise OAuthStoreError("OAUTH_VAULT_NOT_INITIALIZED") from None
        try:
            private_file(os.fstat(descriptor))
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OAuthStoreError("OAUTH_VAULT_BUSY") from None
            yield
        finally:
            os.close(descriptor)

    def _key(self, directory: int, *, create: bool) -> bytes:
        key = read_file(directory, KEY_FILE, 32)
        if key is not None:
            if len(key) != 32:
                raise OAuthStoreError("OAUTH_VAULT_KEY_INVALID")
            return key
        if not create or any(name != LOCK_FILE for name in os.listdir(directory)):
            raise OAuthStoreError("OAUTH_VAULT_KEY_REQUIRED")
        key = secrets.token_bytes(32)
        descriptor = os.open(
            KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)
        return key

    def _decode(self, value: bytes, key: bytes, app: OAuthApp) -> OAuthToken:
        if not value.startswith(MAGIC) or not len(MAGIC) + 28 < len(value) <= MAX_ENCRYPTED:
            raise OAuthStoreError("OAUTH_VAULT_ENVELOPE_INVALID")
        try:
            body = AESGCM(key).decrypt(
                value[len(MAGIC) : len(MAGIC) + 12],
                value[len(MAGIC) + 12 :],
                MAGIC + app_digest(app).encode(),
            )
            data = json.loads(body, object_pairs_hook=unique_object)
            if set(data) != {"access_token", "requested_at", "received_at", "expires_at"}:
                raise ValueError
            if not isinstance(data["access_token"], str):
                raise ValueError
            return OAuthToken(
                SecretStr(data["access_token"]),
                datetime.fromisoformat(data["requested_at"]),
                datetime.fromisoformat(data["received_at"]),
                datetime.fromisoformat(data["expires_at"]),
            )
        except (InvalidTag, ValueError, TypeError, KeyError, RecursionError):
            raise OAuthStoreError("OAUTH_VAULT_AUTHENTICATION_FAILED") from None

    def _write(self, directory: int, ciphertext: bytes) -> None:
        temporary = ".token-" + secrets.token_hex(16) + ".tmp"
        created = False
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory,
            )
            created = True
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(ciphertext)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, TOKEN_FILE, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            if created:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass

    def prepare(self, app: OAuthApp) -> None:
        """Explicit authenticated start may prepare storage before asking for broker consent."""
        now = aware(self._clock())
        with self._open(create=True) as directory, self._lock(directory, create=True):
            key = self._key(directory, create=True)
            previous = read_file(directory, TOKEN_FILE, MAX_ENCRYPTED)
            if previous is not None:
                validate_token(self._decode(previous, key, app), now, allow_expired=True)

    def save(self, app: OAuthApp, token: OAuthToken) -> None:
        now = aware(self._clock())
        validate_token(token, now)  # Invalid input cannot initialize a key or directory.
        with self._open(create=True) as directory, self._lock(directory, create=True):
            key = self._key(directory, create=True)
            previous = read_file(directory, TOKEN_FILE, MAX_ENCRYPTED)
            if previous is not None:
                old = self._decode(previous, key, app)
                validate_token(old, now, allow_expired=True)
                if token.requested_at < old.requested_at:
                    raise OAuthStoreError("OAUTH_VAULT_OLDER_TOKEN_REJECTED")
            body = json.dumps(
                {
                    "access_token": token.access_token.get_secret_value(),
                    "requested_at": token.requested_at.isoformat(),
                    "received_at": token.received_at.isoformat(),
                    "expires_at": token.expires_at.isoformat(),
                }
            ).encode()
            nonce = secrets.token_bytes(12)
            ciphertext = (
                MAGIC + nonce + AESGCM(key).encrypt(nonce, body, MAGIC + app_digest(app).encode())
            )
            if len(ciphertext) > MAX_ENCRYPTED:
                raise OAuthStoreError("OAUTH_VAULT_SIZE_LIMIT")
            self._write(directory, ciphertext)

    def load(self, app: OAuthApp) -> OAuthToken:
        now = aware(self._clock())
        with self._open(create=False) as directory, self._lock(directory, create=False):
            key = self._key(directory, create=False)
            ciphertext = read_file(directory, TOKEN_FILE, MAX_ENCRYPTED)
            if ciphertext is None:
                raise OAuthStoreError("OAUTH_VAULT_NOT_INITIALIZED")
            token = self._decode(ciphertext, key, app)
            validate_token(token, now)
            return token

    def status(self, app: OAuthApp) -> dict[str, object]:
        try:
            token = self.load(app)
            return {
                "state": "STORED_UNVERIFIED",
                "expires_at": token.expires_at.isoformat(),
                "broker_access_verified": False,
                "live_enabled": False,
            }
        except (OAuthStoreError, OAuthError) as error:
            return {"state": str(error), "broker_access_verified": False, "live_enabled": False}
