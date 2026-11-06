import asyncio
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import event, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.instruments.service import archive, prepare
from backend.app.market_data.feed import FeedRequest, decode_frame, resolve_feed
from backend.app.market_data.feed_lifecycle import (
    FeedEvent,
    FeedRunner,
    FeedTracker,
    LifecyclePolicy,
)
from backend.app.market_data.observation_models import ObservationSession
from backend.app.market_data.observations import (
    ObservationError,
    ObservationWriter,
    append_event,
    finish_session,
    list_sessions,
    read_session,
    recover_abandoned,
    start_session,
)
from backend.vendor.upstox import MarketDataFeed_pb2 as pb
from tests.chain_fixtures import chain_metadata
from tests.conftest import ORIGIN, PASSWORD
from tests.unit.test_feed_lifecycle import Authorizer, Connector, Socket

KEY = "NSE_INDEX|Synthetic index"


def seed(engine):
    archive(engine, prepare(chain_metadata()))
    request = FeedRequest(instrument_keys=(KEY,))
    plan = resolve_feed(engine, request)
    identity = start_session(engine, request, LifecyclePolicy(), "SYNTHETIC")
    now = datetime.now(UTC)
    planned = FeedEvent("PLAN", 1, plan=plan, observed_at=now, elapsed_ms=0)
    append_event(engine, identity, planned)
    return identity, plan, now, planned


def source_frame(plan, now, *, info=False, price=100):
    message = pb.FeedResponse(
        type=pb.market_info if info else pb.live_feed, currentTs=int(now.timestamp() * 1000)
    )
    if info:
        message.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_OPEN
    else:
        message.feeds[KEY].ltpc.CopyFrom(pb.LTPC(ltp=price, cp=99, ltt=message.currentTs, ltq=75))
    return decode_frame(message.SerializeToString(), plan, now)


def sample_events(plan, now):
    tracker = FeedTracker(LifecyclePolicy(), (KEY,))
    events = []
    for elapsed, info in [(10, True), (1000, False), (2000, False)]:
        clock = now + timedelta(milliseconds=elapsed)
        result = tracker.accept(source_frame(plan, clock, info=info, price=100 + elapsed / 1000), 1)
        events.append(
            replace(result, observed_at=clock, elapsed_ms=elapsed, health=tracker.health_at(clock))
        )
    return events


def test_canonical_durability_pagination_and_accounting(client):
    engine = client.app.state.engine
    identity, plan, now, planned = seed(engine)
    for item in sample_events(plan, now):
        append_event(engine, identity, item)
    assert append_event(engine, identity, planned) == 1
    result = read_session(engine, identity, 2, 0)
    assert result["next_after"] == 2 and len(result["events"]) == 2
    assert result["session"]["event_count"] == 4
    assert result["session"]["observed_interval_ms"] == 1000
    assert result["session"]["qualifying_observation_days"] == 0
    assert result["session"]["source"] == "SYNTHETIC"
    assert read_session(engine, identity, 50, 2)["events"][0]["sequence"] == 3
    assert list_sessions(engine, 1, None)["sessions"][0]["id"] == identity
    finish_session(engine, identity, "FRAME_LIMIT", 2200)
    before = read_session(engine, identity, 50, 0)
    finish_session(engine, identity, "DURATION_LIMIT", 3000)
    assert read_session(engine, identity, 50, 0) == before
    assert before["session"]["ended_at"].tzinfo is UTC
    with pytest.raises(ObservationError, match="NOT_RUNNING"):
        append_event(engine, identity, replace(planned, elapsed_ms=3000))


def test_idle_disconnect_and_missing_data_never_bridge_capture(client):
    engine = client.app.state.engine
    identity, plan, now, _ = seed(engine)
    events = sample_events(plan, now)
    for item in events[:2]:
        append_event(engine, identity, item)
    append_event(
        engine,
        identity,
        FeedEvent(
            "IDLE",
            1,
            observed_at=now + timedelta(milliseconds=1500),
            elapsed_ms=1500,
            detail="NO_NEW_FRAME",
        ),
    )
    append_event(engine, identity, events[-1])
    assert read_session(engine, identity, 50, 0)["session"]["observed_interval_ms"] == 0
    append_event(
        engine,
        identity,
        FeedEvent(
            "DISCONNECTED",
            1,
            observed_at=now + timedelta(seconds=3),
            elapsed_ms=3000,
            detail="FEED_DISCONNECTED",
        ),
    )
    assert read_session(engine, identity, 50, 0)["session"]["observed_interval_ms"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"detail": "secret credential echo"},
        {"signal_eligible": True},
        {"elapsed_ms": -1},
        {"attempt": 4},
        {"observed_at": datetime.now()},
    ],
)
def test_rejected_events_do_not_mutate_session(client, change):
    engine = client.app.state.engine
    identity, _, _, planned = seed(engine)
    before = read_session(engine, identity, 50, 0)
    with pytest.raises(ObservationError):
        append_event(engine, identity, replace(planned, **change))
    assert read_session(engine, identity, 50, 0) == before


def test_atomic_rollback_and_storage_limit(client):
    engine = client.app.state.engine
    identity, plan, now, _ = seed(engine)
    before = read_session(engine, identity, 50, 0)

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO observation_events"):
            raise SQLAlchemyError("synthetic failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            append_event(engine, identity, sample_events(plan, now)[0])
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert read_session(engine, identity, 50, 0) == before
    with Session(engine) as db, db.begin():
        row = db.get(ObservationSession, identity)
        row.payload_bytes = 32 * 1024 * 1024
    with pytest.raises(ObservationError, match="STORAGE_LIMIT"):
        append_event(engine, identity, sample_events(plan, now)[0])


def test_catalog_and_receipt_mismatch_are_rejected(client):
    engine = client.app.state.engine
    identity, plan, now, _ = seed(engine)
    item = sample_events(plan, now)[1]
    bad = replace(item, frame=replace(item.frame, catalog_snapshot_id="0" * 64))
    with pytest.raises(ObservationError, match="CATALOG_MISMATCH"):
        append_event(engine, identity, bad)
    with pytest.raises(ObservationError, match="TICK_MISMATCH"):
        append_event(engine, identity, replace(item, observations=()))
    append_event(engine, identity, item)
    with pytest.raises(ObservationError, match="CLOCK_REGRESSION"):
        append_event(engine, identity, replace(item, elapsed_ms=900))


def test_abandoned_recovery_no_resume_no_invented_end(client):
    engine = client.app.state.engine
    identity, _, _, planned = seed(engine)
    assert recover_abandoned(engine) == 0
    with engine.begin() as connection:
        connection.execute(
            update(ObservationSession)
            .where(ObservationSession.id == identity)
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert read_session(engine, identity, 50, 0)["session"]["status"] == "ABANDONED"
    assert recover_abandoned(engine) == 1 and recover_abandoned(engine) == 0
    result = read_session(engine, identity, 50, 0)["session"]
    assert result["status"] == "INTERRUPTED" and result["ended_at"] is None
    assert result["recovered_at"].tzinfo is UTC and result["run_elapsed_ms"] is None
    with pytest.raises(ObservationError, match="NOT_RUNNING"):
        append_event(engine, identity, replace(planned, elapsed_ms=1))


def test_private_read_api_no_mutation_or_stream_route(client):
    identity, _, _, _ = seed(client.app.state.engine)
    assert client.get("/api/observations/sessions").status_code == 401
    client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert client.get("/api/observations/sessions").json()["sessions"][0]["id"] == identity
    page = client.get(f"/api/observations/sessions/{identity}", params={"limit": 1}).json()
    assert page["events"][0]["event"]["kind"] == "PLAN"
    assert client.get("/api/observations/sessions/" + "0" * 32).status_code == 404
    for params in [{"limit": 51}, {"after": -1}]:
        assert (
            client.get(f"/api/observations/sessions/{identity}", params=params).status_code == 422
        )
    assert client.post("/api/observations/sessions", json={}).status_code == 405
    assert client.post("/api/observations/start", json={}).status_code == 404


def test_runner_records_then_closes_before_finalization(client):
    engine = client.app.state.engine
    _, plan, now, _ = seed(engine)

    async def exercise():
        request = FeedRequest(instrument_keys=(KEY,))
        identity = start_session(engine, request, LifecyclePolicy(), "SYNTHETIC")
        writer = ObservationWriter(engine, identity)

        async def load():
            return plan

        socket = Socket([source_frame_bytes(plan, now, True), source_frame_bytes(plan, now, False)])
        runner = FeedRunner(
            Authorizer(),
            load,
            writer.append,
            connector=Connector([socket]),
            policy=LifecyclePolicy(max_frames=2),
        )
        result = await runner.run()
        await writer.finish(str(result["reason"]), result["run_elapsed_ms"])
        saved = read_session(engine, identity, 50, 0)
        assert saved["session"]["status"] == "CLOSED" and saved["session"]["event_count"] == 3
        assert [row["event"]["kind"] for row in saved["events"]] == [
            "PLAN",
            "MARKET_INFO",
            "SNAPSHOT",
        ]

    asyncio.run(exercise())


def source_frame_bytes(plan, now, info):
    message = pb.FeedResponse(
        type=pb.market_info if info else pb.live_feed, currentTs=int(now.timestamp() * 1000)
    )
    if info:
        message.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_OPEN
    else:
        message.feeds[KEY].ltpc.CopyFrom(pb.LTPC(ltp=100, cp=99, ltt=message.currentTs, ltq=75))
    return message.SerializeToString()


def test_cancellation_waits_for_atomic_write(client):
    engine = client.app.state.engine
    identity, plan, now, _ = seed(engine)
    entered, release = threading.Event(), threading.Event()
    original = append_event

    def delayed(*args):
        entered.set()
        assert release.wait(2)
        return original(*args)

    async def exercise():
        writer = ObservationWriter(engine, identity)
        with patch("backend.app.market_data.observations.append_event", delayed):
            task = asyncio.create_task(writer.append(sample_events(plan, now)[0]))
            await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        await writer.finish("CANCELLED", 10)
        result = read_session(engine, identity, 50, 0)["session"]
        assert result["event_count"] == 2 and result["status"] == "CLOSED"

    asyncio.run(exercise())
