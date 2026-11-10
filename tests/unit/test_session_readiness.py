import copy
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest

from backend.app.market_data import session_readiness as readiness
from backend.app.market_data.calendar import CalendarError, load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.supervision_store import CapturePolicy
from scripts import market_session_check as cli

NOW = datetime(2026, 11, 11, 4, 0, tzinfo=UTC)  # Synthetic time, not captured evidence.
KEY = "NSE_FO|synthetic-option"


def preflight(now=NOW):
    return {
        "state": "LOCAL_CHECKS_PASSED",
        "can_attempt_capture": True,
        "checked_at": now,
        "blockers": [],
        "checks": {
            "database": "POSTGRESQL_REACHABLE",
            "schema": "CURRENT",
            "metadata": "CURRENT_KEYS_RESOLVED",
            "write_privileges": "TABLE_GRANTS_PRESENT",
        },
        "requested_keys": [KEY],
        "policy": CapturePolicy(total_seconds=20, session_seconds=20, max_sessions=1).model_dump(),
        "calendar": {"policy_id": load_calendar().identity},
        "recording_started": False,
        "entries_enabled": False,
        "live_enabled": False,
        "signal_eligible": False,
        "execution_eligible": False,
    }


def test_ready_is_only_an_attempt_not_broker_proof_or_observation_certification():
    original = preflight()
    before = copy.deepcopy(original)
    result = readiness.market_session_readiness(original, now=NOW)
    assert result["state"] == "READY_FOR_REVIEWED_SESSION_ATTEMPT"
    assert result["can_attempt_market_hours_capture"]
    assert result["qualifying_observation_days"] == 0
    for flag in (
        "broker_access_verified",
        "recording_started",
        "phase2_complete",
        "entries_enabled",
        "live_enabled",
        "signal_eligible",
        "execution_eligible",
    ):
        assert result[flag] is False
    assert "CALENDAR_AMENDMENT_COMPLETENESS" in result["unverified"]
    assert original == before


@pytest.mark.parametrize(
    "boundary,expected",
    [
        ("before-open", "OUTSIDE_REVIEWED_SESSION"),
        ("at-open", None),
        ("fits-exactly", None),
        ("too-long", "REQUEST_EXCEEDS_SESSION_WINDOW"),
        ("at-close", "OUTSIDE_REVIEWED_SESSION"),
    ],
)
def test_exact_session_boundaries_and_whole_requested_window(boundary, expected):
    day = load_calendar().day(date(2026, 11, 11))
    opened, closed = day["opens_at"], day["closes_at"]
    now = {
        "before-open": opened - timedelta(seconds=1),
        "at-open": opened,
        "fits-exactly": closed - timedelta(seconds=20),
        "too-long": closed - timedelta(seconds=19),
        "at-close": closed,
    }[boundary]
    result = readiness.market_session_readiness(preflight(now), now=now)
    assert result["can_attempt_market_hours_capture"] is (expected is None)
    if expected:
        assert expected in result["blockers"]


@pytest.mark.parametrize(
    "day", [date(2026, 11, 7), date(2026, 11, 10), date(2026, 11, 5), date(2027, 1, 4)]
)
def test_weekend_holiday_unknown_hours_and_unknown_year_never_ready(day):
    now = datetime.combine(day, NOW.timetz())
    result = readiness.market_session_readiness(preflight(now), now=now)
    assert "NO_REVIEWED_SESSION" in result["blockers"]
    assert not result["can_attempt_market_hours_capture"]


def test_special_session_uses_actual_reviewed_hours():
    now = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    result = readiness.market_session_readiness(preflight(now), now=now)
    assert result["can_attempt_market_hours_capture"]
    assert result["session"]["state"] == "SPECIAL_SESSION"
    assert result["session"]["opens_at"].astimezone(IST).hour == 14


@pytest.mark.parametrize("age", [31, -3])
def test_stale_or_future_preflight_cannot_be_reused(age):
    result = readiness.market_session_readiness(preflight(NOW - timedelta(seconds=age)), now=NOW)
    assert "PREFLIGHT_CLOCK_OR_AGE_INVALID" in result["blockers"]


@pytest.mark.parametrize(
    "kind",
    [
        "missing-key",
        "index",
        "mixed",
        "stale-catalog",
        "privilege",
        "credential",
        "unsafe",
        "calendar",
        "bad-clock",
        "malformed",
    ],
)
def test_underlying_failures_and_invalid_evidence_fail_closed_without_error_echo(kind):
    source = preflight()
    if kind == "missing-key":
        source["requested_keys"] = []
    elif kind in {"index", "mixed"}:
        source["requested_keys"] = ["NSE_INDEX|synthetic-index"] + (
            [KEY] if kind == "mixed" else []
        )
    elif kind == "stale-catalog":
        source["checks"]["metadata"] = "STALE_METADATA"
    elif kind == "privilege":
        source["checks"]["write_privileges"] = "MISSING"
    elif kind == "credential":
        source.update(can_attempt_capture=False, state="BLOCKED", blockers=["CREDENTIAL_EXPIRED"])
    elif kind == "unsafe":
        source["execution_eligible"] = True
    elif kind == "calendar":
        source["calendar"]["policy_id"] = "different"
    elif kind == "bad-clock":
        source["checked_at"] = NOW.replace(tzinfo=None)
    else:
        source["policy"] = {"unknown": "synthetic-private-value"}
    result = readiness.market_session_readiness(source, now=NOW)
    assert result["blockers"] and not result["can_attempt_market_hours_capture"]
    assert "synthetic-private-value" not in json.dumps(result, default=str)
    if kind == "credential":
        assert "CREDENTIAL_EXPIRED" in result["blockers"]


def test_calendar_hash_failure_or_synthetic_calendar_never_ready(monkeypatch):
    original = preflight()
    monkeypatch.setattr(
        readiness, "load_calendar", Mock(side_effect=CalendarError("synthetic-private-value"))
    )
    result = readiness.market_session_readiness(original, now=NOW)
    assert "SESSION_READINESS_INPUT_OR_EVIDENCE_INVALID" in result["blockers"]
    assert "synthetic-private-value" not in json.dumps(result, default=str)
    monkeypatch.setattr(
        readiness,
        "load_calendar",
        lambda: load_calendar().model_copy(update={"kind": "SYNTHETIC_FIXTURE"}),
    )
    assert (
        "REVIEWED_CALENDAR_MISMATCH"
        in readiness.market_session_readiness(original, now=NOW)["blockers"]
    )


def test_local_wrapper_can_only_request_preflight_not_recording(monkeypatch, tmp_path):
    original = preflight()
    capture = Mock(return_value=(0, original))
    monkeypatch.setattr(cli, "capture_local", capture)
    check = Mock(return_value={"state": "BLOCKED"})
    monkeypatch.setattr(cli, "market_session_readiness", check)
    request, policy = FeedRequest(instrument_keys=(KEY,)), CapturePolicy()
    assert cli.check_local(tmp_path, request, policy) == {"state": "BLOCKED"}
    capture.assert_called_once_with(tmp_path, request, policy, preflight_only=True)
    check.assert_called_once_with(original)
