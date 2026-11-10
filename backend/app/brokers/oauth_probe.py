"""Explicit one-shot OAuth market-status probe. No route, activation or credential promotion."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.brokers.oauth import OAuthError, configured_app, unique_object, utc_now
from backend.app.brokers.oauth_store import OAuthStoreError, OAuthTokenStore
from backend.app.brokers.upstox import MAX_RESPONSE_BYTES, STATUS_URL, MarketPhase, StatusEnvelope
from backend.app.config import Settings


class ProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: Literal[
        "CHECKED",
        "LOCAL_SETUP_REQUIRED",
        "LOCAL_STORAGE_UNAVAILABLE",
        "REAUTHORIZE_REQUIRED",
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "RATE_LIMITED",
        "UNAVAILABLE",
        "INVALID_RESPONSE",
    ]
    credential_type: Literal["OAUTH_QUARANTINED"] = "OAUTH_QUARANTINED"
    market_status: MarketPhase | None = None
    retry_after: int | None = Field(default=None, ge=1, le=3600)
    endpoint_response_verified: bool = False
    account_permissions_verified: Literal[False] = False
    credential_promoted: Literal[False] = False
    recording_started: Literal[False] = False
    entries_enabled: Literal[False] = False
    live_enabled: Literal[False] = False


async def check_oauth_access(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> ProbeResult:
    if (
        settings.trading_mode != "OBSERVATION"
        or settings.live_enabled is not False
        or not settings.upstox_oauth_vault_dir
        or not Path(settings.upstox_oauth_vault_dir).is_absolute()
    ):
        return ProbeResult(state="LOCAL_SETUP_REQUIRED")
    try:
        app = configured_app(settings)
        store = OAuthTokenStore(Path(settings.upstox_oauth_vault_dir), clock=utc_now)
        token = await asyncio.to_thread(store.load, app)
    except OAuthError:
        return ProbeResult(state="LOCAL_SETUP_REQUIRED")
    except OAuthStoreError as error:
        return ProbeResult(
            state="REAUTHORIZE_REQUIRED"
            if str(error) == "OAUTH_VAULT_TOKEN_EXPIRED"
            else "LOCAL_STORAGE_UNAVAILABLE"
        )
    try:
        async with asyncio.timeout(10):
            async with httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(5),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                if token.expires_at <= utc_now():
                    return ProbeResult(state="REAUTHORIZE_REQUIRED")
                async with client.stream(
                    "GET",
                    STATUS_URL,
                    headers={
                        "Authorization": "Bearer " + token.access_token.get_secret_value(),
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as response:
                    if response.status_code in (401, 403):
                        return ProbeResult(
                            state="AUTH_REQUIRED"
                            if response.status_code == 401
                            else "ACCESS_DENIED"
                        )
                    if response.status_code == 429:
                        value = response.headers.get("retry-after", "60")
                        delay = (
                            int(value)
                            if value.isascii() and value.isdigit() and len(value) < 5
                            else 60
                        )
                        return ProbeResult(
                            state="RATE_LIMITED", retry_after=max(1, min(delay, 3600))
                        )
                    if response.status_code != 200:
                        return ProbeResult(state="UNAVAILABLE")
                    if (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        return ProbeResult(state="INVALID_RESPONSE")
                    length = response.headers.get("content-length")
                    if length is not None and (
                        not length.isascii()
                        or not length.isdigit()
                        or len(length) > 8
                        or int(length) > MAX_RESPONSE_BYTES
                    ):
                        return ProbeResult(state="INVALID_RESPONSE")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            return ProbeResult(state="INVALID_RESPONSE")
                        body.extend(chunk)
        envelope = StatusEnvelope.model_validate(json.loads(body, object_pairs_hook=unique_object))
        # Exchange state-change time is not a quote timestamp or session/calendar certificate.
        updated = datetime.fromtimestamp(envelope.data.last_updated / 1000, UTC)
        if updated > utc_now() + timedelta(minutes=5):
            return ProbeResult(state="INVALID_RESPONSE")
        if token.expires_at <= utc_now():
            return ProbeResult(state="REAUTHORIZE_REQUIRED")
        return ProbeResult(
            state="CHECKED", market_status=envelope.data.status, endpoint_response_verified=True
        )
    except (ValueError, ValidationError, OverflowError, RecursionError, OAuthError):
        return ProbeResult(state="INVALID_RESPONSE")
    except (httpx.HTTPError, TimeoutError):
        return ProbeResult(state="UNAVAILABLE")


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"state": "ARGUMENTS_REJECTED", "live_enabled": False}))
        return 2
    try:
        result = asyncio.run(check_oauth_access(Settings()))
    except Exception:
        result = ProbeResult(state="UNAVAILABLE")
    print(result.model_dump_json(), flush=True)
    return 0 if result.state == "CHECKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
