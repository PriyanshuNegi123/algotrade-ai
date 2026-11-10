"""Read-only gate for a bounded derivatives market-hours attempt, never day certification."""

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.market_data.calendar import load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.preflight import ACTIONS
from backend.app.market_data.supervision_store import CapturePolicy


def market_session_readiness(
    preflight: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Aware readiness time required")
    result: dict[str, Any] = {
        "state": "BLOCKED",
        "checked_at": now,
        "can_attempt_market_hours_capture": False,
        "blockers": [],
        "session": None,
        "requested_keys": [],
        "requested_seconds": None,
        "remaining_session_seconds": None,
        "unverified": [
            "BROKER_FRESH_UPDATES",
            "REAL_RECONNECT",
            "CALENDAR_AMENDMENT_COMPLETENESS",
            "SEVEN_CALENDAR_DAY_OBSERVATION",
        ],
        "broker_access_verified": False,
        "recording_started": False,
        "qualifying_observation_days": 0,
        "phase2_complete": False,
        "entries_enabled": False,
        "live_enabled": False,
        "signal_eligible": False,
        "execution_eligible": False,
    }
    blockers = result["blockers"]
    try:
        # Do not echo unknown payload values or upstream error text into the report.
        source_blockers = preflight["blockers"]
        if not isinstance(source_blockers, list) or len(source_blockers) > 100:
            raise ValueError
        blockers.extend(
            code for code in source_blockers if isinstance(code, str) and code in ACTIONS
        )
        if (
            preflight.get("state") != "LOCAL_CHECKS_PASSED"
            or preflight.get("can_attempt_capture") is not True
            or source_blockers
        ):
            blockers.append("LOCAL_PREFLIGHT_NOT_READY")
        for flag in ("entries_enabled", "live_enabled", "signal_eligible", "execution_eligible"):
            if preflight.get(flag) is not False:
                raise ValueError
        if preflight.get("recording_started") is not False:
            raise ValueError
        checked = preflight["checked_at"]
        checked = datetime.fromisoformat(checked) if isinstance(checked, str) else checked
        if not isinstance(checked, datetime) or checked.tzinfo is None:
            raise ValueError
        if checked > now + timedelta(seconds=2) or now - checked > timedelta(seconds=30):
            blockers.append("PREFLIGHT_CLOCK_OR_AGE_INVALID")
        request = FeedRequest(instrument_keys=preflight["requested_keys"])
        policy = CapturePolicy.model_validate(preflight["policy"])
        result.update(
            requested_keys=list(request.instrument_keys), requested_seconds=policy.total_seconds
        )
        if any(not key.startswith("NSE_FO|") for key in request.instrument_keys):
            blockers.append("DERIVATIVE_KEYS_REQUIRED_FOR_ACCEPTANCE")
        checks = preflight["checks"]
        required = {
            "database": "POSTGRESQL_REACHABLE",
            "schema": "CURRENT",
            "metadata": "CURRENT_KEYS_RESOLVED",
            "write_privileges": "TABLE_GRANTS_PRESENT",
        }
        if any(checks.get(name) != value for name, value in required.items()):
            blockers.append("LOCAL_PREFLIGHT_NOT_READY")
        calendar = load_calendar()
        if (
            calendar.kind != "OFFICIAL_BASELINE"
            or preflight["calendar"]["policy_id"] != calendar.identity
        ):
            blockers.append("REVIEWED_CALENDAR_MISMATCH")
        day = calendar.day(now.astimezone(IST).date())
        result["session"] = day
        if day["state"] not in {"REGULAR_BASELINE", "SPECIAL_SESSION"}:
            blockers.append("NO_REVIEWED_SESSION")
        else:
            opens, closes = day["opens_at"], day["closes_at"]
            result["remaining_session_seconds"] = max(
                0, int((closes - max(now, opens)).total_seconds())
            )
            if not opens <= now < closes:
                blockers.append("OUTSIDE_REVIEWED_SESSION")
            elif now + timedelta(seconds=policy.total_seconds) > closes:
                blockers.append("REQUEST_EXCEEDS_SESSION_WINDOW")
    except Exception:
        # Invalid local evidence/configuration must never turn into attempt permission.
        blockers.append("SESSION_READINESS_INPUT_OR_EVIDENCE_INVALID")
    result["blockers"] = list(dict.fromkeys(blockers))
    if not result["blockers"]:
        result.update(
            state="READY_FOR_REVIEWED_SESSION_ATTEMPT", can_attempt_market_hours_capture=True
        )
    return result
