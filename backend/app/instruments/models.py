"""Immutable source snapshots and normalized NSE index/derivative metadata."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class InstrumentSnapshot(Base):
    __tablename__ = "instrument_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_url: Mapped[str] = mapped_column(String(256))
    source_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    source_records: Mapped[int] = mapped_column(Integer)
    selected_records: Mapped[int] = mapped_column(Integer)
    raw_gzip: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    __table_args__ = (
        CheckConstraint("source_records > 0 AND selected_records > 0", name="ck_snapshot_counts"),
    )


class Instrument(Base):
    __tablename__ = "instruments"
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("instrument_snapshots.id"), primary_key=True
    )
    instrument_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    segment: Mapped[str] = mapped_column(String(16))
    instrument_type: Mapped[str] = mapped_column(String(8))
    trading_symbol: Mapped[str] = mapped_column(String(160))
    underlying_key: Mapped[str | None] = mapped_column(String(160))
    lot_size: Mapped[int | None] = mapped_column(Integer)
    minimum_lot: Mapped[int | None] = mapped_column(Integer)
    tick_size_raw: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    tick_size_unit: Mapped[str] = mapped_column(String(32), default="BROKER_UNVERIFIED")
    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    strike_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    __table_args__ = (
        CheckConstraint("instrument_type IN ('INDEX','CE','PE','FUT')", name="ck_instrument_type"),
        CheckConstraint("lot_size IS NULL OR lot_size > 0", name="ck_instrument_lot"),
        CheckConstraint("tick_size_raw IS NULL OR tick_size_raw > 0", name="ck_instrument_tick"),
        Index(
            "ix_instrument_contracts", "snapshot_id", "underlying_key", "instrument_type", "expiry"
        ),
    )
