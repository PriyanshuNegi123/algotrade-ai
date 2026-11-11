"""Synthetic validated frames verify diagnostic-only changes to coverage acceptance."""

from datetime import UTC, date, datetime, timedelta

import pytest

from backend.app.market_data.calendar import load_calendar
from backend.app.market_data.coverage import UNUSABLE_FRAME_REASONS, CoverageRequest, Samples
from backend.app.market_data.observation_schema import CapturedEvent

DAY = date(2026, 11, 11)
RECEIVED = datetime(2026, 11, 11, 5, tzinfo=UTC)
KEY = "NSE_FO|synthetic-option"
REQUEST = CoverageRequest(from_date=DAY, to_date=DAY, instrument_keys=(KEY,))


def frame(received=RECEIVED, age=0, elapsed=1000):
    generated = received - timedelta(seconds=age)
    trade = min(received, generated) - timedelta(seconds=1)
    return CapturedEvent.model_validate(
        {
            "kind": "SNAPSHOT",
            "attempt": 1,
            "frame": {
                "catalog_snapshot_id": "a" * 64,
                "message_type": "initial_feed",
                "generated_at": generated,
                "received_at": received,
                "market_status": [],
                "signal_eligible": False,
                "execution_eligible": False,
            },
            "observations": [
                {
                    "tick": {
                        "instrument_key": KEY,
                        "last_price": "100",
                        "last_trade_at": trade,
                        "last_quantity": 1,
                        "close_price": "99",
                        "indicative_price": None,
                        "quality_flags": [],
                        "freshness": "NOT_EVALUATED",
                        "signal_eligible": False,
                        "execution_eligible": False,
                    },
                    "trade_age_seconds": (received - trade).total_seconds(),
                    "freshness": "RECENT_TRADE",
                }
            ],
            "duplicates": 0,
            "out_of_order": 0,
            "detail": None,
            "signal_eligible": False,
            "execution_eligible": False,
            "health": [],
            "plan": None,
            "observed_at": received,
            "elapsed_ms": elapsed,
        }
    )


@pytest.mark.parametrize("reason", UNUSABLE_FRAME_REASONS)
def test_one_exclusive_reason_for_each_existing_frame_exclusion(reason):
    event = frame()
    policy = load_calendar()
    now = RECEIVED + timedelta(seconds=20)
    if reason == "OUTSIDE_REQUESTED_DATES":
        event = frame(RECEIVED - timedelta(days=1), age=-0.001)
    elif reason == "NO_REVIEWED_SESSION_WINDOW":
        policy = policy.model_copy(
            update={"kind": "SYNTHETIC_FIXTURE", "holidays": {DAY: "fixture"}}
        )
    elif reason == "OUTSIDE_REVIEWED_SESSION_WINDOW":
        event = frame(policy.day(DAY)["opens_at"] - timedelta(microseconds=1))
    elif reason == "RECEIPT_AT_OR_AFTER_REPORT_TIME":
        now = RECEIVED
    elif reason == "GENERATION_AFTER_RECEIPT":
        event = frame(age=-0.001)
    elif reason == "GENERATION_TOO_OLD":
        event = frame(age=10.000001)
    before = event.model_dump_json()
    samples = Samples()
    samples.accept(event, REQUEST, policy, now)
    assert samples.outside == 1 and sum(samples.unusable_reasons.values()) == 1
    assert samples.unusable_reasons[reason] == 1
    assert not samples.counts and not samples.intervals
    assert event.model_dump_json() == before


@pytest.mark.parametrize("age", [-0.000001, 0, 10, 10.000001])
@pytest.mark.parametrize("position", ["before_open", "inside", "at_close", "at_report_time"])
def test_frame_admission_matches_original_predicate_at_boundaries(age, position):
    policy = load_calendar()
    window = policy.day(DAY)
    received = {
        "before_open": window["opens_at"] - timedelta(microseconds=1),
        "inside": RECEIVED,
        "at_close": window["closes_at"],
        "at_report_time": RECEIVED,
    }[position]
    now = received if position == "at_report_time" else received + timedelta(seconds=20)
    event = frame(received, age)
    original_admission = (
        REQUEST.from_date <= received.date() <= REQUEST.to_date
        and window["opens_at"] <= received < min(window["closes_at"], now)
        and 0 <= age <= 10
    )
    samples = Samples()
    samples.accept(event, REQUEST, policy, now)
    assert (samples.counts.get((DAY, KEY), 0) == 1) is original_admission
    assert samples.outside == (0 if original_admission else 1)
    assert sum(samples.unusable_reasons.values()) == samples.outside


def test_rejection_clears_sample_continuity_and_does_not_bridge_a_bad_frame():
    samples = Samples()
    policy = load_calendar()
    now = RECEIVED + timedelta(seconds=20)
    samples.accept(frame(elapsed=1000), REQUEST, policy, now)
    samples.accept(frame(RECEIVED + timedelta(seconds=1), -0.001, 2000), REQUEST, policy, now)
    assert not samples.previous
    samples.accept(frame(RECEIVED + timedelta(seconds=2), 0, 3000), REQUEST, policy, now)
    assert samples.counts[(DAY, KEY)] == 2 and not samples.intervals
    assert samples.unusable_reasons["GENERATION_AFTER_RECEIPT"] == 1


def test_empty_observations_keep_legacy_aggregate_unchanged():
    samples = Samples()
    event = frame().model_copy(update={"observations": ()})
    samples.accept(event, REQUEST, load_calendar(), RECEIVED + timedelta(seconds=20))
    assert samples.outside == 0 and not any(samples.unusable_reasons.values())


def test_counters_are_isolated_between_samples_instances():
    first = Samples()
    second = Samples()
    first.accept(frame(age=-0.001), REQUEST, load_calendar(), RECEIVED + timedelta(seconds=20))
    assert first.unusable_reasons["GENERATION_AFTER_RECEIPT"] == 1
    assert not any(second.unusable_reasons.values())
