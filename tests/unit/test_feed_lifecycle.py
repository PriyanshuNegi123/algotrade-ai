import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from backend.app.brokers import feed_transport
from backend.app.brokers.feed_authorization import FeedAuthorizationError, parse_grant
from backend.app.brokers.feed_transport import FeedTransportError, NoRedirectConnect, open_feed
from backend.app.brokers.upstox import BrokerError
from backend.app.market_data.feed import FeedPlan, decode_frame
from backend.app.market_data.feed_lifecycle import (
    FeedRunner,
    FeedTracker,
    LifecycleError,
    LifecyclePolicy,
)
from backend.vendor.upstox import MarketDataFeed_pb2 as pb
from tests.unit.test_feed import KEY, PLAN, URL, grant_body
from tests.unit.test_feed import message as original_message


def message(now: datetime | None = None):
    result = original_message()
    result.currentTs = int((now or datetime.now(UTC)).timestamp() * 1000)
    result.feeds[KEY].ltpc.ltt = result.currentTs - 1000
    return result


class Authorizer:
    def __init__(self):
        self.calls = 0
        self.state = "UNVERIFIED"
        self.grants = []

    def credential_state(self):
        return self.state

    async def authorize_feed(self):
        self.calls += 1
        grant = parse_grant(grant_body())
        self.grants.append(grant)
        return grant


def info(now: datetime | None = None):
    result = pb.FeedResponse(
        type=pb.market_info, currentTs=int((now or datetime.now(UTC)).timestamp() * 1000)
    )
    result.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_OPEN
    return result.SerializeToString()


class Socket:
    def __init__(self, frames, *, pong=True):
        self.frames, self.sent = list(frames), []
        self.pings = 0
        self.pong = pong

    async def send(self, body):
        self.sent.append(body)

    async def recv(self):
        if not self.frames:
            await asyncio.Future()
        item = self.frames.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def ping(self):
        self.pings += 1
        pong = asyncio.get_running_loop().create_future()
        if self.pong:
            pong.set_result(0.001)
        return pong


class Connector:
    def __init__(self, sockets):
        self.sockets = list(sockets)
        self.opened = self.closed = 0
        self.urls = []

    @asynccontextmanager
    async def __call__(self, grant):
        self.urls.append(grant.consume())
        self.opened += 1
        try:
            socket = self.sockets.pop(0)
            if isinstance(socket, Exception):
                raise socket
            yield socket
        finally:
            self.closed += 1


async def plan_loader():
    return PLAN


def build(sockets, **policy_values):
    events, delays = [], []
    authorizer = Authorizer()
    connector = Connector(sockets)

    async def sink(event):
        events.append(event)

    async def sleep(delay):
        delays.append(delay)

    runner = FeedRunner(
        authorizer,
        plan_loader,
        sink,
        connector=connector,
        sleep=sleep,
        jitter=lambda: 0,
        policy=LifecyclePolicy(**policy_values),
    )
    return runner, authorizer, connector, events, delays


def test_snapshot_order_subscription_and_frame_limit():
    runner, authorizer, connector, events, _ = build(
        [Socket([info(), message().SerializeToString()])], max_frames=2
    )
    result = asyncio.run(runner.run())
    assert result["reason"] == "FRAME_LIMIT" and result["frames"] == 2
    assert [event.kind for event in events] == ["PLAN", "MARKET_INFO", "SNAPSHOT"]
    assert events[-1].observations[0].freshness == "RECENT_TRADE"
    assert not events[-1].execution_eligible and not result["live_enabled"]
    assert connector.closed == 1 and authorizer.calls == 1
    with pytest.raises(FeedAuthorizationError):
        authorizer.grants[0].consume()


@pytest.mark.parametrize(
    "payload,reason",
    [
        (message().SerializeToString(), "MARKET_INFO_REQUIRED"),
        ("not binary", "BINARY_FEED_REQUIRED"),
        (b"\xff", "INVALID_FEED_PROTOBUF"),
    ],
)
def test_protocol_failures_do_not_retry(payload, reason):
    runner, _, connector, _, delays = build([Socket([payload])])
    result = asyncio.run(runner.run())
    assert result["reason"] == reason and connector.closed == 1 and not delays


def test_reconnect_reauthorizes_resolves_and_resubscribes():
    first, second = (
        Socket([FeedTransportError("FEED_DISCONNECTED")]),
        Socket([info(), message().SerializeToString()]),
    )
    runner, authorizer, connector, events, delays = build([first, second], max_frames=2)
    loads = []

    async def load():
        loads.append(1)
        return FeedPlan(str(len(loads)) * 64, (KEY,))

    runner.plan_loader = load
    result = asyncio.run(runner.run())
    assert result["reason"] == "FRAME_LIMIT" and result["attempts"] == 2
    assert authorizer.calls == 2 and len(loads) == 2 and connector.closed == 2
    assert json.loads(first.sent[0])["guid"] != json.loads(second.sent[0])["guid"]
    assert events[-1].frame.catalog_snapshot_id == "2" * 64 and delays == [30]


def test_retry_budget_exponential_backoff_and_sanitized_error():
    runner, _, connector, events, delays = build(
        [FeedTransportError("FEED_UNAVAILABLE") for _ in range(3)]
    )
    result = asyncio.run(runner.run())
    assert result["attempts"] == 3 and result["reason"] == "FEED_UNAVAILABLE"
    assert delays == [30, 60] and connector.closed == 3
    assert URL not in str(result) + str(events)


def test_authorization_rate_limit_and_access_failure():
    runner, authorizer, _, _, delays = build(
        [Socket([info(), message().SerializeToString()])], max_frames=2
    )
    original = authorizer.authorize_feed

    async def authorize():
        if not authorizer.calls:
            authorizer.calls += 1
            raise BrokerError("RATE_LIMITED", 90)
        return await original()

    authorizer.authorize_feed = authorize
    assert asyncio.run(runner.run())["reason"] == "FRAME_LIMIT"
    assert delays == [90]
    runner, authorizer, connector, _, delays = build([])

    async def denied():
        raise BrokerError("ACCESS_DENIED")

    authorizer.authorize_feed = denied
    assert asyncio.run(runner.run())["reason"] == "ACCESS_DENIED"
    assert not delays and connector.opened == 0


def test_missing_and_mid_session_expiry():
    runner, authorizer, connector, _, _ = build([])
    authorizer.state = "EXPIRED"
    assert asyncio.run(runner.run())["reason"] == "FEED_CREDENTIAL_UNAVAILABLE"
    assert not authorizer.calls and not connector.opened
    socket = Socket([info(), message().SerializeToString()])
    runner, authorizer, connector, events, _ = build([socket])
    oldrecv = socket.recv

    async def recv():
        result = await oldrecv()
        authorizer.state = "EXPIRED"
        return result

    socket.recv = recv
    assert asyncio.run(runner.run())["reason"] == "FEED_CREDENTIAL_UNAVAILABLE"
    assert [event.kind for event in events] == ["PLAN"] and connector.closed == 1


def test_initial_timeout_and_heartbeat_failure_cleanup():
    runner, _, connector, _, _ = build(
        [Socket([])], max_attempts=1, first_frame_seconds=0.01, poll_seconds=0.005
    )
    assert asyncio.run(runner.run())["reason"] == "FEED_INITIAL_TIMEOUT"
    assert connector.closed == 1
    socket = Socket([info(), message().SerializeToString()], pong=False)
    runner, _, connector, events, _ = build(
        [socket], max_attempts=1, poll_seconds=0.005, pong_seconds=0.005
    )
    assert asyncio.run(runner.run())["reason"] == "FEED_HEARTBEAT_TIMEOUT"
    assert socket.pings == 1 and events[-2].kind == "IDLE" and connector.closed == 1


def test_pong_does_not_create_ticks_and_cancellation_closes():
    async def exercise():
        socket = Socket([info(), message().SerializeToString()])
        runner, _, connector, events, _ = build([socket], poll_seconds=0.005)
        task = asyncio.create_task(runner.run())
        for _ in range(100):
            await asyncio.sleep(0.001)
            if socket.pings:
                break
        assert socket.pings and events[-1].kind == "IDLE"
        assert sum(len(event.observations) for event in events) == 1
        with pytest.raises(LifecycleError, match="ALREADY_RUNNING"):
            await runner.run()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert connector.closed == 1 and runner.stop_reason == "CANCELLED"

    asyncio.run(exercise())


def test_duration_cancels_backoff():
    async def exercise():
        runner, _, connector, _, _ = build(
            [FeedTransportError("FEED_UNAVAILABLE")], duration_seconds=1
        )
        entered = asyncio.Event()

        async def sleep(_):
            entered.set()
            await asyncio.Future()

        runner.sleep = sleep
        result = await runner.run()
        assert result["reason"] == "DURATION_LIMIT" and connector.closed == 1

    asyncio.run(exercise())


def test_slow_and_failed_consumer_fail_closed():
    runner, _, connector, _, _ = build([Socket([info()])], sink_seconds=0.005)

    async def sink(item):
        if item.kind != "PLAN":
            await asyncio.Future()

    runner.sink = sink
    assert asyncio.run(runner.run())["reason"] == "FEED_SINK_TIMEOUT"
    assert connector.closed == 1
    runner, _, _, _, _ = build([Socket([info()])])

    async def broken(item):
        if item.kind != "PLAN":
            raise ValueError(URL)

    runner.sink = broken
    result = asyncio.run(runner.run())
    assert result["reason"] == "FEED_SINK_FAILED" and URL not in str(result)


@pytest.mark.parametrize("microsecond", [0, 999, 999999])
def test_tracker_duplicate_watermarks_and_trade_freshness(microsecond):
    # One synthetic clock for receipt and protobuf timestamps, including millisecond edges.
    now = datetime(2026, 11, 10, 12, 0, 0, microsecond, tzinfo=UTC)
    first = decode_frame(message(now).SerializeToString(), PLAN, now)
    tracker = FeedTracker(LifecyclePolicy())
    tracker.accept(replace(decode_frame(info(now), PLAN, now), generated_at=first.generated_at), 1)
    snapshot = tracker.accept(first, 1)
    assert snapshot.kind == "SNAPSHOT"
    duplicate = tracker.accept(first, 1)
    assert duplicate.duplicates == 1 and not duplicate.observations
    assert duplicate.frame.ticks == ()
    older = replace(first, generated_at=first.generated_at - timedelta(seconds=1))
    assert tracker.accept(older, 1).kind == "OUT_OF_ORDER"
    tick = replace(
        first.ticks[0], last_trade_at=first.ticks[0].last_trade_at - timedelta(seconds=1)
    )
    oldertrade = replace(first, generated_at=now, ticks=(tick,))
    assert tracker.accept(oldertrade, 1).out_of_order == 1
    missing = replace(first.ticks[0], last_trade_at=None)
    assert (
        tracker.accept(replace(first, generated_at=now, ticks=(missing,)), 1)
        .observations[0]
        .freshness
        == "UNKNOWN_TRADE_TIME"
    )
    # A missing trade time must not reset the prior trade-time high watermark.
    assert tracker.accept(oldertrade, 1).out_of_order == 1


@pytest.mark.parametrize(
    "age,delayed,expected",
    [(30, False, "STALE_TRADE"), (1, True, "DELAYED_FRAME"), (1, False, "RECENT_TRADE")],
)
def test_freshness_is_research_only(age, delayed, expected):
    now = datetime.now(UTC)
    frame = decode_frame(message().SerializeToString(), PLAN, now)
    tick = replace(frame.ticks[0], last_trade_at=now - timedelta(seconds=age))
    frame = replace(
        frame, ticks=(tick,), generated_at=now - timedelta(seconds=11 if delayed else 0)
    )
    tracker = FeedTracker(LifecyclePolicy())
    tracker.seen_info = True
    event = tracker.accept(frame, 1)
    assert event.observations[0].freshness == expected and not event.signal_eligible


def test_no_redirect_and_production_transport_controls():
    redirect = InvalidStatus(Response(302, "Found", Headers({"Location": URL})))
    connection = NoRedirectConnect(URL)
    error = connection.process_redirect(redirect)
    assert isinstance(error, FeedTransportError) and not error.retryable
    captured = {}

    class FakeConnect:
        def __init__(self, url, **options):
            captured.update(options)
            assert url == URL

        async def __aenter__(self):
            return Socket([])

        async def __aexit__(self, *args):
            pass

    async def exercise():
        with patch.object(feed_transport, "NoRedirectConnect", FakeConnect):
            async with open_feed(parse_grant(grant_body())):
                pass

    asyncio.run(exercise())
    assert captured["proxy"] is None and captured["compression"] is None
    assert captured["additional_headers"] is None and captured["max_queue"] == 4
    assert captured["max_size"] == 512 * 1024 and captured["ping_timeout"] == 5
    assert captured["logger"].disabled and not captured["logger"].propagate


@pytest.mark.parametrize(
    "status,code,retry",
    [
        (401, "FEED_ACCESS_DENIED", False),
        (403, "FEED_ACCESS_DENIED", False),
        (429, "FEED_RATE_LIMITED", True),
        (503, "FEED_HANDSHAKE_FAILED", True),
    ],
)
def test_safe_handshake_errors(status, code, retry):
    error = feed_transport._status_error(
        InvalidStatus(Response(status, "bad", Headers({"Retry-After": "90"})))
    )
    assert error.code == code and error.retryable == retry and URL not in str(error)
    if status == 429:
        assert error.retry_after == 90


@pytest.mark.parametrize(
    "values", [{"duration_seconds": 301}, {"max_attempts": 4}, {"max_frames": 10001}]
)
def test_policy_bounds(values):
    with pytest.raises(ValidationError):
        LifecyclePolicy(**values)


def test_health_ages_without_new_ticks_and_missing_keys():
    now = datetime.now(UTC)
    tracker = FeedTracker(LifecyclePolicy(), (KEY, "NSE_FO|missing"))
    tracker.seen_info = True
    tracker.accept(decode_frame(message().SerializeToString(), PLAN, now), 1)
    current = tracker.health_at(now)
    assert {item.freshness for item in current} == {"AWAITING_FIRST_TICK", "RECENT_TRADE"}
    later = tracker.health_at(now + timedelta(seconds=30))
    assert {item.freshness for item in later} == {"AWAITING_FIRST_TICK", "DELAYED_FRAME"}
