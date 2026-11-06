"""Secret-free local capture diagnostics. No broker requests, DB writes or permissions granted."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.config import Settings
from backend.app.database import SCHEMA_REVISION
from backend.app.market_data.calendar import CalendarError, load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.feed import FeedError, FeedPlan, FeedRequest, resolve_feed_catalog
from backend.app.market_data.feed_lifecycle import FeedEvent
from backend.app.market_data.observation_models import ObservationSession
from backend.app.market_data.observations import event_payload_bytes
from backend.app.market_data.supervision_models import CaptureRun
from backend.app.market_data.supervision_store import CapturePolicy
from backend.app.schema import SchemaMismatch, verify_schema

ACTIONS = {
    "OBSERVATION_MODE_REQUIRED": "Set TRADING_MODE=OBSERVATION in protected local configuration.",
    "LIVE_FLAG_INVALID": "Keep live execution disabled; review local configuration.",
    "CREDENTIAL_MISSING": "Run python -m scripts.configure_upstox locally; keep tokens private.",
    "CREDENTIAL_EXPIRED": "Replace the expired credential with the local setup helper.",
    "CREDENTIAL_WINDOW_TOO_SHORT": "Use a credential valid for this run plus 60 seconds.",
    "DATABASE_UNAVAILABLE": "Start the database and check protected connection settings.",
    "DATABASE_TEST_ONLY": "Use PostgreSQL; SQLite is for synthetic tests.",
    "DATABASE_PRIVILEGES_MISSING": "Review the application role capture-table grants.",
    "SCHEMA_REVISION_MISMATCH": "Apply python -m alembic upgrade head to the configured database.",
    "SCHEMA_UNAVAILABLE": "Apply migrations and verify table read permissions.",
    "CURRENT_CATALOG_REQUIRED": "Import current metadata before capture.",
    "FEED_KEY_NOT_IN_CATALOG": "Use instrument keys present in the current imported catalog.",
    "UNSUPPORTED_FEED_INSTRUMENT": "Select catalog indices or unexpired CE/PE contracts.",
    "EXPIRED_FEED_INSTRUMENT": "Select an unexpired contract from current metadata.",
    "LOCAL_CAPTURE_PRESENT": "Inspect active capture records before another run.",
    "CALENDAR_EVIDENCE_INVALID": "Restore and review the bundled calendar evidence hashes.",
    "CALENDAR_UNKNOWN": "Review the derivatives calendar for this date.",
    "BYTE_QUOTA_BELOW_PLAN_RESERVE": "Increase the byte budget for the initial PLAN record.",
    "EVENT_QUOTA_BELOW_INITIAL_SEQUENCE": "Allow at least three initial events.",
}

# SELECT is checked by schema/catalog queries; these are the write privileges the recorder uses.
WRITE_PERMISSIONS = (
    ("capture_runs", "INSERT"),
    ("capture_runs", "UPDATE"),
    ("observation_sessions", "INSERT"),
    ("observation_sessions", "UPDATE"),
    ("observation_attempts", "INSERT"),
    ("observation_events", "INSERT"),
)


def capture_preflight(
    engine: Engine,
    settings: Settings,
    request: FeedRequest,
    policy: CapturePolicy,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Aware preflight time required")
    blockers: list[str] = []
    warnings = ["BROKER_ACCEPTANCE_UNVERIFIED", "ACCOUNT_CONNECTION_COORDINATION_UNVERIFIED"]
    checks: dict[str, Any] = {
        "configuration": "VALIDATED",
        "required_schema": SCHEMA_REVISION,
        "database": "NOT_CHECKED",
        "schema": "NOT_CHECKED",
        "metadata": "NOT_CHECKED",
        "write_privileges": "NOT_CHECKED",
        "credential": "NOT_CONFIGURED",
    }
    if settings.trading_mode != "OBSERVATION":
        blockers.append("OBSERVATION_MODE_REQUIRED")
    if settings.live_enabled is not False:
        blockers.append("LIVE_FLAG_INVALID")
    if not settings.admin_password_hash.get_secret_value():
        warnings.append("ADMIN_DASHBOARD_UNCONFIGURED")
    expires = settings.upstox_analytics_expires_at
    if not settings.upstox_analytics_token.get_secret_value() or expires is None:
        blockers.append("CREDENTIAL_MISSING")
    elif expires <= now:
        checks["credential"] = "EXPIRED"
        blockers.append("CREDENTIAL_EXPIRED")
    elif expires <= now + timedelta(seconds=policy.total_seconds + 60):
        checks["credential"] = "EXPIRING_DURING_REQUESTED_WINDOW"
        blockers.append("CREDENTIAL_WINDOW_TOO_SHORT")
    else:
        checks["credential"] = "CONFIGURED_OPERATOR_DECLARED"
    calendar: dict[str, Any] | None = None
    try:
        calendar_policy = load_calendar()
        day = calendar_policy.day(now.astimezone(IST).date())
        calendar = {
            "policy_id": calendar_policy.identity,
            "kind": calendar_policy.kind,
            "reviewed_at": calendar_policy.reviewed_at,
            "today": day,
            "amendment_completeness_verified": False,
        }
        warnings.append("CALENDAR_REVIEW_BASELINE_ONLY")
        if any(key.startswith("NSE_FO|") for key in request.instrument_keys):
            if day["state"] in {"UNKNOWN_CALENDAR", "UNKNOWN_HOURS"}:
                blockers.append("CALENDAR_UNKNOWN")
            elif not day["opens_at"] or not day["opens_at"] <= now < day["closes_at"]:
                warnings.append("OUTSIDE_REVIEWED_SESSION")
        if any(key.startswith("NSE_INDEX|") for key in request.instrument_keys):
            warnings.append("INDEX_REFERENCE_CALENDAR_UNVERIFIED")
    except CalendarError:
        blockers.append("CALENDAR_EVIDENCE_INVALID")
    plan: FeedPlan | None = None
    isolation = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"
    try:
        with engine.connect().execution_options(isolation_level=isolation) as connection:
            with connection.begin(), Session(bind=connection) as db:
                if engine.dialect.name == "postgresql":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                    connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                    checks["database"] = "POSTGRESQL_REACHABLE"
                else:
                    checks["database"] = "TEST_DATABASE"
                    blockers.append("DATABASE_TEST_ONLY")
                try:
                    verify_schema(connection)
                    checks["schema"] = "CURRENT"
                except SchemaMismatch:
                    checks["schema"] = "REVISION_MISMATCH"
                    blockers.append("SCHEMA_REVISION_MISMATCH")
                except SQLAlchemyError:
                    checks["schema"] = "UNAVAILABLE"
                    blockers.append("SCHEMA_UNAVAILABLE")
                    # A missing relation aborts PostgreSQL's read-only transaction.
                    raise
                if checks["schema"] == "CURRENT":
                    if engine.dialect.name == "postgresql":
                        privileges = [
                            bool(
                                connection.scalar(
                                    text(
                                        "SELECT has_table_privilege(current_user,:table,:privilege)"
                                    ),
                                    {"table": table, "privilege": privilege},
                                )
                            )
                            for table, privilege in WRITE_PERMISSIONS
                        ]
                        checks["write_privileges"] = (
                            "TABLE_GRANTS_PRESENT" if all(privileges) else "MISSING"
                        )
                        if not all(privileges):
                            blockers.append("DATABASE_PRIVILEGES_MISSING")
                    try:
                        plan = resolve_feed_catalog(db, request)
                        checks["metadata"] = "CURRENT_KEYS_RESOLVED"
                    except FeedError as error:
                        code = str(error)
                        checks["metadata"] = code
                        blockers.append(code if code in ACTIONS else "CURRENT_CATALOG_REQUIRED")
                    active_parent = db.scalar(
                        select(CaptureRun.id)
                        .where(CaptureRun.status == "RUNNING", CaptureRun.lease_expires_at > now)
                        .limit(1)
                    )
                    active_child = db.scalar(
                        select(ObservationSession.id)
                        .where(
                            ObservationSession.status == "RUNNING",
                            ObservationSession.lease_expires_at > now,
                        )
                        .limit(1)
                    )
                    if active_parent or active_child:
                        blockers.append("LOCAL_CAPTURE_PRESENT")
    except SQLAlchemyError:
        if "SCHEMA_UNAVAILABLE" not in blockers:
            blockers.append("DATABASE_UNAVAILABLE")
        checks["database"] = "CHECK_FAILED"
    if policy.max_events < 3:
        blockers.append("EVENT_QUOTA_BELOW_INITIAL_SEQUENCE")
    reserve = None
    if plan:
        reserve = (
            event_payload_bytes(FeedEvent("PLAN", 1, plan=plan, observed_at=now, elapsed_ms=0)) + 64
        )
        if policy.max_payload_bytes < reserve:
            blockers.append("BYTE_QUOTA_BELOW_PLAN_RESERVE")
    if policy.total_seconds < 30:
        warnings.append("SHORT_CAPTURE_WINDOW")
    if policy.total_seconds < policy.max_sessions + 30 * (policy.max_sessions - 1):
        warnings.append("SESSION_CAP_EXCEEDS_MINIMUM_TIME_BUDGET")
    if policy.max_events > 20_000 or policy.max_payload_bytes > 8 * 1024 * 1024:
        warnings.append("CAPTURE_QUOTAS_EXCEED_SINGLE_COVERAGE_REPORT_BOUNDS")
    blockers = list(dict.fromkeys(blockers))
    return {
        "state": "BLOCKED" if blockers else "LOCAL_CHECKS_PASSED",
        "checked_at": now,
        "can_attempt_capture": not blockers,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "next_actions": [ACTIONS[code] for code in blockers if code in ACTIONS],
        "requested_keys": list(request.instrument_keys),
        "policy": policy.model_dump(),
        "plan_reserve_bytes": reserve,
        "catalog_snapshot_id": plan.catalog_snapshot_id if plan else None,
        "calendar": calendar,
        "broker_access_verified": False,
        "database_writes_verified": False,
        "recording_started": False,
        "observation_started_at": None,
        "qualifying_observation_days": 0,
        "entries_enabled": False,
        "live_enabled": False,
        "signal_eligible": False,
        "execution_eligible": False,
    }
