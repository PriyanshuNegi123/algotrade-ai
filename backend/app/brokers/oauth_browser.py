"""Ephemeral browser binding for OAuth; caller authenticates the session on each operation."""

import asyncio
import hashlib
import re
import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from pydantic import SecretStr

from backend.app.brokers.oauth import (
    AuthorizationRequest,
    OAuthApp,
    OAuthError,
    OAuthStates,
    OAuthToken,
    UpstoxOAuth,
    app_digest,
    utc_now,
)


@dataclass(frozen=True)
class BrowserBinding:
    session_digest: str = field(repr=False)
    app_digest: str = field(repr=False)
    nonce_digest: str = field(repr=False)
    expires_at: datetime


class OAuthBrowserFlows:
    def __init__(self) -> None:
        self._states = OAuthStates()
        self._bindings: dict[str, BrowserBinding] = {}
        self._current: dict[str, tuple[str, datetime]] = {}
        self._lock = threading.Lock()

    def begin(
        self,
        app: OAuthApp,
        session_digest: str,
        session_expires_at: datetime,
        *,
        storage_context: str,
    ) -> tuple[AuthorizationRequest, SecretStr, SecretStr]:
        now = utc_now()
        nonce = secrets.token_urlsafe(32)
        with self._lock:
            self._current = {key: value for key, value in self._current.items() if value[1] > now}
            if session_digest not in self._current and len(self._current) >= 32:
                raise OAuthError("OAUTH_PENDING_LIMIT")
            authorization = self._states.begin(app, session_digest, session_expires_at, now=now)
            state = parse_qs(urlsplit(authorization.url.get_secret_value()).query)["state"][0]
            self._bindings = {
                key: item
                for key, item in self._bindings.items()
                if item.expires_at > now and item.session_digest != session_digest
            }
            self._bindings[hashlib.sha256(state.encode()).hexdigest()] = BrowserBinding(
                session_digest,
                self._configuration_digest(app, storage_context),
                hashlib.sha256(nonce.encode()).hexdigest(),
                authorization.expires_at,
            )
            self._current[session_digest] = (
                hashlib.sha256(state.encode()).hexdigest(),
                authorization.expires_at,
            )
        return authorization, SecretStr(state), SecretStr(nonce)

    @staticmethod
    def _configuration_digest(app: OAuthApp, storage_context: str) -> str:
        return hashlib.sha256((app_digest(app) + "\n" + storage_context).encode()).hexdigest()

    @contextmanager
    def finalize(self, session_digest: str, state: SecretStr) -> Iterator[None]:
        identity = hashlib.sha256(state.get_secret_value().encode()).hexdigest()
        with self._lock:
            expected = self._current.get(session_digest)
            if expected is None or expected[0] != identity or expected[1] <= utc_now():
                raise OAuthError("OAUTH_STATE_SUPERSEDED")
            try:
                yield
            finally:
                self._current.pop(session_digest, None)

    def discard_consumed(self, session_digest: str, state: SecretStr) -> None:
        identity = hashlib.sha256(state.get_secret_value().encode()).hexdigest()
        with self._lock:
            current = self._current.get(session_digest)
            if identity not in self._bindings and current is not None and current[0] == identity:
                self._current.pop(session_digest, None)

    async def finish(
        self,
        app: OAuthApp,
        client: UpstoxOAuth,
        session_digest: str,
        state: SecretStr,
        nonce: SecretStr,
        code: SecretStr | None,
        *,
        denied: bool,
        storage_context: str,
    ) -> OAuthToken:
        await asyncio.to_thread(self._claim, app, session_digest, state, nonce, storage_context)
        raw_state = state.get_secret_value()
        if denied:
            self._states.consume(app, raw_state, session_digest)
            raise OAuthError("OAUTH_AUTHORIZATION_DENIED")
        return await client.complete(
            app, self._states, raw_state, session_digest, code or SecretStr("")
        )

    def _claim(
        self,
        app: OAuthApp,
        session_digest: str,
        state: SecretStr,
        nonce: SecretStr,
        storage_context: str,
    ) -> None:
        raw_state, raw_nonce = state.get_secret_value(), nonce.get_secret_value()
        if any(
            re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None for value in (raw_state, raw_nonce)
        ):
            raise OAuthError("OAUTH_BROWSER_BINDING_INVALID")
        identity = hashlib.sha256(raw_state.encode()).hexdigest()
        with self._lock:
            binding = self._bindings.get(identity)
            if binding is None:
                raise OAuthError("OAUTH_BROWSER_BINDING_INVALID")
            if binding.expires_at <= utc_now():
                del self._bindings[identity]
                raise OAuthError("OAUTH_BROWSER_BINDING_INVALID")
            if not secrets.compare_digest(
                binding.session_digest, session_digest
            ) or not secrets.compare_digest(
                binding.nonce_digest, hashlib.sha256(raw_nonce.encode()).hexdigest()
            ):
                raise OAuthError("OAUTH_BROWSER_BINDING_INVALID")
            del self._bindings[identity]
            if not secrets.compare_digest(
                binding.app_digest, self._configuration_digest(app, storage_context)
            ):
                raise OAuthError("OAUTH_APP_CHANGED")


def callback_configuration(app: OAuthApp, allowed_origins: list[str]) -> tuple[str, str]:
    url = urlsplit(app.redirect_uri)
    host = url.hostname or ""
    host = "[" + host + "]" if ":" in host else host
    port = url.port
    authority = host + (
        ":" + str(port)
        if port is not None and port != {"http": 80, "https": 443}[url.scheme]
        else ""
    )
    origin = url.scheme + "://" + authority
    path = url.path
    if (
        origin not in allowed_origins
        or re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", path) is None
        or any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in ("/api", "/assets", "/health", "/docs", "/redoc")
        )
    ):
        raise OAuthError("OAUTH_CALLBACK_CONFIGURATION_INVALID")
    return path, origin
