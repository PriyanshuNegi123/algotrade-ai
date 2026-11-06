"""Durable bounded capture groups; never permission to trade."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class CaptureRun(Base):
    __tablename__ = "capture_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    requested_keys: Mapped[list[str]] = mapped_column(JSON)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    stats: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("source IN ('UPSTOX_V3','SYNTHETIC')", name="ck_capture_source"),
        CheckConstraint("status IN ('RUNNING','CLOSED','INTERRUPTED')", name="ck_capture_status"),
        CheckConstraint(
            "session_count >= 0 AND session_count <= 12 AND event_count >= 0 "
            "AND event_count <= 100000 AND payload_bytes >= 0 AND payload_bytes <= 67108864",
            name="ck_capture_bounds",
        ),
    )
