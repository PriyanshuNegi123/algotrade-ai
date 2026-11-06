"""Restricted Upstox status/history/chain/feed-authorization GET adapter.

No public URL/method, funds or order API.

Official endpoint/contract checked 2026-11-06; docs/BROKER_COMPLIANCE.md records sources.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.brokers.feed_authorization import (
    AUTHORIZE_URL,
    FeedAuthorizationError,
    FeedGrant,
    parse_grant,
)
from backend.app.config import Settings
from backend.app.market_data.contracts import CandleRequest, history_url
from backend.app.market_data.option_contracts import ChainRequest, chain_url

STATUS_URL = "https://api.upstox.com/v2/market/status/NSE"
MAX_RESPONSE_BYTES = 65_536

MarketPhase = Literal[
    "NORMAL_OPEN", "NORMAL_CLOSE", "PRE_OPEN_START", "PRE_OPEN_END", "CLOSING_START", "CLOSING_END"
]
ProbeCode = Literal[
    "NOT_CONFIGURED",
    "EXPIRED",
    "AUTH_REQUIRED",
    "ACCESS_DENIED",
    "RATE_LIMITED",
    "UNAVAILABLE",
    "INVALID_RESPONSE",
]


class BrokerError(Exception):
    def __init__(self, code: ProbeCode, retry_after: int = 30):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class ExchangeStatus(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    exchange: Literal["NSE"]
    status: MarketPhase
    # An exchange-state change time, NOT a market-price timestamp.
    last_updated: int = Field(gt=0, le=253402300799999)


class StatusEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    status: Literal["success"]
    data: ExchangeStatus


@dataclass(frozen=True)
class BrokerPayload:
    source_url: str
    body: bytes = field(repr=False)
    retrieved_at: datetime


class ReadOnlyUpstox:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._transport = transport

    def credential_state(self) -> Literal["NOT_CONFIGURED", "EXPIRED", "UNVERIFIED"]:
        if not self._settings.upstox_analytics_token.get_secret_value():
            return "NOT_CONFIGURED"
        expires = self._settings.upstox_analytics_expires_at
        if expires is None or expires <= datetime.now(UTC):
            return "EXPIRED"
        return "UNVERIFIED"

    async def _download_json(self, url: str, max_bytes: int) -> BrokerPayload:
        state = self.credential_state()
        if state != "UNVERIFIED":
            raise BrokerError(state)
        token = self._settings.upstox_analytics_token.get_secret_value()
        try:
            # Fixed official host/path, no redirects, proxy env or automatic retries.
            async with asyncio.timeout(10):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(5),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "GET",
                        url,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    ) as response:
                        if response.status_code == 401:
                            raise BrokerError("AUTH_REQUIRED")
                        if response.status_code == 403:
                            raise BrokerError("ACCESS_DENIED")
                        if response.status_code == 429:
                            value = response.headers.get("retry-after", "60")
                            delay = (
                                int(value)
                                if value.isascii() and value.isdigit() and len(value) < 5
                                else 60
                            )
                            raise BrokerError("RATE_LIMITED", retry_after=max(1, min(delay, 3600)))
                        if response.status_code != 200:
                            raise BrokerError("UNAVAILABLE")
                        media_type = response.headers.get("content-type", "").split(";")[0].lower()
                        if media_type != "application/json":
                            raise BrokerError("INVALID_RESPONSE")
                        if (
                            response.headers.get("content-encoding", "identity").lower()
                            != "identity"
                        ):
                            # Reject compression before decoding an unbounded expansion.
                            raise BrokerError("INVALID_RESPONSE")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            body.extend(chunk)
                            if len(body) > max_bytes:
                                raise BrokerError("INVALID_RESPONSE")
            return BrokerPayload(url, bytes(body), datetime.now(UTC))
        except (httpx.HTTPError, TimeoutError):
            raise BrokerError("UNAVAILABLE") from None

    async def exchange_status(self) -> ExchangeStatus:
        payload = await self._download_json(STATUS_URL, MAX_RESPONSE_BYTES)
        try:
            envelope = StatusEnvelope.model_validate(json.loads(payload.body))
            updated = datetime.fromtimestamp(envelope.data.last_updated / 1000, UTC)
            if updated > datetime.now(UTC) + timedelta(minutes=5):
                raise BrokerError("INVALID_RESPONSE")
            return envelope.data
        except (ValueError, ValidationError, OverflowError, RecursionError):
            raise BrokerError("INVALID_RESPONSE") from None

    async def historical_candles(self, request: CandleRequest) -> BrokerPayload:
        # Catalog resolution happens before this method; keys remain one encoded path component.
        return await self._download_json(history_url(request), 3 * 1024 * 1024)

    async def authorize_feed(self) -> FeedGrant:
        payload = await self._download_json(AUTHORIZE_URL, 16_384)
        try:
            return parse_grant(payload.body)
        except FeedAuthorizationError:
            raise BrokerError("INVALID_RESPONSE") from None

    async def option_chain(self, request: ChainRequest) -> BrokerPayload:
        return await self._download_json(chain_url(request), 3 * 1024 * 1024)


class BrokerSnapshot(BaseModel):
    state: str
    credential_type: Literal["ANALYTICS_OPERATOR_DECLARED"] = "ANALYTICS_OPERATOR_DECLARED"
    checked_at: datetime | None = None
    exchange: ExchangeStatus | None = None
    next_action: str
    entries_enabled: Literal[False] = False
    live_enabled: Literal[False] = False


ACTIONS = {
    "NOT_CONFIGURED": "Configure the Analytics Token and its expiry through server secrets.",
    "EXPIRED": "Replace the expired Analytics Token locally; trading remains disabled.",
    "UNVERIFIED": "Run the read-only connection check. No market recording is active.",
    "CHECKED": "Connectivity checked only; quotes and observation recording remain inactive.",
    "AUTH_REQUIRED": "Broker rejected authentication. Replace the credential locally.",
    "ACCESS_DENIED": "Review token permissions and broker access restrictions.",
    "RATE_LIMITED": "Wait for the retry period before checking again.",
    "UNAVAILABLE": "Broker connection unavailable; retry after checking network health.",
    "INVALID_RESPONSE": "Broker response could not be validated; do not use it for trading.",
}


class BrokerMonitor:
    """Single-worker, serialized probes; state is ephemeral and never trading authorization."""

    def __init__(self, adapter: ReadOnlyUpstox):
        self._adapter = adapter
        self._lock = asyncio.Lock()
        self._next_attempt = 0.0
        self._checked_at: datetime | None = None
        self._exchange: ExchangeStatus | None = None
        self._state = "UNVERIFIED"

    def snapshot(self) -> BrokerSnapshot:
        state: str = self._adapter.credential_state()
        if state == "UNVERIFIED":
            state = self._state
            if self._checked_at and datetime.now(UTC) - self._checked_at > timedelta(seconds=60):
                state = "UNVERIFIED"
        return BrokerSnapshot(
            state=state,
            checked_at=self._checked_at,
            exchange=self._exchange if state == "CHECKED" else None,
            next_action=ACTIONS[state],
        )

    async def check(self) -> BrokerSnapshot:
        async with self._lock:
            if self._adapter.credential_state() != "UNVERIFIED":
                return self.snapshot()
            if time.monotonic() < self._next_attempt:
                raise BrokerError(
                    "RATE_LIMITED", max(1, int(self._next_attempt - time.monotonic()) + 1)
                )
            self._next_attempt = time.monotonic() + 30
            try:
                result = await self._adapter.exchange_status()
            except BrokerError as error:
                self._state, self._exchange = error.code, None
                self._checked_at = datetime.now(UTC)
                if error.code == "RATE_LIMITED":
                    self._next_attempt = max(
                        self._next_attempt, time.monotonic() + error.retry_after
                    )
                raise
            self._state, self._exchange = "CHECKED", result
            self._checked_at = datetime.now(UTC)
            return self.snapshot()
