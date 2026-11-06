import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from backend.app.brokers.feed_authorization import (
    AUTHORIZE_URL,
    FeedAuthorizationError,
    parse_grant,
)
from backend.app.brokers.upstox import BrokerError, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.service import archive, prepare
from backend.app.market_data.feed import (
    MAX_FRAME_BYTES,
    FeedError,
    FeedPlan,
    FeedRequest,
    decode_frame,
    resolve_feed,
)
from backend.vendor.upstox import MarketDataFeed_pb2 as pb
from tests.chain_fixtures import chain_metadata

NOW = datetime.now(UTC)
KEY = "NSE_INDEX|Synthetic index"
PLAN = FeedPlan("a" * 64, (KEY,))
URL = (
    "wss://feed.upstox.com/market-data-feeder/v3/upstox-developer-api/feeds"
    "?requestId=11111111-1111-1111-1111-111111111111&code=22222222-2222-2222-2222-222222222222"
)


def grant_body(url=URL):
    return json.dumps({"status": "success", "data": {"authorized_redirect_uri": url}}).encode()


def adapter(handler, **overrides):
    values = {
        "_env_file": None,
        "app_env": "test",
        "database_url": "sqlite://",
        "upstox_analytics_token": "synthetic-feed-credential",
        "upstox_analytics_expires_at": NOW + timedelta(hours=1),
        **overrides,
    }
    return ReadOnlyUpstox(Settings(**values), httpx.MockTransport(handler))


def message():
    result = pb.FeedResponse(type=pb.live_feed, currentTs=int(NOW.timestamp() * 1000))
    result.feeds[KEY].ltpc.CopyFrom(
        pb.LTPC(
            ltp=123.45,
            cp=120,
            ltt=int((NOW - timedelta(seconds=1)).timestamp() * 1000),
            ltq=75,
        )
    )
    return result


def test_schema_integrity_and_binary_vector():
    schema = Path("backend/vendor/upstox/MarketDataFeed.proto")
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == (
        "3e1c939dce2c83a3fef91405c5ca268dfa089aae973319f56685f12a5afcf612"
    )
    # Independently hand-encoded fixed64 ltp=1.0, int64 ltt=1000, quantity=2, cp=2.0.
    tick = pb.LTPC.FromString(bytes.fromhex("09000000000000f03f10e8071802210000000000000040"))
    assert (tick.ltp, tick.ltt, tick.ltq, tick.cp) == (1, 1000, 2, 2)


def test_authorization_fixed_get_and_single_use_redaction():
    calls = []

    def handler(request):
        calls.append(request)
        assert str(request.url) == AUTHORIZE_URL
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer synthetic-feed-credential"
        return httpx.Response(200, json=json.loads(grant_body()))

    grant = asyncio.run(adapter(handler).authorize_feed())
    assert URL not in repr(grant) and "22222222" not in repr(grant)
    assert grant.consume() == URL
    with pytest.raises(FeedAuthorizationError, match="UNAVAILABLE"):
        grant.consume()
    assert len(calls) == 1 and URL not in repr(grant)


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("wss:", "ws:"),
        URL.replace("wss:", "https:"),
        URL.replace("feed.upstox.com", "upstox.com.evil.example"),
        URL.replace("feed.upstox.com", "127.0.0.1"),
        URL.replace("feed.upstox.com", "feed.upstox.com:443"),
        URL.replace("feed.upstox.com", "user@feed.upstox.com"),
        URL.replace("feed.upstox.com", "feed.upstox.com."),
        URL.replace("feed.upstox.com", "foo.feed.upstox.com"),
        URL.replace("/v3/", "/v2/"),
        URL + "#fragment",
        URL + "&extra=value",
        URL.replace("&code=", "&requestId="),
        URL.replace("&code=", "&code=bad/"),
        URL.replace("&code=22222222-2222-2222-2222-222222222222", ""),
        URL.replace("wss:", "wss:\n"),
        URL.replace("/feeds?", "/%66eeds?"),
    ],
)
def test_unsafe_grants_are_rejected_without_echo(url):
    with pytest.raises(FeedAuthorizationError) as error:
        parse_grant(grant_body(url))
    assert url not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"status":"success","status":"success"}',
        b"[]",
        b'{"status":"success","data":null}',
        b"x" * 16385,
    ],
)
def test_malformed_grants(body):
    with pytest.raises(FeedAuthorizationError):
        parse_grant(body)


def test_expired_local_grant(monkeypatch):
    grant = parse_grant(grant_body())
    monkeypatch.setattr("backend.app.brokers.feed_authorization.time.monotonic", lambda: 1e30)
    with pytest.raises(FeedAuthorizationError):
        grant.consume()


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTH_REQUIRED"),
        (403, "ACCESS_DENIED"),
        (429, "RATE_LIMITED"),
        (302, "UNAVAILABLE"),
        (500, "UNAVAILABLE"),
    ],
)
def test_authorization_safe_http_errors(status, code):
    with pytest.raises(BrokerError, match=code):
        asyncio.run(adapter(lambda _: httpx.Response(status, text=URL)).authorize_feed())


def test_missing_expired_credentials_and_invalid_grant():
    def forbidden(_):
        pytest.fail("Credential failure must not issue a request")

    for overrides, code in [
        ({"upstox_analytics_token": "", "upstox_analytics_expires_at": None}, "NOT_CONFIGURED"),
        ({"upstox_analytics_expires_at": NOW - timedelta(seconds=1)}, "EXPIRED"),
    ]:
        with pytest.raises(BrokerError, match=code):
            asyncio.run(adapter(forbidden, **overrides).authorize_feed())
    with pytest.raises(BrokerError, match="INVALID_RESPONSE") as error:
        asyncio.run(
            adapter(lambda _: httpx.Response(200, json={"status": "success"})).authorize_feed()
        )
    assert URL not in str(error.value)


@pytest.mark.parametrize(
    "keys",
    [
        (),
        (KEY, KEY),
        ("https://evil.example",),
        ("NSE_FO|a/b",),
        ("NSE_INDEX|a\n",),
        tuple(f"NSE_FO|{i}" for i in range(101)),
    ],
)
def test_invalid_subscriptions(keys):
    with pytest.raises(ValidationError):
        FeedRequest(instrument_keys=keys)


def test_catalog_plan_and_binary_subscription(client):
    engine = client.app.state.engine
    with pytest.raises(FeedError, match="CATALOG"):
        resolve_feed(engine, FeedRequest(instrument_keys=(KEY,)))
    catalog = archive(engine, prepare(chain_metadata()))
    plan = resolve_feed(engine, FeedRequest(instrument_keys=(KEY,)))
    assert plan.catalog_snapshot_id == catalog["id"]
    first, second = plan.subscription(), plan.subscription()
    assert isinstance(first, bytes) and first != second
    assert json.loads(first)["data"] == {"mode": "ltpc", "instrumentKeys": [KEY]}
    with pytest.raises(FeedError, match="NOT_IN_CATALOG"):
        resolve_feed(engine, FeedRequest(instrument_keys=("NSE_FO|unknown",)))
    with engine.begin() as connection:
        connection.execute(
            update(InstrumentSnapshot).values(source_modified_at=NOW - timedelta(days=2))
        )
    with pytest.raises(FeedError, match="CURRENT_CATALOG"):
        resolve_feed(engine, FeedRequest(instrument_keys=(KEY,)))


def test_expired_catalog_contract(client):
    engine = client.app.state.engine
    archive(engine, prepare(chain_metadata()))
    with engine.begin() as connection:
        connection.execute(
            update(Instrument)
            .where(Instrument.instrument_type == "CE")
            .values(expiry=NOW - timedelta(days=1))
        )
        key = connection.scalar(
            select(Instrument.instrument_key).where(Instrument.instrument_type == "CE")
        )
    with pytest.raises(FeedError, match="EXPIRED_FEED"):
        resolve_feed(engine, FeedRequest(instrument_keys=(key,)))


def test_ltpc_identity_times_presence_and_unknown_fields():
    result = decode_frame(message().SerializeToString() + b"\xa2\x06\x06secret", PLAN, NOW)
    tick = result.ticks[0]
    assert tick.instrument_key == KEY and tick.last_price == Decimal("123.45")
    assert tick.last_trade_at.tzinfo is UTC and result.generated_at <= result.received_at
    assert tick.freshness == "NOT_EVALUATED" and not tick.execution_eligible
    assert not result.signal_eligible and "secret" not in str(asdict(result))
    assert tick.indicative_price is None
    initial = message()
    initial.type = pb.initial_feed
    initial.feeds[KEY].ltpc.iep.value = 123
    assert decode_frame(initial.SerializeToString(), PLAN, NOW).ticks[0].indicative_price == 123
    empty = message()
    empty.feeds[KEY].ltpc.Clear()
    tick = decode_frame(empty.SerializeToString(), PLAN, NOW).ticks[0]
    assert tick.last_trade_at is None and "ZERO_OR_MISSING_PRICE" in tick.quality_flags


def test_market_info_and_empty_frame():
    info = pb.FeedResponse(type=pb.market_info, currentTs=int(NOW.timestamp() * 1000))
    info.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_CLOSE
    result = decode_frame(info.SerializeToString(), PLAN, NOW)
    assert result.ticks == () and result.market_status == (("NSE_INDEX", "NORMAL_CLOSE"),)
    empty = pb.FeedResponse(type=pb.live_feed, currentTs=int(NOW.timestamp() * 1000))
    assert decode_frame(empty.SerializeToString(), PLAN, NOW).ticks == ()


@pytest.mark.parametrize("body", [b"", b"\xff", b"\x12\x20x", b"x" * (MAX_FRAME_BYTES + 1)])
def test_invalid_binary_frames(body):
    with pytest.raises(FeedError):
        decode_frame(body, PLAN, NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ltp", float("nan")),
        ("ltp", float("inf")),
        ("ltp", -1),
        ("cp", -1),
        ("ltq", -1),
        ("ltt", -1),
        ("ltt", 253402300800000),
        ("ltt", int((NOW + timedelta(minutes=1)).timestamp() * 1000)),
    ],
)
def test_invalid_ticks(field, value):
    response = message()
    setattr(response.feeds[KEY].ltpc, field, value)
    with pytest.raises(FeedError):
        decode_frame(response.SerializeToString(), PLAN, NOW)


def test_bad_identity_type_mode_and_time():
    response = message()
    with pytest.raises(FeedError, match="UNSUBSCRIBED"):
        decode_frame(response.SerializeToString(), FeedPlan("a" * 64, ("NSE_FO|other",)), NOW)
    response.type = 123
    with pytest.raises(FeedError, match="TYPE"):
        decode_frame(response.SerializeToString(), PLAN, NOW)
    response = message()
    response.feeds[KEY].fullFeed.indexFF.ltpc.ltp = 100
    with pytest.raises(FeedError, match="MODE"):
        decode_frame(response.SerializeToString(), PLAN, NOW)
    response = message()
    response.currentTs = 0
    with pytest.raises(FeedError, match="TIMESTAMP"):
        decode_frame(response.SerializeToString(), PLAN, NOW)
    response.currentTs = int((NOW + timedelta(minutes=1)).timestamp() * 1000)
    with pytest.raises(FeedError, match="FUTURE_FEED"):
        decode_frame(response.SerializeToString(), PLAN, NOW)
    with pytest.raises(FeedError, match="NAIVE"):
        decode_frame(message().SerializeToString(), PLAN, NOW.replace(tzinfo=None))
