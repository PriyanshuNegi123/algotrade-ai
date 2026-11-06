"""One-use, server-only V3 connection grants. Never serialize the authorized URL."""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

from pydantic import SecretStr

from backend.app.market_data.validation import MarketDataError, strict_json

AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
SOCKET_PATH = "/market-data-feeder/v3/upstox-developer-api/feeds"


class FeedAuthorizationError(Exception):
    pass


@dataclass(repr=False)
class FeedGrant:
    _url: SecretStr = field(repr=False)
    _deadline: float = field(repr=False)
    _used: bool = field(default=False, repr=False)

    def __repr__(self) -> str:
        return "FeedGrant(<redacted>)"

    def consume(self) -> str:
        """Only the future server connector should consume this, immediately before dialing."""
        if self._used or time.monotonic() >= self._deadline:
            self._url = SecretStr("")
            raise FeedAuthorizationError("FEED_GRANT_UNAVAILABLE")
        self._used = True
        result = self._url.get_secret_value()
        self._url = SecretStr("")
        return result


def parse_grant(body: bytes) -> FeedGrant:
    try:
        if len(body) > 16_384:
            raise ValueError
        envelope = strict_json(body)
        if not isinstance(envelope, dict) or envelope.get("status") != "success":
            raise ValueError
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise ValueError
        value = data.get("authorized_redirect_uri")
        if not isinstance(value, str) or len(value) > 2048 or not value.isascii():
            raise ValueError
        if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
            raise ValueError
        url = urlsplit(value)
        # Official docs use a variable xyz.upstox.com hostname. Never allow other domains,
        # userinfo, custom ports, encoded paths, fragments or redirects from the grant.
        if (
            url.scheme != "wss"
            or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.upstox\.com", url.netloc)
            is None
            or url.path != SOCKET_PATH
            or url.fragment
        ):
            raise ValueError
        pairs = parse_qsl(url.query, strict_parsing=True, max_num_fields=2)
        if len(pairs) != 2 or {key for key, _ in pairs} != {"requestId", "code"}:
            raise ValueError
        if any(re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token) is None for _, token in pairs):
            raise ValueError
        return FeedGrant(SecretStr(value), time.monotonic() + 60)
    except (ValueError, TypeError, MarketDataError):
        raise FeedAuthorizationError("INVALID_FEED_GRANT") from None
