"""Bounded V3 LTPC decoding for catalog-resolved subscriptions; no socket or trading loop."""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from google.protobuf.message import DecodeError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.service import aware, snapshot_summary
from backend.app.market_data.contracts import IST
from backend.vendor.upstox import MarketDataFeed_pb2 as pb

MAX_FRAME_BYTES = 512 * 1024
MAX_KEYS = 100  # Deliberately smaller than broker limits; no subscription entitlement implied.


class FeedError(Exception):
    pass


class FeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    instrument_keys: tuple[str, ...] = Field(min_length=1, max_length=MAX_KEYS)

    @field_validator("instrument_keys")
    @classmethod
    def keys(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("Duplicate feed key")
        for value in values:
            if (
                len(value) > 160
                or re.fullmatch(r"NSE_(?:INDEX|FO)\|[^|/\\?#\x00-\x1f\x7f]+", value) is None
                or value != value.strip()
            ):
                raise ValueError("Invalid feed key")
        return values


@dataclass(frozen=True)
class FeedPlan:
    catalog_snapshot_id: str
    instrument_keys: tuple[str, ...]
    mode: Literal["ltpc"] = "ltpc"

    def subscription(self) -> bytes:
        return json.dumps(
            {
                "guid": uuid4().hex,
                "method": "sub",
                "data": {
                    "mode": self.mode,
                    "instrumentKeys": self.instrument_keys,
                },
            },
            separators=(",", ":"),
        ).encode()


def resolve_feed(engine: Engine, request: FeedRequest) -> FeedPlan:
    with Session(engine) as db:
        return resolve_feed_catalog(db, request)


def resolve_feed_catalog(db: Session, request: FeedRequest) -> FeedPlan:
    catalog = db.scalar(
        select(InstrumentSnapshot).order_by(InstrumentSnapshot.imported_at.desc()).limit(1)
    )
    if catalog is None or snapshot_summary(catalog)["state"] != "CURRENT_METADATA":
        raise FeedError("CURRENT_CATALOG_REQUIRED")
    rows = list(
        db.scalars(
            select(Instrument).where(
                Instrument.snapshot_id == catalog.id,
                Instrument.instrument_key.in_(request.instrument_keys),
            )
        )
    )
    if len(rows) != len(request.instrument_keys):
        raise FeedError("FEED_KEY_NOT_IN_CATALOG")
    today = datetime.now(UTC).astimezone(IST).date()
    for row in rows:
        if row.instrument_type not in {"INDEX", "CE", "PE"}:
            raise FeedError("UNSUPPORTED_FEED_INSTRUMENT")
        if row.instrument_type != "INDEX" and (
            row.expiry is None or aware(row.expiry).astimezone(IST).date() < today
        ):
            raise FeedError("EXPIRED_FEED_INSTRUMENT")
    return FeedPlan(catalog.id, request.instrument_keys)


@dataclass(frozen=True)
class FeedTick:
    instrument_key: str
    last_price: Decimal
    last_trade_at: datetime | None
    last_quantity: int
    close_price: Decimal
    indicative_price: Decimal | None
    quality_flags: tuple[str, ...]
    freshness: Literal["NOT_EVALUATED"] = "NOT_EVALUATED"
    signal_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False


@dataclass(frozen=True)
class FeedFrame:
    catalog_snapshot_id: str
    message_type: str
    generated_at: datetime
    received_at: datetime
    ticks: tuple[FeedTick, ...]
    market_status: tuple[tuple[str, str], ...]
    signal_eligible: Literal[False] = False
    execution_eligible: Literal[False] = False


def _timestamp(value: int) -> datetime:
    if value <= 0 or value > 253402300799999:
        raise FeedError("INVALID_FEED_TIMESTAMP")
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=value)


def _price(value: float) -> Decimal:
    if not math.isfinite(value) or value < 0 or value >= 1e16:
        raise FeedError("INVALID_FEED_PRICE")
    # The wire type is double, not an exact exchange decimal. Preserve its shortest decimal
    # representation; do not infer tick alignment, precision, or trade eligibility.
    return Decimal(str(value))


def decode_frame(body: bytes, plan: FeedPlan, received_at: datetime) -> FeedFrame:
    if not isinstance(body, bytes) or not body or len(body) > MAX_FRAME_BYTES:
        raise FeedError("INVALID_FEED_FRAME_SIZE")
    if received_at.tzinfo is None:
        raise FeedError("NAIVE_FEED_RECEIPT")
    if not 1 <= len(plan.instrument_keys) <= MAX_KEYS or len(set(plan.instrument_keys)) != len(
        plan.instrument_keys
    ):
        raise FeedError("INVALID_FEED_PLAN")
    message = pb.FeedResponse()
    try:
        message.ParseFromString(body)
    except DecodeError:
        raise FeedError("INVALID_FEED_PROTOBUF") from None
    generated = _timestamp(message.currentTs)
    receipt = received_at.astimezone(UTC)
    if generated > receipt + timedelta(seconds=5):
        raise FeedError("FUTURE_FEED_TIMESTAMP")
    if message.type not in (pb.initial_feed, pb.live_feed, pb.market_info):
        raise FeedError("UNSUPPORTED_FEED_TYPE")
    if len(message.feeds) > len(plan.instrument_keys):
        raise FeedError("FEED_KEY_LIMIT_EXCEEDED")
    statuses: list[tuple[str, str]] = []
    if message.type == pb.market_info:
        if message.feeds or not message.HasField("marketInfo"):
            raise FeedError("INVALID_MARKET_INFO")
        if len(message.marketInfo.segmentStatus) > 64:
            raise FeedError("MARKET_SEGMENT_LIMIT_EXCEEDED")
        for segment, status in message.marketInfo.segmentStatus.items():
            if re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", segment) is None or status not in range(6):
                raise FeedError("UNSUPPORTED_MARKET_STATUS")
            statuses.append((segment, pb.MarketStatus.Name(status)))
    elif message.HasField("marketInfo"):
        raise FeedError("UNEXPECTED_MARKET_INFO")
    ticks = []
    allowed = set(plan.instrument_keys)
    for key in sorted(message.feeds):
        if key not in allowed:
            raise FeedError("UNSUBSCRIBED_FEED_KEY")
        feed = message.feeds[key]
        if feed.WhichOneof("FeedUnion") != "ltpc" or feed.requestMode != pb.ltpc:
            raise FeedError("UNSUPPORTED_FEED_MODE")
        value = feed.ltpc
        price, close = _price(value.ltp), _price(value.cp)
        indicative = _price(value.iep.value) if value.HasField("iep") else None
        trade_at = _timestamp(value.ltt) if value.ltt != 0 else None
        if trade_at and trade_at > generated + timedelta(seconds=5):
            raise FeedError("FUTURE_TRADE_TIMESTAMP")
        if value.ltq < 0:
            raise FeedError("INVALID_FEED_QUANTITY")
        flags = ["PROTO3_SCALAR_PRESENCE_UNKNOWN", "WIRE_DOUBLE_PRICE"]
        if price == 0:
            flags.append("ZERO_OR_MISSING_PRICE")
        if close == 0:
            flags.append("ZERO_OR_MISSING_CLOSE")
        if trade_at is None:
            flags.append("MISSING_TRADE_TIME")
        ticks.append(FeedTick(key, price, trade_at, value.ltq, close, indicative, tuple(flags)))
    return FeedFrame(
        plan.catalog_snapshot_id,
        pb.Type.Name(message.type),
        generated,
        receipt,
        tuple(ticks),
        tuple(sorted(statuses)),
    )
