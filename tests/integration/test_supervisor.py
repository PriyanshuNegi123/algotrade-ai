import asyncio
import threading
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import update

from backend.app.instruments.service import archive, prepare
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.feed_lifecycle import LifecyclePolicy
from backend.app.market_data.observations import read_session, start_session
from backend.app.market_data.supervision_models import CaptureRun
from backend.app.market_data.supervision_store import (
    CaptureError,
    CapturePolicy,
    capture_stop_requested,
    create_capture,
    finish_capture,
    read_capture,
    recover_captures,
    request_capture_stop,
)
from backend.app.market_data.supervisor import CaptureSupervisor
from tests.chain_fixtures import chain_metadata
from tests.conftest import ORIGIN, PASSWORD
from tests.unit.test_feed_lifecycle import Authorizer, Connector, Socket, info, message

KEY = "NSE_INDEX|Synthetic index"


def build(engine, count=2, policy=None, sockets=None, sink=None):
    archive(engine, prepare(chain_metadata()))
    authorizer = Authorizer()
    connector = Connector(
        sockets or [Socket([info(), message().SerializeToString()]) for _ in range(count)]
    )
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    supervisor = CaptureSupervisor(
        engine,
        FeedRequest(instrument_keys=(KEY,)),
        authorizer,
        source="SYNTHETIC",
        policy=policy or CapturePolicy(total_seconds=30, max_sessions=count, session_seconds=1),
        connector=connector,
        sleep=sleep,
        event_sink=sink,
        child_policy=LifecyclePolicy(max_frames=2),
    )
    return supervisor, authorizer, connector, sleeps


def test_rollover_fresh_auth_catalog_sessions_and_aggregates(client):
    supervisor, authorizer, connector, sleeps = build(client.app.state.engine, 3)
    result = asyncio.run(supervisor.run())
    parent = result["capture"]
    assert parent["reason"] == "SESSION_LIMIT" and parent["status"] == "CLOSED"
    assert parent["session_count"] == 3 and parent["event_count"] == 9
    assert parent["stats"]["snapshots"] == 3 and parent["stats"]["observations"] == 3
    assert sleeps == [30, 30] and authorizer.calls == 3 and connector.closed == 3
    assert len({row["id"] for row in result["sessions"]}) == 3
    assert all(row["status"] == "CLOSED" for row in result["sessions"])
    assert all(row["observed_interval_ms"] == 0 for row in result["sessions"])
    assert parent["payload_bytes"] == sum(row["payload_bytes"] for row in result["sessions"])
    assert not parent["live_enabled"] and not parent["health_current"]
    assert parent["source"] == "SYNTHETIC" and parent["qualifying_observation_days"] == 0


@pytest.mark.parametrize(
    "quota,reason,events",
    [
        ({"max_events": 1}, "CAPTURE_EVENT_QUOTA", 1),
        ({"max_payload_bytes": 1}, "CAPTURE_BYTE_QUOTA", 0),
    ],
)
def test_parent_quotas_no_overrun_or_late_writes(client, quota, reason, events):
    policy = CapturePolicy(total_seconds=5, max_sessions=2, session_seconds=1, **quota)
    supervisor, authorizer, connector, _ = build(client.app.state.engine, policy=policy)
    result = asyncio.run(supervisor.run())
    assert result["capture"]["reason"] == reason and result["capture"]["event_count"] == events
    assert len(result["sessions"]) == 1
    assert authorizer.calls == int(events > 0) and connector.closed == int(events > 0)
    assert (
        result["sessions"][0]["event_count"] == events
        and result["sessions"][0]["status"] == "CLOSED"
    )


def test_child_access_failure_never_restarts_parent_budget(client):
    from backend.app.brokers.feed_transport import FeedTransportError

    supervisor, authorizer, _, sleeps = build(
        client.app.state.engine, sockets=[FeedTransportError("FEED_ACCESS_DENIED", retryable=False)]
    )
    result = asyncio.run(supervisor.run())
    assert result["capture"]["reason"] == "CHILD_FAILED" and len(result["sessions"]) == 1
    assert authorizer.calls == 1 and not sleeps


def test_retry_pending_duration_does_not_bypass_backoff(client):
    from backend.app.brokers.feed_transport import FeedTransportError

    socket = Socket(
        [info(), message().SerializeToString(), FeedTransportError("FEED_DISCONNECTED")]
    )
    supervisor, authorizer, _, _ = build(client.app.state.engine, sockets=[socket])
    supervisor.child_policy = LifecyclePolicy(max_frames=10)
    result = asyncio.run(supervisor.run())
    assert result["capture"]["reason"] == "CHILD_FAILED" and authorizer.calls == 1
    assert result["capture"]["stats"]["disconnects"] == 1


def test_cooperative_stop_closes_active_child(client):
    async def exercise():
        supervisor = None

        async def sink(event):
            if event.kind == "SNAPSHOT":
                supervisor.stop.set()

        supervisor, _, connector, _ = build(client.app.state.engine, sink=sink)
        supervisor.child_policy = LifecyclePolicy(max_frames=10)
        result = await supervisor.run()
        assert result["capture"]["reason"] == "COOPERATIVE_STOP"
        assert result["sessions"][0]["status"] == "CLOSED" and connector.closed == 1

    asyncio.run(exercise())


def test_persisted_operator_stop_closes_child_and_preserves_request(client):
    async def exercise():
        engine = client.app.state.engine
        supervisor = None

        async def sink(event):
            if event.kind == "SNAPSHOT":
                first = await asyncio.to_thread(request_capture_stop, engine, supervisor.identity)
                assert first["stop_requested"] and not first["final_state_verified"]
                recorded = read_capture(engine, supervisor.identity)["capture"]["stop_requested_at"]
                await asyncio.to_thread(request_capture_stop, engine, supervisor.identity)
                assert (
                    read_capture(engine, supervisor.identity)["capture"]["stop_requested_at"]
                    == recorded
                )

        supervisor, _, connector, _ = build(client.app.state.engine, sink=sink)
        supervisor.child_policy = LifecyclePolicy(max_frames=10)
        result = await supervisor.run()
        assert result["capture"]["reason"] == "COOPERATIVE_STOP"
        assert result["capture"]["status"] == "CLOSED"
        assert result["capture"]["stop_requested_at"]
        assert result["sessions"][0]["status"] == "CLOSED" and connector.closed == 1

    asyncio.run(exercise())


def test_operator_stop_only_targets_requested_parent(client):
    engine = client.app.state.engine
    request = FeedRequest(instrument_keys=(KEY,))
    first = create_capture(engine, request, CapturePolicy(), "SYNTHETIC")
    other = create_capture(engine, request, CapturePolicy(), "SYNTHETIC")
    assert request_capture_stop(engine, first)["stop_requested"]
    assert capture_stop_requested(engine, first)
    assert not capture_stop_requested(engine, other)
    finish_capture(engine, first, "COOPERATIVE_STOP")
    finish_capture(engine, other, "SESSION_LIMIT")


def test_operator_stop_interrupts_rollover_without_another_subscription(client):
    async def exercise():
        engine = client.app.state.engine
        supervisor, authorizer, connector, _ = build(engine, 2)

        async def wait_between_sessions(delay):
            await asyncio.to_thread(request_capture_stop, engine, supervisor.identity)
            await asyncio.Future()

        supervisor.sleep = wait_between_sessions
        result = await supervisor.run()
        assert result["capture"]["reason"] == "COOPERATIVE_STOP"
        assert result["capture"]["session_count"] == 1
        assert authorizer.calls == 1 and connector.closed == 1

    asyncio.run(exercise())


def test_stop_on_closed_capture_is_nonmutating(client):
    engine = client.app.state.engine
    identity = create_capture(
        engine, FeedRequest(instrument_keys=(KEY,)), CapturePolicy(), "SYNTHETIC"
    )
    finish_capture(engine, identity, "SESSION_LIMIT")
    before = read_capture(engine, identity)
    assert not request_capture_stop(engine, identity)["stop_requested"]
    assert read_capture(engine, identity) == before


@pytest.mark.parametrize("identity", ["not-an-id", "a" * 32])
def test_stop_invalid_or_unknown_capture_fails_closed(client, identity):
    with pytest.raises(CaptureError):
        request_capture_stop(client.app.state.engine, identity)


def test_cancelled_parent_drains_child_before_closing(client):
    async def exercise():
        entered = asyncio.Event()

        async def sink(event):
            if event.kind == "SNAPSHOT":
                entered.set()
                await asyncio.Future()

        supervisor, _, connector, _ = build(client.app.state.engine, sink=sink)
        task = asyncio.create_task(supervisor.run())
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = read_capture(client.app.state.engine, supervisor.identity)
        assert result["capture"]["reason"] == "CANCELLED" and connector.closed == 1
        assert result["sessions"][0]["status"] == "CLOSED"

    asyncio.run(exercise())


def test_cancel_during_creation_keeps_identity_and_closes_child(client):
    entered, release = threading.Event(), threading.Event()

    def delayed(*args):
        entered.set()
        assert release.wait(2)
        return start_session(*args)

    async def exercise():
        supervisor, authorizer, _, _ = build(client.app.state.engine)
        with patch("backend.app.market_data.supervisor.start_session", delayed):
            task = asyncio.create_task(supervisor.run())
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        result = read_capture(client.app.state.engine, supervisor.identity)
        assert (
            result["capture"]["status"] == "CLOSED" and result["capture"]["reason"] == "CANCELLED"
        )
        assert result["sessions"][0]["status"] == "CLOSED" and authorizer.calls == 0

    asyncio.run(exercise())


def test_expired_parent_recovery_no_false_crash_end(client):
    from datetime import UTC, datetime, timedelta

    from backend.app.market_data.supervision_store import create_capture

    engine = client.app.state.engine
    request = FeedRequest(instrument_keys=(KEY,))
    parent = create_capture(engine, request, CapturePolicy(), "SYNTHETIC")
    child = start_session(engine, request, LifecyclePolicy(), "SYNTHETIC", parent)
    assert recover_captures(engine) == 0
    with engine.begin() as connection:
        connection.execute(
            update(CaptureRun)
            .where(CaptureRun.id == parent)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert read_capture(engine, parent)["capture"]["status"] == "ABANDONED"
    assert recover_captures(engine) == 1 and recover_captures(engine) == 0
    result = read_capture(engine, parent)
    assert result["capture"]["status"] == "INTERRUPTED" and result["capture"]["ended_at"] is None
    assert read_session(engine, child, 20, 0)["session"]["status"] == "INTERRUPTED"


def test_read_api_private_and_no_start_route(client):
    supervisor, _, _, _ = build(client.app.state.engine, 1)
    identity = asyncio.run(supervisor.run())["capture"]["id"]
    assert client.get(f"/api/observations/captures/{identity}").status_code == 401
    client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert (
        client.get(f"/api/observations/captures/{identity}").json()["capture"]["session_count"] == 1
    )
    assert client.get("/api/observations/captures/" + "0" * 32).status_code == 404
    assert client.post("/api/observations/captures", json={}).status_code == 405


@pytest.mark.parametrize(
    "values",
    [
        {"total_seconds": 3601},
        {"max_sessions": 13},
        {"max_payload_bytes": 67108865},
        {"max_events": 100001},
    ],
)
def test_hard_policy_bounds(values):
    with pytest.raises(ValidationError):
        CapturePolicy(**values)


def test_total_runtime_interrupts_rollover_wait(client):
    async def exercise():
        supervisor, authorizer, _, _ = build(
            client.app.state.engine,
            policy=CapturePolicy(total_seconds=2, session_seconds=1, max_sessions=3),
        )

        async def sleep(_):
            await asyncio.Future()

        supervisor.sleep = sleep
        result = await supervisor.run()
        assert result["capture"]["reason"] == "TOTAL_DURATION_LIMIT"
        assert result["capture"]["session_count"] == 1 and authorizer.calls == 1

    asyncio.run(exercise())


def test_preset_stop_has_no_db_or_network_side_effect(client):
    supervisor, authorizer, _, _ = build(client.app.state.engine)
    supervisor.stop.set()
    result = asyncio.run(supervisor.run())
    assert result["capture"] is None and authorizer.calls == 0 and supervisor.identity is None
