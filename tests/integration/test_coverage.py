import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import update

from backend.app.instruments.service import archive, prepare
from backend.app.market_data import calendar, coverage
from backend.app.market_data.calendar import (
    CalendarError,
    CalendarPolicy,
    SpecialWindow,
    calendar_days,
    load_calendar,
)
from backend.app.market_data.contracts import IST
from backend.app.market_data.coverage import CoverageError, CoverageRequest, coverage_report
from backend.app.market_data.feed import FeedRequest, decode_frame, resolve_feed
from backend.app.market_data.feed_lifecycle import FeedEvent, FeedTracker, LifecyclePolicy
from backend.app.market_data.observation_models import ObservationEvent
from backend.app.market_data.observations import append_event, read_session, start_session
from backend.vendor.upstox import MarketDataFeed_pb2 as pb
from tests.chain_fixtures import chain_metadata
from tests.conftest import ORIGIN, PASSWORD

KEY = "NSE_FO|synthetic-option"


def fixture_calendar():
    today = datetime.now(IST).date()
    return CalendarPolicy(
        kind="SYNTHETIC_FIXTURE",
        segment="NSE_FO",
        reviewed_at=datetime.now(UTC),
        valid_from=date(today.year, 1, 1),
        valid_through=date(today.year, 12, 31),
        regular_from=date(today.year, 1, 1),
        regular_open=time(0),
        regular_close=time(23, 59),
        holidays={},
        special={today: SpecialWindow(opens=time(0), closes=time(23, 59), source="fixture")},
        evidence_sha256={},
    )


def report_request(source="SYNTHETIC", keys=(KEY,)):
    today = datetime.now(IST).date()
    return CoverageRequest(from_date=today, to_date=today, instrument_keys=keys, source=source)


def recorded(engine, base=None, break_kind=None):
    archive(engine, prepare(chain_metadata()))
    plan = resolve_feed(engine, FeedRequest(instrument_keys=(KEY,)))
    identity = start_session(
        engine, FeedRequest(instrument_keys=(KEY,)), LifecyclePolicy(), "SYNTHETIC"
    )
    base = base or datetime.now(UTC) - timedelta(seconds=3)
    append_event(engine, identity, FeedEvent("PLAN", 1, plan=plan, observed_at=base, elapsed_ms=0))
    tracker = FeedTracker(LifecyclePolicy(), (KEY,))
    for elapsed, info in [(10, True), (1000, False), (2000, False)]:
        clock = base + timedelta(milliseconds=elapsed)
        message = pb.FeedResponse(
            type=pb.market_info if info else pb.live_feed, currentTs=int(clock.timestamp() * 1000)
        )
        if info:
            message.marketInfo.segmentStatus["NSE_FO"] = pb.NORMAL_OPEN
        else:
            message.feeds[KEY].ltpc.CopyFrom(
                pb.LTPC(ltp=100 + elapsed / 1000, cp=99, ltt=message.currentTs, ltq=75)
            )
        frame = decode_frame(message.SerializeToString(), plan, clock)
        item = replace(tracker.accept(frame, 1), observed_at=clock, elapsed_ms=elapsed)
        if elapsed == 2000 and break_kind:
            append_event(
                engine,
                identity,
                FeedEvent(
                    break_kind,
                    1,
                    observed_at=base + timedelta(milliseconds=1500),
                    elapsed_ms=1500,
                    detail="FEED_DISCONNECTED" if break_kind == "DISCONNECTED" else None,
                ),
            )
        append_event(engine, identity, item)
    return identity, base


@pytest.mark.parametrize(
    "day,state",
    [
        ("2026-11-06", "REGULAR_BASELINE"),
        ("2026-11-07", "WEEKEND"),
        ("2026-11-08", "SPECIAL_SESSION"),
        ("2026-11-10", "HOLIDAY"),
        ("2026-01-15", "HOLIDAY"),
        ("2026-01-16", "UNKNOWN_HOURS"),
        ("2027-01-04", "UNKNOWN_CALENDAR"),
    ],
)
def test_verified_calendar_evidence_and_unknowns(day, state):
    result = load_calendar().day(date.fromisoformat(day))
    assert result["state"] == state
    if state == "REGULAR_BASELINE":
        assert result["opens_at"].astimezone(IST).time() == time(9, 15)
        assert result["closes_at"].astimezone(IST).time() == time(15, 40)
    if state == "SPECIAL_SESSION":
        assert result["opens_at"].astimezone(IST).time() == time(14, 20)
        assert result["closes_at"].astimezone(IST).time() == time(15, 40)
    assert not load_calendar().provenance()["amendment_completeness_verified"]


def test_provenance_and_hash_rejection(tmp_path, monkeypatch):
    original = load_calendar()
    assert len(original.evidence_sha256) == 5
    for name, digest in original.evidence_sha256.items():
        assert hashlib.sha256((calendar.DATA / name).read_bytes()).hexdigest() == digest
        (tmp_path / name).write_bytes((calendar.DATA / name).read_bytes())
    (tmp_path / "nse_fo_2026.json").write_bytes((calendar.DATA / "nse_fo_2026.json").read_bytes())
    (tmp_path / "FAOP71777.pdf").write_bytes(b"changed")
    load_calendar.cache_clear()
    monkeypatch.setattr(calendar, "DATA", tmp_path)
    with pytest.raises(CalendarError, match="EVIDENCE_INVALID"):
        load_calendar()
    load_calendar.cache_clear()


def test_calendar_range_and_timezone():
    result = calendar_days(date(2026, 11, 6), date(2026, 11, 8))
    assert len(result["days"]) == 3 and result["days"][0]["opens_at"].tzinfo is UTC
    assert not result["signal_eligible"]
    with pytest.raises(CalendarError):
        calendar_days(date(2026, 1, 1), date(2026, 2, 1))


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument_keys": ("NSE_INDEX|Synthetic",)},
        {"instrument_keys": (KEY, KEY)},
        {"instrument_keys": ("NSE_FO|https://evil.example",)},
        {"instrument_keys": tuple(f"NSE_FO|{i}" for i in range(21))},
        {"to_date": date(9999, 12, 31)},
        {"from_date": date(2026, 1, 1), "to_date": date(2026, 1, 8)},
    ],
)
def test_report_request_bounds(changes):
    values = {
        "from_date": date(2026, 11, 6),
        "to_date": date(2026, 11, 6),
        "instrument_keys": (KEY,),
        **changes,
    }
    with pytest.raises(ValidationError):
        CoverageRequest(**values)


def test_sampled_intervals_are_unioned_and_synthetic_separated(client):
    engine = client.app.state.engine
    first, base = recorded(engine)
    second, _ = recorded(engine, base)
    result = coverage_report(engine, report_request(), policy=fixture_calendar())
    key = result["days"][0]["keys"][0]
    assert key["sampled_interval_ms"] == 1000 and key["accepted_samples"] == 4
    assert set(result["session_ids"]) == {first, second}
    assert key["uncovered_elapsed_ms"] > 0 and key["sampled_fraction"] < 1
    assert result["source"] == "SYNTHETIC" and result["calendar"]["kind"] == "SYNTHETIC_FIXTURE"
    assert result["qualifying_observation_days"] == 0 and not result["calendar_verified"]
    actual = coverage_report(engine, report_request("UPSTOX_V3"), policy=fixture_calendar())
    assert actual["session_ids"] == [] and actual["days"][0]["keys"][0]["sampled_interval_ms"] == 0


@pytest.mark.parametrize("kind", ["IDLE", "DISCONNECTED", "OUT_OF_ORDER"])
def test_discontinuities_never_bridge(client, kind):
    engine = client.app.state.engine
    recorded(engine, break_kind=kind)
    result = coverage_report(engine, report_request(), policy=fixture_calendar())
    assert result["days"][0]["keys"][0]["sampled_interval_ms"] == 0


def test_no_evidence_unknown_hours_future_and_closed(client):
    engine = client.app.state.engine
    for day, expected in [
        (date(2026, 1, 16), None),
        (date(2026, 11, 10), 0),
        (date(2027, 1, 4), None),
    ]:
        request = CoverageRequest(from_date=day, to_date=day, instrument_keys=(KEY,))
        result = coverage_report(engine, request)
        assert result["days"][0]["keys"][0]["uncovered_elapsed_ms"] == expected
    result = coverage_report(
        engine,
        CoverageRequest(
            from_date=date(2026, 11, 6), to_date=date(2026, 11, 6), instrument_keys=(KEY,)
        ),
        now=datetime(2026, 11, 6, 0, tzinfo=UTC),
    )
    assert result["days"][0]["elapsed_scheduled_ms"] == 0
    assert result["days"][0]["keys"][0]["sampled_fraction"] is None


def test_outside_windows_and_missing_keys(client):
    engine = client.app.state.engine
    recorded(engine)
    policy = fixture_calendar().model_copy(
        update={"special": {}, "regular_open": time(0), "regular_close": time(0, 1)}
    )
    result = coverage_report(engine, report_request(keys=(KEY, "NSE_FO|missing")), policy=policy)
    assert all(item["sampled_interval_ms"] == 0 for item in result["days"][0]["keys"])
    assert result["outside_or_unusable_frames"] == 2


def test_digest_and_resource_caps_fail_without_partial_report(client, monkeypatch):
    engine = client.app.state.engine
    identity, _ = recorded(engine)
    monkeypatch.setattr(coverage, "MAX_EVENTS", 1)
    with pytest.raises(CoverageError, match="REPORT_LIMIT"):
        coverage_report(engine, report_request(), policy=fixture_calendar())
    monkeypatch.setattr(coverage, "MAX_EVENTS", 20_000)
    with engine.begin() as connection:
        connection.execute(
            update(ObservationEvent)
            .where(ObservationEvent.session_id == identity, ObservationEvent.sequence == 1)
            .values(payload_sha256="0" * 64)
        )
    with pytest.raises(CoverageError, match="ARCHIVE_INVALID"):
        coverage_report(engine, report_request(), policy=fixture_calendar())


def test_private_endpoints_do_not_mutate_or_contact_broker(client):
    engine = client.app.state.engine
    identity, _ = recorded(engine)
    params = {
        "from_date": "2026-11-06",
        "to_date": "2026-11-06",
        "instrument_key": KEY,
        "source": "SYNTHETIC",
    }
    assert client.get("/api/observations/coverage", params=params).status_code == 401
    client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    before = read_session(engine, identity, 50, 0)
    response = client.get("/api/observations/coverage", params=params)
    assert response.status_code == 200 and response.json()["qualifying_observation_days"] == 0
    assert client.get("/api/observations/calendar", params=params).status_code == 200
    assert read_session(engine, identity, 50, 0) == before
    assert (
        client.get(
            "/api/observations/coverage", params={**params, "instrument_key": "NSE_INDEX|x"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/observations/coverage", params={**params, "to_date": "2026-12-31"}
        ).status_code
        == 422
    )
    assert client.post("/api/observations/coverage", json={}).status_code == 405
