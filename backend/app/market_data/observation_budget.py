"""Read-only pilot ledger diagnostics; no reservation, capture or trading authorization."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine

from backend.app.instruments.service import aware
from backend.app.market_data.calendar import load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.coverage import MAX_BYTES, MAX_EVENTS, MAX_SESSIONS
from backend.app.market_data.observation_models import ObservationSession
from backend.app.market_data.supervision_models import CaptureRun
from backend.app.market_data.supervision_store import CapturePolicy

DAILY_RUNS = 3
STANDARD_POLICY = CapturePolicy(
    total_seconds=120,
    session_seconds=120,
    max_sessions=1,
    max_events=300,
    max_payload_bytes=262144,
)


class BudgetError(Exception):
    pass


class BudgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    from_date: date
    to_date: date

    @model_validator(mode="after")
    def bounds(self) -> "BudgetRequest":
        if (
            self.from_date.year < 1970
            or self.to_date.year > 9998
            or self.to_date < self.from_date
            or (self.to_date - self.from_date).days >= 7
        ):
            raise ValueError("Budget range exceeds seven dates")
        return self


def pilot_budget(
    engine: Engine, request: BudgetRequest, *, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise BudgetError("AWARE_BUDGET_TIME_REQUIRED")
    calendar = load_calendar()
    days = [
        request.from_date + timedelta(days=i)
        for i in range((request.to_date - request.from_date).days + 1)
    ]
    windows = [calendar.day(day) for day in days]
    eligible = [w["date"] for w in windows if w["opens_at"] and w["closes_at"]]
    start = datetime.combine(request.from_date, time.min, IST).astimezone(UTC)
    end = datetime.combine(request.to_date + timedelta(days=1), time.min, IST).astimezone(UTC)
    isolation = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"
    with engine.connect().execution_options(isolation_level=isolation) as connection:
        with connection.begin():
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            parents = list(
                connection.execute(
                    select(
                        CaptureRun.id,
                        CaptureRun.created_at,
                        CaptureRun.session_count,
                        CaptureRun.event_count,
                        CaptureRun.payload_bytes,
                    )
                    .where(
                        CaptureRun.source == "UPSTOX_V3",
                        CaptureRun.created_at >= start,
                        CaptureRun.created_at < end,
                    )
                    .order_by(CaptureRun.id)
                    .limit(MAX_SESSIONS + 1)
                ).mappings()
            )
            children = list(
                connection.execute(
                    select(
                        ObservationSession.supervisor_id,
                        ObservationSession.created_at,
                        ObservationSession.event_count,
                        ObservationSession.payload_bytes,
                    )
                    .where(
                        ObservationSession.source == "UPSTOX_V3",
                        ObservationSession.created_at < end,
                        ObservationSession.lease_expires_at >= start,
                    )
                    .order_by(ObservationSession.id)
                    .limit(MAX_SESSIONS + 1)
                ).mappings()
            )
            if len(parents) > MAX_SESSIONS or len(children) > MAX_SESSIONS:
                raise BudgetError("BUDGET_LEDGER_ROW_LIMIT")
            active = sum(
                connection.scalar(
                    select(func.count()).select_from(model).where(model.status == "RUNNING")
                )
                or 0
                for model in (CaptureRun, ObservationSession)
            )
    usage = {day: {"runs": 0, "sessions": 0, "events": 0, "payload_bytes": 0} for day in days}
    blockers = []
    if calendar.kind != "OFFICIAL_BASELINE" or any(
        w["state"] in {"UNKNOWN_CALENDAR", "UNKNOWN_HOURS"} for w in windows
    ):
        blockers.append("CALENDAR_BUDGET_REVIEW_REQUIRED")
    parent_ids = {p["id"] for p in parents}
    for parent in parents:
        bucket = usage[aware(parent["created_at"]).astimezone(IST).date()]
        bucket["runs"] += 1  # Closed, failed and interrupted parents all consume a slot.
        bucket["sessions"] += parent["session_count"]
        bucket["events"] += parent["event_count"]
        bucket["payload_bytes"] += parent["payload_bytes"]
        linked = [child for child in children if child["supervisor_id"] == parent["id"]]
        if (
            len(linked) != parent["session_count"]
            or sum(c["event_count"] for c in linked) != parent["event_count"]
            or sum(c["payload_bytes"] for c in linked) != parent["payload_bytes"]
        ):
            blockers.append("BUDGET_LEDGER_REVIEW_REQUIRED")
    standalone = 0
    for child in children:
        day = aware(child["created_at"]).astimezone(IST).date()
        if child["supervisor_id"] is None and day in usage:
            standalone += 1
            bucket = usage[day]
            bucket["runs"] += 1
            bucket["sessions"] += 1
            bucket["events"] += child["event_count"]
            bucket["payload_bytes"] += child["payload_bytes"]
        elif child["supervisor_id"] not in parent_ids:
            blockers.append("BUDGET_LEDGER_REVIEW_REQUIRED")
    today = now.astimezone(IST).date()
    current = usage.get(today, {"runs": 0, "sessions": 0, "events": 0, "payload_bytes": 0})
    totals = {key: sum(day[key] for day in usage.values()) for key in current}
    report_usage = {
        "sessions": len(children),
        "events": sum(c["event_count"] for c in children),
        "payload_bytes": sum(c["payload_bytes"] for c in children),
    }
    report_slots = min(
        MAX_SESSIONS - report_usage["sessions"],
        (MAX_EVENTS - report_usage["events"]) // STANDARD_POLICY.max_events,
        (MAX_BYTES - report_usage["payload_bytes"]) // STANDARD_POLICY.max_payload_bytes,
    )
    remaining_today = min(
        DAILY_RUNS - current["runs"],
        DAILY_RUNS - current["sessions"],
        (DAILY_RUNS * STANDARD_POLICY.max_events - current["events"]) // STANDARD_POLICY.max_events,
        (DAILY_RUNS * STANDARD_POLICY.max_payload_bytes - current["payload_bytes"])
        // STANDARD_POLICY.max_payload_bytes,
    )
    window_runs = len(eligible) * DAILY_RUNS
    window_slots = min(
        window_runs - totals["runs"],
        window_runs - totals["sessions"],
        (window_runs * STANDARD_POLICY.max_events - totals["events"]) // STANDARD_POLICY.max_events,
        (window_runs * STANDARD_POLICY.max_payload_bytes - totals["payload_bytes"])
        // STANDARD_POLICY.max_payload_bytes,
    )
    if today not in eligible:
        blockers.append("NO_PLANNED_SESSION_DATE")
    if remaining_today <= 0:
        blockers.append("DAILY_PILOT_BUDGET_EXHAUSTED")
    if window_slots <= 0:
        blockers.append("WINDOW_RUN_BUDGET_EXHAUSTED")
    if report_slots <= 0:
        blockers.append("REPORT_HEADROOM_EXHAUSTED")
    if active:
        blockers.append("ACTIVE_OR_UNRESOLVED_RECORDING_PRESENT")
    return {
        "report_kind": "OBSERVATION_PILOT_BUDGET",
        "state": "BUDGET_BLOCKED" if blockers else "BUDGET_AVAILABLE_FOR_RECHECK",
        "checked_at": now,
        "from_date": request.from_date,
        "to_date": request.to_date,
        "source": "UPSTOX_V3",
        "standard_policy": STANDARD_POLICY.model_dump(),
        "calendar_id": calendar.identity,
        "calendar_amendment_completeness_verified": False,
        "baseline_session_dates": eligible,
        "daily_usage": [{"date": day, **used} for day, used in usage.items()],
        "window_usage": totals,
        "standalone_sessions_counted": standalone,
        "active_recording_rows": active,
        "conservative_report_usage_all_keys": report_usage,
        "remaining_standard_runs_today": max(0, min(remaining_today, window_slots, report_slots))
        if today in eligible
        else 0,
        "remaining_window_run_slots_before_session_checks": max(0, min(window_slots, report_slots)),
        "blockers": list(dict.fromkeys(blockers)),
        "daily_limit_enforced_by_recorder": False,
        "reservation_created": False,
        "authorizes_capture": False,
        "recording_started": False,
        "qualifying_observation_days": 0,
        "phase2_complete": False,
        "entries_enabled": False,
        "live_enabled": False,
    }
