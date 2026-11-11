"""Synthetic ledger rows only; no market connection, recording or account access."""

import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.app.market_data import observation_budget as budget
from backend.app.market_data.observation_models import ObservationSession
from backend.app.market_data.supervision_models import CaptureRun
from scripts.observation_budget import local_budget

NOW = datetime(2026, 11, 11, 6, tzinfo=UTC)
REQUEST = budget.BudgetRequest(from_date=date(2026, 11, 11), to_date=date(2026, 11, 17))


def seed(
    engine,
    *,
    at=NOW,
    count=1,
    events=10,
    size=1000,
    sessions=1,
    source="UPSTOX_V3",
    status="CLOSED",
    standalone=False,
):
    with Session(engine) as db, db.begin():
        for _ in range(count):
            identity = uuid4().hex
            if not standalone:
                db.add(
                    CaptureRun(
                        id=identity,
                        source=source,
                        requested_keys=["NSE_FO|fixture"],
                        policy=budget.STANDARD_POLICY.model_dump(),
                        status=status,
                        created_at=at,
                        lease_expires_at=at + timedelta(seconds=120),
                        session_count=sessions,
                        event_count=events,
                        payload_bytes=size,
                        stats={},
                    )
                )
                db.flush()
            for index in range(sessions):
                db.add(
                    ObservationSession(
                        id=uuid4().hex,
                        supervisor_id=None if standalone else identity,
                        source=source,
                        schema_sha256="0" * 64,
                        requested_keys=["NSE_FO|fixture"],
                        policy={},
                        status=status,
                        created_at=at,
                        lease_expires_at=at + timedelta(seconds=120),
                        event_count=events // sessions + (index < events % sessions),
                        payload_bytes=size // sessions + (index < size % sessions),
                    )
                )


def checked(engine, *, now=NOW):
    result = budget.pilot_budget(engine, REQUEST, now=now)
    for flag in (
        "authorizes_capture",
        "reservation_created",
        "recording_started",
        "phase2_complete",
        "entries_enabled",
        "live_enabled",
        "daily_limit_enforced_by_recorder",
    ):
        assert result[flag] is False
    assert result["qualifying_observation_days"] == 0
    return result


def test_empty_budget_is_read_only_and_only_advisory(client):
    engine = client.app.state.engine
    statements = []

    def observed(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.upper())

    event.listen(engine, "before_cursor_execute", observed)
    try:
        result = checked(engine)
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert result["state"] == "BUDGET_AVAILABLE_FOR_RECHECK"
    assert result["remaining_standard_runs_today"] == 3
    assert result["remaining_window_run_slots_before_session_checks"] == 15
    assert len(result["baseline_session_dates"]) == 5
    assert all(s.lstrip().startswith("SELECT") for s in statements)
    assert not any(
        "OBSERVATION_EVENTS" in s or "REQUESTED_KEYS" in s or "CAPTURE_RUNS.POLICY" in s
        for s in statements
    )


def test_all_parent_outcomes_consume_daily_budget(client):
    engine = client.app.state.engine
    for status in ("CLOSED", "INTERRUPTED", "CLOSED"):
        seed(engine, status=status)
    result = checked(engine)
    assert result["window_usage"] == {"runs": 3, "sessions": 3, "events": 30, "payload_bytes": 3000}
    assert result["remaining_standard_runs_today"] == 0
    assert result["remaining_window_run_slots_before_session_checks"] == 12
    assert "DAILY_PILOT_BUDGET_EXHAUSTED" in result["blockers"]


def test_synthetic_history_is_not_credited_but_active_recordings_still_block(client):
    engine = client.app.state.engine
    seed(engine, count=3, source="SYNTHETIC")
    assert checked(engine)["window_usage"]["runs"] == 0
    seed(engine, at=NOW - timedelta(days=10), source="SYNTHETIC", status="RUNNING")
    result = checked(engine)
    assert result["window_usage"]["runs"] == 0
    assert result["active_recording_rows"] == 2
    assert "ACTIVE_OR_UNRESOLVED_RECORDING_PRESENT" in result["blockers"]


def test_standalone_genuine_sessions_cannot_bypass_the_budget(client):
    seed(client.app.state.engine, count=3, standalone=True)
    result = checked(client.app.state.engine)
    assert result["standalone_sessions_counted"] == 3
    assert result["window_usage"]["runs"] == 3 and result["remaining_standard_runs_today"] == 0


@pytest.mark.parametrize("changes", [{"events": 901}, {"size": 786433}, {"sessions": 4}])
def test_aggregate_daily_quotas_cannot_be_bypassed_by_one_large_parent(client, changes):
    seed(client.app.state.engine, **changes)
    result = checked(client.app.state.engine)
    assert result["remaining_standard_runs_today"] == 0
    assert "DAILY_PILOT_BUDGET_EXHAUSTED" in result["blockers"]


@pytest.mark.parametrize("changes", [{"events": 20000, "sessions": 2}, {"size": 8 * 1024 * 1024}])
def test_report_headroom_counts_other_dates_in_the_window(client, changes):
    seed(client.app.state.engine, **changes)
    result = checked(client.app.state.engine, now=NOW + timedelta(days=1))
    assert "REPORT_HEADROOM_EXHAUSTED" in result["blockers"]
    assert result["remaining_standard_runs_today"] == 0


def test_ist_midnight_buckets_are_distinct(client):
    # 18:30 UTC is the next IST date, not the UTC date.
    seed(client.app.state.engine, at=datetime(2026, 11, 11, 18, 29, 59, tzinfo=UTC))
    seed(client.app.state.engine, at=datetime(2026, 11, 11, 18, 30, tzinfo=UTC))
    result = checked(client.app.state.engine, now=NOW + timedelta(days=1))
    assert result["daily_usage"][0]["runs"] == 1 and result["daily_usage"][1]["runs"] == 1
    assert result["remaining_standard_runs_today"] == 2


def test_parent_child_ledger_mismatch_requires_review(client):
    from sqlalchemy import update

    engine = client.app.state.engine
    seed(engine)
    with engine.begin() as c:
        c.execute(update(CaptureRun).values(event_count=11))
    assert "BUDGET_LEDGER_REVIEW_REQUIRED" in checked(engine)["blockers"]


def test_overlapping_external_session_requires_review_and_counts_report_bytes(client):
    seed(client.app.state.engine, at=datetime(2026, 11, 10, 18, 29, 59, tzinfo=UTC))
    result = checked(client.app.state.engine)
    assert result["window_usage"]["runs"] == 0
    assert result["conservative_report_usage_all_keys"]["payload_bytes"] == 1000
    assert "BUDGET_LEDGER_REVIEW_REQUIRED" in result["blockers"]


@pytest.mark.parametrize(
    "now", [NOW - timedelta(days=1), NOW + timedelta(days=3), NOW + timedelta(days=7)]
)
def test_nonplanned_dates_do_not_have_today_slots(client, now):
    result = checked(client.app.state.engine, now=now)
    assert result["remaining_standard_runs_today"] == 0
    assert "NO_PLANNED_SESSION_DATE" in result["blockers"]


def test_unknown_calendar_and_naive_time_fail_closed(client):
    engine = client.app.state.engine
    unknown = budget.BudgetRequest(from_date=date(2027, 1, 4), to_date=date(2027, 1, 10))
    result = budget.pilot_budget(engine, unknown, now=datetime(2027, 1, 4, tzinfo=UTC))
    assert "CALENDAR_BUDGET_REVIEW_REQUIRED" in result["blockers"]
    with pytest.raises(budget.BudgetError, match="AWARE_BUDGET_TIME_REQUIRED"):
        budget.pilot_budget(engine, REQUEST, now=NOW.replace(tzinfo=None))


def test_bounded_ledger_refuses_truncation(client, monkeypatch):
    seed(client.app.state.engine, count=3)
    monkeypatch.setattr(budget, "MAX_SESSIONS", 2)
    with pytest.raises(budget.BudgetError, match="BUDGET_LEDGER_ROW_LIMIT"):
        checked(client.app.state.engine)


@pytest.mark.parametrize(
    "start,end",
    [(date(2026, 11, 11), date(2026, 11, 18)), (date(2026, 11, 12), date(2026, 11, 11))],
)
def test_budget_range_is_bounded(start, end):
    with pytest.raises(ValidationError):
        budget.BudgetRequest(from_date=start, to_date=end)


def response_payload():
    return {
        "report_kind": "OBSERVATION_PILOT_BUDGET",
        "state": "BUDGET_BLOCKED",
        "blockers": ["DAILY_PILOT_BUDGET_EXHAUSTED"],
        **{
            name: False
            for name in (
                "authorizes_capture",
                "reservation_created",
                "recording_started",
                "phase2_complete",
                "entries_enabled",
                "live_enabled",
            )
        },
    }


def test_local_forwarding_uses_only_trusted_budget_source(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/observation_budget.py").write_text("# trusted read-only budget")
    payload = response_payload()
    with (
        patch("scripts.bootstrap_local.ROOT", tmp_path),
        patch("scripts.capture_local.local_container", return_value=("docker", "app")),
        patch(
            "scripts.observation_budget.subprocess.run",
            return_value=subprocess.CompletedProcess([], 2, json.dumps(payload), ""),
        ) as run,
    ):
        assert local_budget(REQUEST) == payload
    command = run.call_args.args[0]
    assert "--env" not in command and "--local" not in command
    assert command[-4:] == ["--from-date", "2026-11-11", "--to-date", "2026-11-17"]
    assert run.call_args.kwargs["input"] == "# trusted read-only budget"


@pytest.mark.parametrize("case", ["bad_json", "failure", "wrong_kind", "active_flag", "wrong_exit"])
def test_local_response_failures_do_not_become_budget_availability(tmp_path, case):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/observation_budget.py").write_text("# trusted budget")
    payload = response_payload()
    code = 2
    if case == "wrong_kind":
        payload["report_kind"] = "unexpected"
    if case == "active_flag":
        payload["authorizes_capture"] = True
    if case in {"failure", "wrong_exit"}:
        code = 1 if case == "failure" else 0
    body = "invalid" if case == "bad_json" else json.dumps(payload)
    with (
        patch("scripts.bootstrap_local.ROOT", tmp_path),
        patch("scripts.capture_local.local_container", return_value=("docker", "app")),
        patch(
            "scripts.observation_budget.subprocess.run",
            return_value=subprocess.CompletedProcess([], code, body, "withheld upstream details"),
        ),
        pytest.raises(ValueError),
    ):
        local_budget(REQUEST)
