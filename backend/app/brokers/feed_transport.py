"""Restricted WSS transport. Credential-bearing URI and upstream exceptions never escape."""

import logging
import ssl
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Protocol, cast

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from backend.app.brokers.feed_authorization import FeedGrant
from backend.app.market_data.feed import MAX_FRAME_BYTES

# A private non-propagating logger also suppresses handshake/frame debug and close reasons.
_SOCKET_LOG = logging.Logger("algotrade.feed.private", level=logging.CRITICAL)
_SOCKET_LOG.addHandler(logging.NullHandler())
_SOCKET_LOG.propagate = False
_SOCKET_LOG.disabled = True


class FeedTransportError(Exception):
    def __init__(self, code: str, *, retryable: bool = True, retry_after: int = 30):
        self.code, self.retryable, self.retry_after = code, retryable, retry_after
        super().__init__(code)


class NoRedirectConnect(connect):
    def process_redirect(self, exc: Exception) -> Exception | str:
        # Returning an exception prevents the library's redirect loop, even for same-host URLs.
        if isinstance(exc, InvalidStatus) and 300 <= exc.response.status_code < 400:
            return FeedTransportError("FEED_REDIRECT_BLOCKED", retryable=False)
        return exc


class FeedSocket(Protocol):
    async def send(self, message: bytes) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def ping(self) -> Awaitable[float]: ...


def _status_error(error: InvalidStatus) -> FeedTransportError:
    status = error.response.status_code
    if status in (401, 403):
        return FeedTransportError("FEED_ACCESS_DENIED", retryable=False)
    if status == 429:
        raw = error.response.headers.get("Retry-After", "60")
        delay = int(raw) if raw.isascii() and raw.isdigit() and len(raw) < 5 else 60
        return FeedTransportError("FEED_RATE_LIMITED", retry_after=max(30, min(delay, 3600)))
    return FeedTransportError("FEED_HANDSHAKE_FAILED", retryable=status >= 500)


@asynccontextmanager
async def open_feed(grant: FeedGrant) -> AsyncIterator[FeedSocket]:
    try:
        async with NoRedirectConnect(
            grant.consume(),
            proxy=None,
            compression=None,
            additional_headers=None,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=5,
            close_timeout=3,
            max_size=MAX_FRAME_BYTES,
            max_queue=4,
            write_limit=32768,
            logger=_SOCKET_LOG,
        ) as connection:
            yield cast(FeedSocket, connection)
    except FeedTransportError:
        raise
    except InvalidStatus as error:
        raise _status_error(error) from None
    except ssl.SSLCertVerificationError:
        raise FeedTransportError("FEED_TLS_FAILED", retryable=False) from None
    except ConnectionClosed:
        raise FeedTransportError("FEED_DISCONNECTED") from None
    except (OSError, TimeoutError, WebSocketException):
        raise FeedTransportError("FEED_UNAVAILABLE") from None
