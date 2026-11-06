"""Immutable import batches; historical price observations never imply simulated fills."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base


class CandleImport(Base):
    __tablename__ = "candle_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(64))
    instrument_key: Mapped[str] = mapped_column(String(160))
    instrument_type: Mapped[str] = mapped_column(String(8))
    interval: Mapped[int] = mapped_column(Integer)
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(1024))
    response_sha256: Mapped[str] = mapped_column(String(64))
    canonical_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    row_count: Mapped[int] = mapped_column(Integer)
    gap_count: Mapped[int] = mapped_column(Integer)
    source_order: Mapped[str] = mapped_column(String(16))
    canonical_payload: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "instrument_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        CheckConstraint("interval IN (1,5,15)", name="ck_candle_interval"),
        CheckConstraint("row_count >= 0 AND gap_count >= 0", name="ck_candle_counts"),
    )


class Candle(Base):
    __tablename__ = "candles"
    import_id: Mapped[str] = mapped_column(ForeignKey("candle_imports.id"), primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    high: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    low: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    close: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    volume: Mapped[int] = mapped_column(BigInteger)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    __table_args__ = (
        CheckConstraint(
            "low > 0 AND high >= low AND open >= low AND open <= high "
            "AND close >= low AND close <= high",
            name="ck_candle_ohlc",
        ),
        CheckConstraint(
            "volume >= 0 AND (open_interest IS NULL OR open_interest >= 0)", name="ck_candle_volume"
        ),
        CheckConstraint("closed_at > opened_at", name="ck_candle_times"),
    )
