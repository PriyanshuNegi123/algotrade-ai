"""Atomic bounded research archives and conservative sampled-interval accounting."""

import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, undefer

from backend.app.instruments.models import Instrument
from backend.app.instruments.service import aware
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.feed_lifecycle import FeedEvent, LifecyclePolicy
from backend.app.market_data.observation_models import (
    ObservationAttempt,
    ObservationEvent,
    ObservationSession,
)
from backend.app.market_data.observation_schema import SAFE_REASONS, CapturedEvent
from backend.app.market_data.supervision_store import (
    CaptureError,
    charge_event,
    lock_capture,
    running,
)

SCHEMA_HASH = "3e1c939dce2c83a3fef91405c5ca268dfa089aae973319f56685f12a5afcf612"
MAX_BYTES = 32 * 1024 * 1024


class ObservationError(Exception):
    pass


def _limits(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET LOCAL statement_timeout = '1000ms'"))
        db.execute(text("SET LOCAL lock_timeout = '1000ms'"))
    else:
        db.connection().exec_driver_sql("PRAGMA busy_timeout=1000")


def start_session(
    engine: Engine,
    request: FeedRequest,
    policy: LifecyclePolicy,
    source: Literal["UPSTOX_V3", "SYNTHETIC"],
    supervisor_id: str | None = None,
) -> str:
    if source not in {"UPSTOX_V3", "SYNTHETIC"}:
        raise ObservationError("INVALID_OBSERVATION_SOURCE")
    identity = uuid4().hex
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        _limits(db)
        if supervisor_id:
            parent = lock_capture(db, supervisor_id)
            running(parent)
            if parent.requested_keys != list(request.instrument_keys) or parent.source != source:
                raise CaptureError("CAPTURE_REQUEST_MISMATCH")
            if parent.session_count >= parent.policy["max_sessions"]:
                raise CaptureError("CAPTURE_SESSION_QUOTA")
            if parent.payload_bytes >= parent.policy["max_payload_bytes"]:
                raise CaptureError("CAPTURE_BYTE_QUOTA")
            if parent.event_count >= parent.policy["max_events"]:
                raise CaptureError("CAPTURE_EVENT_QUOTA")
            if policy.duration_seconds > parent.policy["session_seconds"]:
                raise CaptureError("CAPTURE_SESSION_DURATION")
            parent.session_count += 1
        db.add(
            ObservationSession(
                id=identity,
                supervisor_id=supervisor_id,
                source=source,
                schema_sha256=SCHEMA_HASH,
                requested_keys=list(request.instrument_keys),
                policy=policy.model_dump(),
                status="RUNNING",
                created_at=now,
                lease_expires_at=now + timedelta(seconds=policy.duration_seconds + 60),
                event_count=0,
                payload_bytes=0,
                last_elapsed_ms=0,
                observed_interval_ms=0,
            )
        )
    return identity


def _canonical(event: FeedEvent) -> tuple[CapturedEvent, dict[str, Any], bytes]:
    try:
        raw = asdict(event)
        if raw["frame"] is not None:
            ticks = raw["frame"].pop("ticks")
            if ticks != [item["tick"] for item in raw["observations"]] and tuple(ticks) != tuple(
                item["tick"] for item in raw["observations"]
            ):
                raise ObservationError("OBSERVATION_TICK_MISMATCH")
        validated = CapturedEvent.model_validate(raw)
        if validated.detail is not None:
            if validated.kind == "BACKOFF":
                delay = float(validated.detail)
                if not 0 <= delay <= 3605:
                    raise ValueError
            elif validated.detail not in SAFE_REASONS and validated.detail != "NO_NEW_FRAME":
                raise ValueError
        payload = validated.model_dump(mode="json")
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if len(canonical) > 256 * 1024:
            raise ObservationError("OBSERVATION_EVENT_SIZE")
        return validated, payload, canonical
    except (ValidationError, ValueError, TypeError):
        raise ObservationError("INVALID_OBSERVATION_EVENT") from None


def _locked(db: Session, identity: str) -> ObservationSession:
    row = db.scalar(
        select(ObservationSession).where(ObservationSession.id == identity).with_for_update()
    )
    if row is None:
        raise ObservationError("OBSERVATION_NOT_FOUND")
    return row


def _account(row: ObservationSession, event: CapturedEvent) -> None:
    frame = event.frame
    qualifying = bool(
        frame
        and event.observations
        and 0 <= (frame.received_at - frame.generated_at).total_seconds() <= 10
    )
    if not qualifying or frame is None:
        row.previous_sample = None
        return
    previous = row.previous_sample
    if previous and previous["attempt"] == event.attempt:
        delta = event.elapsed_ms - int(previous["elapsed_ms"])
        receipt_delta = int(
            (frame.received_at - datetime.fromisoformat(previous["received_at"])).total_seconds()
            * 1000
        )
        if 0 < delta <= 10_000 and 0 < receipt_delta <= 10_000:
            row.observed_interval_ms += min(delta, receipt_delta)
    row.previous_sample = {
        "attempt": event.attempt,
        "elapsed_ms": event.elapsed_ms,
        "received_at": frame.received_at.isoformat(),
    }


def append_event(engine: Engine, identity: str, event: FeedEvent) -> int:
    validated, payload, canonical = _canonical(event)
    digest = hashlib.sha256(canonical).hexdigest()
    with Session(engine) as db, db.begin():
        _limits(db)
        parent_id = db.scalar(
            select(ObservationSession.supervisor_id).where(ObservationSession.id == identity)
        )
        parent = lock_capture(db, parent_id) if parent_id else None
        row = _locked(db, identity)
        existing = db.scalar(
            select(ObservationEvent.sequence).where(
                ObservationEvent.session_id == identity, ObservationEvent.payload_sha256 == digest
            )
        )
        if existing is not None:
            return existing
        if row.status != "RUNNING" or datetime.now(UTC) >= aware(row.lease_expires_at):
            raise ObservationError("OBSERVATION_NOT_RUNNING")
        now = datetime.now(UTC)
        if (
            validated.attempt > row.policy["max_attempts"]
            or validated.elapsed_ms > row.policy["duration_seconds"] * 1000 + 30_000
            or validated.observed_at < aware(row.created_at) - timedelta(seconds=5)
            or validated.observed_at > now + timedelta(seconds=5)
        ):
            raise ObservationError("OBSERVATION_SESSION_BOUNDS")
        if validated.elapsed_ms < row.last_elapsed_ms:
            raise ObservationError("OBSERVATION_CLOCK_REGRESSION")
        if row.event_count >= 11_000 or row.payload_bytes + len(canonical) > MAX_BYTES:
            raise ObservationError("OBSERVATION_STORAGE_LIMIT")
        if validated.plan:
            plan = validated.plan
            if list(plan.instrument_keys) != row.requested_keys:
                raise ObservationError("OBSERVATION_PLAN_MISMATCH")
            keys = set(
                db.scalars(
                    select(Instrument.instrument_key).where(
                        Instrument.snapshot_id == plan.catalog_snapshot_id,
                        Instrument.instrument_key.in_(plan.instrument_keys),
                    )
                )
            )
            already = db.get(ObservationAttempt, (identity, event.attempt))
            if keys != set(plan.instrument_keys) or already is not None:
                raise ObservationError("OBSERVATION_CATALOG_MISMATCH")
            db.add(
                ObservationAttempt(
                    session_id=identity,
                    number=event.attempt,
                    catalog_snapshot_id=plan.catalog_snapshot_id,
                    instrument_keys=list(plan.instrument_keys),
                )
            )
            db.flush()
        attempt = db.get(ObservationAttempt, (identity, event.attempt))
        if attempt is None:
            raise ObservationError("OBSERVATION_PLAN_REQUIRED")
        if validated.frame and validated.frame.catalog_snapshot_id != attempt.catalog_snapshot_id:
            raise ObservationError("OBSERVATION_FRAME_CATALOG_MISMATCH")
        keys = {item.tick.instrument_key for item in validated.observations} | {
            item.instrument_key for item in validated.health
        }
        if not keys.issubset(set(attempt.instrument_keys)):
            raise ObservationError("OBSERVATION_KEY_MISMATCH")
        if len({item.tick.instrument_key for item in validated.observations}) != len(
            validated.observations
        ):
            raise ObservationError("DUPLICATE_OBSERVATION_KEY")
        if parent is not None:
            charge_event(parent, validated, len(canonical))
        row.event_count += 1
        row.payload_bytes += len(canonical)
        row.last_elapsed_ms = validated.elapsed_ms
        _account(row, validated)
        db.add(
            ObservationEvent(
                session_id=identity,
                sequence=row.event_count,
                attempt=event.attempt,
                kind=event.kind,
                observed_at=validated.observed_at,
                elapsed_ms=validated.elapsed_ms,
                payload_sha256=digest,
                payload=payload,
            )
        )
        return row.event_count


def finish_session(engine: Engine, identity: str, reason: str, elapsed_ms: int) -> None:
    reason = reason if reason in SAFE_REASONS else "UNCLASSIFIED_STOP"
    if type(elapsed_ms) is not int or not 0 <= elapsed_ms <= 360_000:
        raise ObservationError("INVALID_OBSERVATION_DURATION")
    with Session(engine) as db, db.begin():
        _limits(db)
        row = _locked(db, identity)
        if row.status != "RUNNING":
            return
        row.status, row.reason, row.ended_at = "CLOSED", reason, datetime.now(UTC)
        row.run_elapsed_ms = max(elapsed_ms, row.last_elapsed_ms)
        row.previous_sample = None


def recover_abandoned(engine: Engine) -> int:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        _limits(db)
        rows = list(
            db.scalars(
                select(ObservationSession)
                .where(
                    ObservationSession.status == "RUNNING",
                    ObservationSession.lease_expires_at <= now,
                )
                .order_by(ObservationSession.created_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status, row.reason, row.recovered_at = "INTERRUPTED", "LEASE_EXPIRED", now
            row.previous_sample = None
        return len(rows)


def session_info(row: ObservationSession) -> dict[str, Any]:
    abandoned = row.status == "RUNNING" and datetime.now(UTC) >= aware(row.lease_expires_at)
    return {
        "id": row.id,
        "supervisor_id": row.supervisor_id,
        "source": row.source,
        "schema_sha256": row.schema_sha256,
        "requested_keys": row.requested_keys,
        "policy": row.policy,
        "status": "ABANDONED" if abandoned else row.status,
        "reason": row.reason,
        "created_at": aware(row.created_at),
        "lease_expires_at": aware(row.lease_expires_at),
        "ended_at": aware(row.ended_at) if row.ended_at else None,
        "recovered_at": aware(row.recovered_at) if row.recovered_at else None,
        "event_count": row.event_count,
        "payload_bytes": row.payload_bytes,
        "run_elapsed_ms": row.run_elapsed_ms,
        "observed_interval_ms": row.observed_interval_ms,
        "calendar_verified": False,
        "qualifying_observation_days": 0,
        "signal_eligible": False,
        "execution_eligible": False,
    }


def list_sessions(engine: Engine, limit: int, after: str | None) -> dict[str, Any]:
    with Session(engine) as db:
        query = select(ObservationSession)
        if after:
            query = query.where(ObservationSession.id > after)
        rows = list(db.scalars(query.order_by(ObservationSession.id).limit(limit + 1)))
        page = rows[:limit]
        return {
            "sessions": [session_info(row) for row in page],
            "next_after": page[-1].id if len(rows) > limit and page else None,
        }


def read_session(engine: Engine, identity: str, limit: int, after: int) -> dict[str, Any] | None:
    with Session(engine) as db:
        row = db.get(ObservationSession, identity)
        if row is None:
            return None
        events = list(
            db.scalars(
                select(ObservationEvent)
                .options(undefer(ObservationEvent.payload))
                .where(
                    ObservationEvent.session_id == identity,
                    ObservationEvent.sequence > after,
                )
                .order_by(ObservationEvent.sequence)
                .limit(limit + 1)
            )
        )
        page = events[:limit]
        attempts = list(
            db.scalars(
                select(ObservationAttempt)
                .where(ObservationAttempt.session_id == identity)
                .order_by(ObservationAttempt.number)
            )
        )
        return {
            "session": session_info(row),
            "attempts": [
                {
                    "number": attempt.number,
                    "catalog_snapshot_id": attempt.catalog_snapshot_id,
                    "instrument_keys": attempt.instrument_keys,
                }
                for attempt in attempts
            ],
            "events": [
                {
                    "sequence": event.sequence,
                    "payload_sha256": event.payload_sha256,
                    "event": event.payload,
                }
                for event in page
            ],
            "next_after": page[-1].sequence if len(events) > limit and page else None,
        }


class ObservationWriter:
    """Wait for in-flight commits before propagating cancellation or finalizing a session."""

    def __init__(self, engine: Engine, identity: str):
        self.engine, self.identity = engine, identity
        self.lock = asyncio.Lock()

    async def _call(self, function: Any, *args: Any) -> Any:
        async with self.lock:
            task = asyncio.create_task(
                asyncio.to_thread(function, self.engine, self.identity, *args)
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await asyncio.shield(task)
                raise

    async def append(self, event: FeedEvent) -> None:
        await self._call(append_event, event)

    async def finish(self, reason: str, elapsed_ms: int) -> None:
        await self._call(finish_session, reason, elapsed_ms)


def event_payload_bytes(event: FeedEvent) -> int:
    """Canonical size estimate for local quota planning; never performs a write."""
    return len(_canonical(event)[2])
