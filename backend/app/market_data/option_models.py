"""Receipt-versioned, catalog-bound option-chain observations; never execution authority."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
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


class ChainSnapshot(Base):
    __tablename__ = "option_chain_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    catalog_snapshot_id: Mapped[str] = mapped_column(String(64))
    underlying_key: Mapped[str] = mapped_column(String(160))
    expiry_date: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(1024))
    response_sha256: Mapped[str] = mapped_column(String(64))
    canonical_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    strike_count: Mapped[int] = mapped_column(Integer)
    leg_count: Mapped[int] = mapped_column(Integer)
    flagged_legs: Mapped[int] = mapped_column(Integer)
    canonical_payload: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["catalog_snapshot_id", "underlying_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        CheckConstraint(
            "strike_count >= 0 AND leg_count = 2 * strike_count AND flagged_legs >= 0",
            name="ck_chain_counts",
        ),
    )


class ChainLeg(Base):
    __tablename__ = "option_chain_legs"
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("option_chain_snapshots.id"), primary_key=True
    )
    instrument_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    catalog_snapshot_id: Mapped[str] = mapped_column(String(64))
    option_type: Mapped[str] = mapped_column(String(2))
    strike_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    lot_size: Mapped[int] = mapped_column(Integer)
    underlying_spot: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    pcr: Mapped[Decimal | None] = mapped_column(Numeric(30, 16))
    ltp: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    spread: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    bid_qty: Mapped[int | None] = mapped_column(BigInteger)
    ask_qty: Mapped[int | None] = mapped_column(BigInteger)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    oi: Mapped[int | None] = mapped_column(BigInteger)
    prev_oi: Mapped[int | None] = mapped_column(BigInteger)
    greeks: Mapped[dict[str, Any]] = mapped_column(JSON)
    quality_flags: Mapped[list[str]] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(
            ["catalog_snapshot_id", "instrument_key"],
            ["instruments.snapshot_id", "instruments.instrument_key"],
        ),
        CheckConstraint(
            "option_type IN ('CE','PE') AND strike_price > 0 AND lot_size > 0",
            name="ck_chain_identity",
        ),
        CheckConstraint(
            "(bid_price IS NULL OR bid_price >= 0) AND (ask_price IS NULL OR ask_price >= 0)",
            name="ck_chain_prices",
        ),
        CheckConstraint(
            "bid_price IS NULL OR ask_price IS NULL OR bid_price = 0 "
            "OR ask_price = 0 OR bid_price <= ask_price",
            name="ck_chain_spread",
        ),
    )
