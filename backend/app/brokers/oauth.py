"""Upstox OAuth protocol foundation, not wired to routes, storage or the Analytics adapter."""

import asyncio
import hashlib
import json
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

from backend.app.config import Settings
from backend.app.market_data.contracts import IST

AUTHORIZATION_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
MAX_RESPONSE_BYTES = 65_536


class OAuthError(Exception):
    """Fixed safe codes; never interpolate request, response or credential values."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise OAuthError("OAUTH_AWARE_TIME_REQUIRED")
    return value.astimezone(UTC)


class OAuthApp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    client_id: str
    redirect_uri: str
    client_secret: SecretStr

    @field_validator("client_id")
    @classmethod
    def client_identifier(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value) is None:
            raise ValueError("Invalid OAuth client identifier")
        return value

    @field_validator("redirect_uri")
    @classmethod
    def callback(cls, value: str) -> str:
        # Validate without normalizing: the exact registered value goes to both endpoints.
        if len(value) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in value) or "\\" in value:
            raise ValueError("Invalid OAuth callback")
        url = urlsplit(value)
        if (
            not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or "?" in value
            or "#" in value
            or not url.path.startswith("/")
            or url.path.startswith("//")
            or url.scheme not in {"http", "https"}
            or (url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"})
        ):
            raise ValueError("HTTPS or explicit local loopback callback required")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("Invalid OAuth callback port")
        return value

    @field_validator("client_secret")
    @classmethod
    def secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if not 1 <= len(secret) <= 8192 or any(not 33 <= ord(c) <= 126 for c in secret):
            raise ValueError("Invalid OAuth client secret")
        return value


def configured_app(settings: Settings) -> OAuthApp:
    if not all(
        (
            settings.upstox_client_id,
            settings.upstox_client_secret.get_secret_value(),
            settings.upstox_redirect_uri,
        )
    ):
        raise OAuthError("OAUTH_APP_NOT_CONFIGURED")
    try:
        return OAuthApp(
            client_id=settings.upstox_client_id,
            client_secret=settings.upstox_client_secret,
            redirect_uri=settings.upstox_redirect_uri,
        )
    except ValidationError:
        raise OAuthError("OAUTH_APP_CONFIGURATION_INVALID") from None


def configuration_status(settings: Settings) -> dict[str, object]:
    fields = {
        "UPSTOX_CLIENT_ID": bool(settings.upstox_client_id),
        "UPSTOX_CLIENT_SECRET": bool(settings.upstox_client_secret.get_secret_value()),
        "UPSTOX_REDIRECT_URI": bool(settings.upstox_redirect_uri),
    }
    try:
        configured_app(settings)
        state = "CONFIGURED_OPERATOR_DECLARED"
    except OAuthError as error:
        state = "INVALID" if str(error) == "OAUTH_APP_CONFIGURATION_INVALID" else "INCOMPLETE"
        if not any(fields.values()):
            state = "NOT_CONFIGURED"
    return {
        "state": state,
        "configured_fields": fields,
        "registration_verified": False,
        "browser_flow_implemented": True,
        "vault_directory_configured": bool(settings.upstox_oauth_vault_dir),
        "token_storage_checked": False,
        "tokens_stored": None,
        "analytics_credential_used": False,
        "live_enabled": False,
    }


@dataclass(frozen=True)
class AuthorizationRequest:
    url: SecretStr = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class PendingState:
    session_digest: str = field(repr=False)
    app_digest: str = field(repr=False)
    created_at: datetime
    expires_at: datetime


def app_digest(app: OAuthApp) -> str:
    # Changing even the configured app secret invalidates a previously started flow.
    return hashlib.sha256(
        json.dumps([app.client_id, app.redirect_uri, app.client_secret.get_secret_value()]).encode()
    ).hexdigest()


def session_binding(value: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise OAuthError("OAUTH_SESSION_BINDING_REQUIRED")


class OAuthStates:
    """Bounded single-process state ledger; hashes only, one pending flow per admin session."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingState] = {}
        self._lock = threading.Lock()

    def begin(
        self,
        app: OAuthApp,
        session_digest: str,
        session_expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> AuthorizationRequest:
        now = aware(now or utc_now())
        expiry = min(aware(session_expires_at), now + timedelta(minutes=5))
        session_binding(session_digest)
        if expiry <= now:
            raise OAuthError("OAUTH_SESSION_EXPIRED")
        state = secrets.token_urlsafe(32)
        with self._lock:
            self._pending = {
                key: item
                for key, item in self._pending.items()
                if item.expires_at > now and item.session_digest != session_digest
            }
            if len(self._pending) >= 32:
                raise OAuthError("OAUTH_PENDING_LIMIT")
            self._pending[hashlib.sha256(state.encode()).hexdigest()] = PendingState(
                session_digest, app_digest(app), now, expiry
            )
        url = (
            AUTHORIZATION_URL
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": app.client_id,
                    "redirect_uri": app.redirect_uri,
                    "state": state,
                }
            )
        )
        return AuthorizationRequest(SecretStr(url), expiry)

    def consume(
        self,
        app: OAuthApp,
        state: str,
        session_digest: str,
        *,
        now: datetime | None = None,
    ) -> datetime:
        now = aware(now or utc_now())
        session_binding(session_digest)
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", state) is None:
            raise OAuthError("OAUTH_STATE_INVALID")
        identity = hashlib.sha256(state.encode()).hexdigest()
        with self._lock:
            item = self._pending.get(identity)
            if item is None:
                raise OAuthError("OAUTH_STATE_INVALID")
            if item.expires_at <= now:
                del self._pending[identity]
                raise OAuthError("OAUTH_STATE_EXPIRED")
            if now < item.created_at:
                del self._pending[identity]
                raise OAuthError("OAUTH_CLOCK_INVALID")
            if not secrets.compare_digest(item.session_digest, session_digest):
                raise OAuthError("OAUTH_SESSION_MISMATCH")
            if not secrets.compare_digest(item.app_digest, app_digest(app)):
                del self._pending[identity]
                raise OAuthError("OAUTH_APP_CHANGED")
            del self._pending[identity]  # Burn before validation/network; no callback retry.
        return item.expires_at


def daily_cutoff(issued_at: datetime) -> datetime:
    local = aware(issued_at).astimezone(IST)
    cutoff = datetime.combine(local.date(), time(3, 30), IST)
    if local >= cutoff:
        cutoff += timedelta(days=1)
    return cutoff.astimezone(UTC)


@dataclass(frozen=True)
class OAuthToken:
    access_token: SecretStr = field(repr=False)
    requested_at: datetime
    received_at: datetime
    expires_at: datetime


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response field")
        result[key] = value
    return result


class UpstoxOAuth:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = utc_now,
    ):
        self._transport, self._clock = transport, clock

    async def complete(
        self, app: OAuthApp, states: OAuthStates, state: str, session_digest: str, code: SecretStr
    ) -> OAuthToken:
        started = aware(self._clock())
        deadline = states.consume(app, state, session_digest, now=started)
        raw_code = code.get_secret_value()
        if not 1 <= len(raw_code) <= 8192 or any(not 33 <= ord(c) <= 126 for c in raw_code):
            raise OAuthError("OAUTH_CODE_INVALID")
        try:
            async with (
                asyncio.timeout(10),
                httpx.AsyncClient(
                    transport=self._transport, timeout=5, follow_redirects=False, trust_env=False
                ) as client,
            ):
                async with client.stream(
                    "POST",
                    TOKEN_URL,
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    data={
                        "code": raw_code,
                        "client_id": app.client_id,
                        "client_secret": app.client_secret.get_secret_value(),
                        "redirect_uri": app.redirect_uri,
                        "grant_type": "authorization_code",
                    },
                ) as response:
                    if response.status_code == 429:
                        raise OAuthError("OAUTH_RATE_LIMITED")
                    if 300 <= response.status_code < 400:
                        raise OAuthError("OAUTH_REDIRECT_REJECTED")
                    if 400 <= response.status_code < 500:
                        raise OAuthError("OAUTH_TOKEN_REQUEST_REJECTED")
                    if response.status_code != 200:
                        raise OAuthError("OAUTH_TOKEN_SERVICE_UNAVAILABLE")
                    if (
                        response.headers.get("content-type", "").split(";")[0].lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise OAuthError("OAUTH_TOKEN_RESPONSE_INVALID")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise OAuthError("OAUTH_TOKEN_RESPONSE_TOO_LARGE")
            value = json.loads(body, object_pairs_hook=unique_object)
            token = value.get("access_token") if isinstance(value, dict) else None
            if (
                not isinstance(token, str)
                or not 1 <= len(token) <= 8192
                or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is None
            ):
                raise OAuthError("OAUTH_TOKEN_RESPONSE_INVALID")
        except (httpx.HTTPError, TimeoutError):
            raise OAuthError("OAUTH_TOKEN_SERVICE_UNAVAILABLE") from None
        except (ValueError, RecursionError):
            raise OAuthError("OAUTH_TOKEN_RESPONSE_INVALID") from None
        finished = aware(self._clock())
        expiry = daily_cutoff(started)
        if finished < started or finished >= min(expiry, deadline):
            raise OAuthError("OAUTH_EXPIRED_DURING_EXCHANGE")
        # Discard profile, extended token and arbitrary response fields. Never persist/activate.
        return OAuthToken(SecretStr(token), started, finished, expiry)
