"""Synthetic reader outputs exercise progress boundaries, never real-day certification."""

from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import Mock

import pytest

from backend.app.market_data import initial_report
from backend.app.market_data.contracts import IST
from backend.app.market_data.coverage import CoverageRequest

START = date(2026, 11, 11)
END = date(2026, 11, 17)
OPEN = datetime.combine(START, time.min, IST)
CLOSE = datetime.combine(END + timedelta(days=1), time.min, IST)
KEY = "NSE_FO|synthetic-option"


def reader_output(as_of):
    days = []
    for index in range(7):
        day = START + timedelta(days=index)
        weekend = day.weekday() >= 5
        days.append(
            {
                "date": day,
                "state": "WEEKEND" if weekend else "REGULAR_BASELINE",
                "opens_at": None if weekend else datetime.combine(day, time(9, 15), IST),
                "closes_at": None if weekend else datetime.combine(day, time(15, 40), IST),
                "keys": [{"accepted_samples": 0, "sampled_interval_ms": 0}],
            }
        )
    return {
        "source": "UPSTOX_V3",
        "as_of": as_of,
        "session_ids": [],
        "counts": {"events": 0},
        "days": days,
        "calendar": {"kind": "OFFICIAL_BASELINE", "amendment_completeness_verified": False},
        "outside_or_unusable_frames": 0,
        "coverage_kind": "CONSERVATIVE_SAMPLED_SPANS",
        "qualifying_observation_days": 0,
    }


def report(monkeypatch, coverage, request=None):
    reader = Mock(return_value=coverage)
    monkeypatch.setattr(initial_report, "coverage_report", reader)
    engine = object()
    request = request or CoverageRequest(from_date=START, to_date=END, instrument_keys=(KEY,))
    result = initial_report.initial_observation_report(engine, request)
    reader.assert_called_once_with(engine, request)
    assert result["assessment"] == "NOT_CERTIFIED"
    assert result["qualifying_observation_days"] == 0
    assert not result["live_enabled"]
    assert not result["window_progress"]["review_complete"]
    assert not result["window_progress"]["phase2_complete"]
    assert not result["window_progress"]["requested_range_is_verified_observation_start"]
    assert not result["window_progress"]["minimum_coverage_threshold_defined"]
    return result


@pytest.mark.parametrize(
    ("as_of", "state", "elapsed", "seven_elapsed"),
    [
        (OPEN - timedelta(microseconds=1), "FUTURE", 0, False),
        (OPEN, "IN_PROGRESS", 0, False),
        (OPEN + timedelta(days=1), "IN_PROGRESS", 1, False),
        (CLOSE - timedelta(microseconds=1), "IN_PROGRESS", 6, False),
        (CLOSE, "ELAPSED", 7, True),
        (CLOSE + timedelta(days=1), "ELAPSED", 7, True),
    ],
)
def test_progress_uses_exact_ist_midnight_boundaries(
    monkeypatch, as_of, state, elapsed, seven_elapsed
):
    # UTC inputs straddle the previous UTC date at IST midnight.
    result = report(monkeypatch, reader_output(as_of.astimezone(UTC)))
    progress = result["window_progress"]
    assert progress["range_state"] == state
    assert progress["elapsed_calendar_dates"] == elapsed
    assert progress["remaining_calendar_dates"] == 7 - elapsed
    assert progress["seven_date_range_elapsed"] is seven_elapsed
    assert progress["starts_at_ist"] == OPEN and progress["ends_at_exclusive_ist"] == CLOSE
    assert ("REQUESTED_RANGE_NOT_ELAPSED" in progress["review_blockers"]) is (not seven_elapsed)
    assert "ACCEPTANCE_CRITERIA_REVIEW_REQUIRED" in progress["review_blockers"]
    assert "CALENDAR_AMENDMENTS_UNVERIFIED" in progress["review_blockers"]


def test_elapsed_empty_week_does_not_invent_missing_weekend_sessions(monkeypatch):
    result = report(monkeypatch, reader_output(CLOSE))
    progress = result["window_progress"]
    expected = [START + timedelta(days=i) for i in (0, 1, 2, 5, 6)]
    assert progress["calendar_session_dates"] == expected
    assert progress["elapsed_calendar_session_dates"] == expected
    assert progress["elapsed_session_dates_without_sampled_intervals"] == expected
    assert "ELAPSED_SESSION_DATES_WITHOUT_SAMPLED_INTERVALS" in progress["review_blockers"]


def test_open_session_is_not_reported_as_elapsed_missing_evidence(monkeypatch):
    result = report(monkeypatch, reader_output(datetime.combine(START, time(12), IST)))
    assert result["window_progress"]["elapsed_calendar_session_dates"] == []
    assert result["window_progress"]["elapsed_session_dates_without_sampled_intervals"] == []


def test_one_sampled_span_does_not_complete_a_day_or_require_every_key_every_date(monkeypatch):
    coverage = reader_output(CLOSE)
    coverage["days"][0]["keys"] = [
        {"accepted_samples": 2, "sampled_interval_ms": 307},
        {"accepted_samples": 0, "sampled_interval_ms": 0},
    ]
    coverage["days"][1]["keys"][0]["accepted_samples"] = 1  # No measured interval.
    result = report(monkeypatch, coverage)
    assert result["sampled_dates"] == [START]
    missing = result["window_progress"]["elapsed_session_dates_without_sampled_intervals"]
    assert START not in missing and START + timedelta(days=1) in missing


def test_unknown_and_synthetic_evidence_are_explicit(monkeypatch):
    coverage = reader_output(CLOSE)
    coverage["source"] = "SYNTHETIC"
    coverage["calendar"]["kind"] = "SYNTHETIC_FIXTURE"
    coverage["days"][0].update(state="UNKNOWN_HOURS", opens_at=None, closes_at=None)
    request = CoverageRequest(
        from_date=START, to_date=END, instrument_keys=(KEY,), source="SYNTHETIC"
    )
    result = report(monkeypatch, coverage, request)
    progress = result["window_progress"]
    assert progress["unknown_calendar_dates"] == [START]
    assert {"SYNTHETIC_SOURCE", "SYNTHETIC_CALENDAR", "UNKNOWN_CALENDAR_WINDOWS"} <= set(
        progress["review_blockers"]
    )
    assert START not in progress["elapsed_session_dates_without_sampled_intervals"]


def test_short_elapsed_filter_is_not_a_seven_date_window(monkeypatch):
    coverage = reader_output(CLOSE)
    coverage["days"] = coverage["days"][:1]
    request = CoverageRequest(from_date=START, to_date=START, instrument_keys=(KEY,))
    result = report(monkeypatch, coverage, request)
    progress = result["window_progress"]
    assert progress["range_state"] == "ELAPSED" and progress["elapsed_calendar_dates"] == 1
    assert not progress["seven_date_range_elapsed"]
    assert "SEVEN_CALENDAR_DATES_REQUIRED" in progress["review_blockers"]


def test_progress_does_not_mutate_reader_evidence_or_share_state(monkeypatch):
    coverage = reader_output(CLOSE)
    before = deepcopy(coverage)
    first = report(monkeypatch, coverage)
    first["window_progress"]["review_blockers"].clear()
    first["window_progress"]["calendar_session_dates"].clear()
    second = report(monkeypatch, coverage)
    assert coverage == before
    assert second["window_progress"]["review_blockers"]
    assert second["window_progress"]["calendar_session_dates"]


def test_holiday_and_dated_weekend_special_session_use_calendar_windows(monkeypatch):
    coverage = reader_output(CLOSE)
    coverage["days"][0].update(state="HOLIDAY", opens_at=None, closes_at=None)
    special = coverage["days"][3]
    special.update(
        state="SPECIAL_SESSION",
        opens_at=datetime.combine(special["date"], time(14, 20), IST),
        closes_at=datetime.combine(special["date"], time(15, 40), IST),
    )
    coverage["as_of"] = special["closes_at"]
    result = report(monkeypatch, coverage)
    dates = result["window_progress"]["elapsed_calendar_session_dates"]
    assert START not in dates and special["date"] in dates
    assert not result["window_progress"]["seven_date_range_elapsed"]


def test_samples_on_all_baseline_dates_still_require_acceptance_review(monkeypatch):
    coverage = reader_output(CLOSE)
    for day in coverage["days"]:
        if day["opens_at"]:
            day["keys"][0].update(accepted_samples=2, sampled_interval_ms=1)
    result = report(monkeypatch, coverage)
    progress = result["window_progress"]
    assert progress["seven_date_range_elapsed"]
    assert progress["elapsed_session_dates_without_sampled_intervals"] == []
    assert "ACCEPTANCE_CRITERIA_REVIEW_REQUIRED" in progress["review_blockers"]
