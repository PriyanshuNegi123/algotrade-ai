"""Durable bounded research sessions; no trading or completed-day authority."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class ObservationSession(Base):
    __tablename__ = "observation_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    supervisor_id: Mapped[str | None] = mapped_column(
        ForeignKey("capture_runs.id", name="fk_observation_supervisor"), index=True
    )
    source: Mapped[str] = mapped_column(String(16))
    schema_sha256: Mapped[str] = mapped_column(String(64))
    requested_keys: Mapped[list[str]] = mapped_column(JSON)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    run_elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    observed_interval_ms: Mapped[int] = mapped_column(Integer, default=0)
    previous_sample: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (
        CheckConstraint("source IN ('UPSTOX_V3','SYNTHETIC')", name="ck_observation_source"),
        CheckConstraint(
            "status IN ('RUNNING','CLOSED','INTERRUPTED')", name="ck_observation_status"
        ),
        CheckConstraint(
            "event_count >= 0 AND event_count <= 11000 AND payload_bytes >= 0 "
            "AND payload_bytes <= 33554432 AND observed_interval_ms >= 0 "
            "AND last_elapsed_ms >= 0",
            name="ck_observation_bounds",
        ),
    )


class ObservationAttempt(Base):
    __tablename__ = "observation_attempts"
    session_id: Mapped[str] = mapped_column(ForeignKey("observation_sessions.id"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_snapshot_id: Mapped[str] = mapped_column(ForeignKey("instrument_snapshots.id"))
    instrument_keys: Mapped[list[str]] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("number >= 1 AND number <= 3", name="ck_observation_attempt"),
    )


class ObservationEvent(Base):
    __tablename__ = "observation_events"
    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, deferred=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "attempt"],
            ["observation_attempts.session_id", "observation_attempts.number"],
        ),
        UniqueConstraint("session_id", "payload_sha256", name="uq_observation_receipt"),
        CheckConstraint("sequence > 0 AND elapsed_ms >= 0", name="ck_observation_event"),
    )
