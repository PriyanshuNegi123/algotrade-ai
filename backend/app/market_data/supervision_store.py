"""Parent quota ledger; acquire its row before any linked observation-session lock."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.instruments.service import aware
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.observation_models import ObservationSession
from backend.app.market_data.observation_schema import CapturedEvent
from backend.app.market_data.supervision_models import CaptureRun


class CapturePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    total_seconds: int = Field(default=600, ge=1, le=3600)
    session_seconds: int = Field(default=300, ge=1, le=300)
    max_sessions: int = Field(default=3, ge=1, le=12)
    max_payload_bytes: int = Field(default=8 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)
    max_events: int = Field(default=20_000, ge=1, le=100_000)


class CaptureError(Exception):
    pass


def request_capture_stop(engine: Engine, identity: str) -> dict[str, Any]:
    """Request one parent's cooperative stop; never signal a PID or alter child state."""
    if re.fullmatch(r"[0-9a-f]{32}", identity) is None:
        raise CaptureError("INVALID_CAPTURE_ID")
    with Session(engine) as db, db.begin():
        if engine.dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = '1000ms'"))
            db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
        row = lock_capture(db, identity)
        active = row.status == "RUNNING" and datetime.now(UTC) < aware(row.lease_expires_at)
        if active and not row.stats.get("stop_requested_at"):
            row.stats = {**row.stats, "stop_requested_at": datetime.now(UTC).isoformat()}
        return {
            "capture_id": identity,
            "stop_requested": active,
            "status": capture_info(row)["status"],
            "final_state_verified": False,
            "live_enabled": False,
        }


def capture_stop_requested(engine: Engine, identity: str) -> bool:
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '1000ms'"))
        with Session(bind=connection) as db:
            row = db.get(CaptureRun, identity)
            if row is None:
                raise CaptureError("CAPTURE_NOT_FOUND")
            return bool(row.stats.get("stop_requested_at"))


def lock_capture(db: Session, identity: str) -> CaptureRun:
    row = db.scalar(select(CaptureRun).where(CaptureRun.id == identity).with_for_update())
    if row is None:
        raise CaptureError("CAPTURE_NOT_FOUND")
    return row


def running(row: CaptureRun) -> None:
    if row.status != "RUNNING" or datetime.now(UTC) >= aware(row.lease_expires_at):
        raise CaptureError("CAPTURE_NOT_RUNNING")


def charge_event(row: CaptureRun, event: CapturedEvent, size: int) -> None:
    running(row)
    if row.payload_bytes + size > row.policy["max_payload_bytes"]:
        raise CaptureError("CAPTURE_BYTE_QUOTA")
    if row.event_count >= row.policy["max_events"]:
        raise CaptureError("CAPTURE_EVENT_QUOTA")
    row.payload_bytes += size
    row.event_count += 1
    stats = dict(row.stats)
    for key, value in (
        ("observations", len(event.observations)),
        ("duplicates", event.duplicates),
        ("out_of_order", event.out_of_order),
        ("disconnects", int(event.kind == "DISCONNECTED")),
        ("idle_events", int(event.kind == "IDLE")),
        ("snapshots", int(event.kind == "SNAPSHOT")),
    ):
        stats[key] = int(stats.get(key, 0)) + value
    stats["last_event_at"] = event.observed_at.isoformat()
    stats["last_event_kind"] = event.kind
    stats["last_health"] = [item.model_dump(mode="json") for item in event.health]
    row.stats = stats


def create_capture(
    engine: Engine,
    request: FeedRequest,
    policy: CapturePolicy,
    source: Literal["UPSTOX_V3", "SYNTHETIC"],
) -> str:
    if source not in {"UPSTOX_V3", "SYNTHETIC"}:
        raise CaptureError("INVALID_CAPTURE_SOURCE")
    identity, now = uuid4().hex, datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.add(
            CaptureRun(
                id=identity,
                source=source,
                requested_keys=list(request.instrument_keys),
                policy=policy.model_dump(),
                status="RUNNING",
                created_at=now,
                lease_expires_at=now + timedelta(seconds=policy.total_seconds + 120),
                session_count=0,
                event_count=0,
                payload_bytes=0,
                stats={},
            )
        )
    return identity


def finish_capture(engine: Engine, identity: str, reason: str) -> None:
    reasons = {
        "SESSION_LIMIT",
        "TOTAL_DURATION_LIMIT",
        "COOPERATIVE_STOP",
        "CANCELLED",
        "CHILD_FAILED",
        "CHILD_NOT_STREAMING",
        "CAPTURE_BYTE_QUOTA",
        "CAPTURE_EVENT_QUOTA",
        "CAPTURE_SESSION_QUOTA",
        "INTERNAL_ERROR",
    }
    with Session(engine) as db, db.begin():
        if engine.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
        row = lock_capture(db, identity)
        if row.status != "RUNNING":
            return
        active = db.scalar(
            select(ObservationSession.id)
            .where(
                ObservationSession.supervisor_id == identity, ObservationSession.status == "RUNNING"
            )
            .limit(1)
        )
        if active:
            raise CaptureError("CAPTURE_CHILD_ACTIVE")
        row.status, row.reason, row.ended_at = (
            "CLOSED",
            reason if reason in reasons else "INTERNAL_ERROR",
            datetime.now(UTC),
        )


def recover_captures(engine: Engine) -> int:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        if engine.dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            db.execute(text("SET LOCAL statement_timeout = '1000ms'"))
        rows = list(
            db.scalars(
                select(CaptureRun)
                .where(CaptureRun.status == "RUNNING", CaptureRun.lease_expires_at <= now)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            for child in db.scalars(
                select(ObservationSession)
                .where(
                    ObservationSession.supervisor_id == row.id,
                    ObservationSession.status == "RUNNING",
                )
                .with_for_update()
            ):
                child.status, child.reason, child.recovered_at = "INTERRUPTED", "LEASE_EXPIRED", now
                child.previous_sample = None
            row.status, row.reason, row.recovered_at = "INTERRUPTED", "LEASE_EXPIRED", now
        return len(rows)


def capture_info(row: CaptureRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "requested_keys": row.requested_keys,
        "policy": row.policy,
        "status": "ABANDONED"
        if row.status == "RUNNING" and datetime.now(UTC) >= aware(row.lease_expires_at)
        else row.status,
        "reason": row.reason,
        "created_at": aware(row.created_at),
        "lease_expires_at": aware(row.lease_expires_at),
        "ended_at": aware(row.ended_at) if row.ended_at else None,
        "recovered_at": aware(row.recovered_at) if row.recovered_at else None,
        "session_count": row.session_count,
        "event_count": row.event_count,
        "payload_bytes": row.payload_bytes,
        "stats": row.stats,
        "health_current": False,
        "stop_requested_at": row.stats.get("stop_requested_at"),
        "qualifying_observation_days": 0,
        "signal_eligible": False,
        "execution_eligible": False,
        "live_enabled": False,
    }


def read_capture(engine: Engine, identity: str) -> dict[str, Any] | None:
    isolation = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"
    with engine.connect().execution_options(isolation_level=isolation) as connection:
        with connection.begin(), Session(bind=connection) as db:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
            row = db.get(CaptureRun, identity)
            if row is None:
                return None
            children = list(
                db.scalars(
                    select(ObservationSession)
                    .where(ObservationSession.supervisor_id == identity)
                    .order_by(ObservationSession.created_at)
                    .limit(12)
                )
            )
            return {
                "capture": capture_info(row),
                "sessions": [
                    {
                        "id": child.id,
                        "status": child.status,
                        "reason": child.reason,
                        "event_count": child.event_count,
                        "payload_bytes": child.payload_bytes,
                        "observed_interval_ms": child.observed_interval_ms,
                    }
                    for child in children
                ],
            }


def list_captures(engine: Engine, limit: int, after: str | None) -> dict[str, Any]:
    with Session(engine) as db:
        query = select(CaptureRun)
        if after:
            query = query.where(CaptureRun.id > after)
        rows = list(db.scalars(query.order_by(CaptureRun.id).limit(limit + 1)))
        page = rows[:limit]
        return {
            "captures": [capture_info(row) for row in page],
            "next_after": page[-1].id if len(rows) > limit and page else None,
        }
