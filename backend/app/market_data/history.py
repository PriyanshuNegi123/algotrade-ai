"""Validate research-only minute history and persist immutable, versioned import batches."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.brokers.upstox import BrokerPayload
from backend.app.instruments.service import aware, lookup
from backend.app.market_data.contracts import IST, CandleRequest, history_url
from backend.app.market_data.models import Candle, CandleImport
from backend.app.market_data.validation import MarketDataError, quantity, strict_json


class PriceValue(BaseModel):
    value: Decimal = Field(gt=0, max_digits=24, decimal_places=8, allow_inf_nan=False)


MAX_CANDLES = 12_000


class CandleError(Exception):
    """Fixed local reason code; no broker body or input value in error text."""


@dataclass(frozen=True)
class Bar:
    opened_at: datetime
    closed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    open_interest: int | None


@dataclass(frozen=True)
class PreparedCandles:
    bars: tuple[Bar, ...]
    source_order: str
    gap_count: int
    canonical: bytes
    response_sha256: str
    retrieved_at: datetime
    source_url: str


def _price(value: object) -> Decimal:
    if type(value) is not int and not isinstance(value, Decimal):
        raise CandleError("INVALID_OHLC")
    try:
        return PriceValue(value=Decimal(value)).value
    except (ValidationError, ValueError):
        raise CandleError("INVALID_OHLC") from None


def validate_history(request: CandleRequest, payload: BrokerPayload) -> PreparedCandles:
    if payload.source_url != history_url(request):
        raise CandleError("SOURCE_IDENTITY_MISMATCH")
    if payload.retrieved_at.tzinfo is None or payload.retrieved_at > datetime.now(UTC) + timedelta(
        minutes=5
    ):
        raise CandleError("INVALID_RETRIEVAL_TIME")
    if len(payload.body) > 3 * 1024 * 1024:
        raise CandleError("RESPONSE_LIMIT_EXCEEDED")
    try:
        body = strict_json(payload.body)
        if not isinstance(body, dict) or body.get("status") != "success":
            raise CandleError("INVALID_CANDLE_ENVELOPE")
        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("candles"), list):
            raise CandleError("INVALID_CANDLE_ENVELOPE")
        # The reviewed contract does not guarantee an echoed key. Reject a conflicting
        # echo if one exists; otherwise identity remains bound to the encoded request URL.
        if "instrument_key" in data and data["instrument_key"] != request.instrument_key:
            raise CandleError("INSTRUMENT_IDENTITY_MISMATCH")
        rows = data["candles"]
        if len(rows) > MAX_CANDLES:
            raise CandleError("CANDLE_COUNT_LIMIT_EXCEEDED")
        bars: list[Bar] = []
        seen: set[datetime] = set()
        stride = timedelta(minutes=request.interval)
        for row in rows:
            if not isinstance(row, list) or len(row) != 7 or not isinstance(row[0], str):
                raise CandleError("INVALID_CANDLE_ROW")
            opened = datetime.fromisoformat(row[0])
            if opened.tzinfo is None:
                raise CandleError("NAIVE_CANDLE_TIME")
            opened = opened.astimezone(UTC)
            if opened.second or opened.microsecond:
                raise CandleError("MISALIGNED_CANDLE_TIME")
            if not request.from_date <= opened.astimezone(IST).date() <= request.to_date:
                raise CandleError("CANDLE_OUTSIDE_REQUEST")
            closed = opened + stride
            if closed > payload.retrieved_at:
                raise CandleError("INCOMPLETE_CANDLE")
            if opened in seen:
                raise CandleError("DUPLICATE_CANDLE_TIME")
            seen.add(opened)
            opening, high, low, closing = (_price(value) for value in row[1:5])
            if low > min(opening, closing) or high < max(opening, closing) or low > high:
                raise CandleError("INCONSISTENT_OHLC")
            bars.append(
                Bar(
                    opened,
                    closed,
                    opening,
                    high,
                    low,
                    closing,
                    quantity(row[5]),
                    None if row[6] is None else quantity(row[6]),
                )
            )
        source_order = "EMPTY" if not bars else "SINGLE"
        if len(bars) > 1:
            differences = [b.opened_at - a.opened_at for a, b in pairwise(bars)]
            if all(delta > timedelta(0) for delta in differences):
                source_order = "ASCENDING"
            elif all(delta < timedelta(0) for delta in differences):
                source_order = "DESCENDING"
                bars.reverse()
            else:
                raise CandleError("UNORDERED_CANDLES")
        gaps = 0
        for previous, current in pairwise(bars):
            if (
                previous.opened_at.astimezone(IST).date()
                != current.opened_at.astimezone(IST).date()
            ):
                continue
            delta = current.opened_at - previous.opened_at
            if delta % stride:
                raise CandleError("MISALIGNED_CANDLE_SEQUENCE")
            gaps += int(delta // stride) - 1
        # Persist only validated fields, never untrusted extra broker fields or an echoed secret.
        canonical = json.dumps(
            [
                [
                    bar.opened_at.isoformat(),
                    *(str(value.normalize()) for value in (bar.open, bar.high, bar.low, bar.close)),
                    bar.volume,
                    bar.open_interest,
                ]
                for bar in bars
            ],
            separators=(",", ":"),
        ).encode()
        return PreparedCandles(
            tuple(bars),
            source_order,
            gaps,
            canonical,
            hashlib.sha256(payload.body).hexdigest(),
            payload.retrieved_at.astimezone(UTC),
            payload.source_url,
        )
    except MarketDataError as error:
        raise CandleError(str(error)) from None
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise CandleError("INVALID_CANDLE_RESPONSE") from None


def resolve_instrument(engine: Engine, request: CandleRequest) -> dict[str, Any]:
    metadata = lookup(engine, request.instrument_key, datetime.now(UTC))
    if metadata is None:
        raise CandleError("INSTRUMENT_NOT_IN_CATALOG")
    if metadata["instrument_type"] != "INDEX":
        if metadata["expired"] or request.to_date > metadata["expiry_date"]:
            raise CandleError("EXPIRED_CONTRACT_UNSUPPORTED")
    return metadata


def batch_summary(row: CandleImport) -> dict[str, Any]:
    return {
        "id": row.id,
        "snapshot_id": row.snapshot_id,
        "instrument_key": row.instrument_key,
        "instrument_type": row.instrument_type,
        "unit": "minutes",
        "interval": row.interval,
        "from_date": row.from_date,
        "to_date": row.to_date,
        "source_url": row.source_url,
        "response_sha256": row.response_sha256,
        "canonical_sha256": row.canonical_sha256,
        "retrieved_at": aware(row.retrieved_at),
        "imported_at": aware(row.imported_at),
        "row_count": row.row_count,
        "gap_count": row.gap_count,
        "source_order": row.source_order,
        "state": "EMPTY"
        if row.row_count == 0
        else "GAPS_UNVERIFIED"
        if row.gap_count
        else "NOT_SESSION_VERIFIED",
        "identity_binding": "REQUEST_PATH_ONLY",
        "historical_metadata_verified": False,
        "signal_eligible": False,
        "execution_eligible": False,
    }


def archive_candles(
    engine: Engine, request: CandleRequest, prepared: PreparedCandles, metadata: dict[str, Any]
) -> dict[str, Any]:
    if request.instrument_key != metadata.get("instrument_key"):
        raise CandleError("INSTRUMENT_IDENTITY_MISMATCH")
    digest = hashlib.sha256(prepared.canonical).hexdigest()
    identity = hashlib.sha256(
        (metadata["snapshot_id"] + request.model_dump_json() + digest).encode()
    ).hexdigest()
    with Session(engine) as db:
        existing = db.get(CandleImport, identity)
        if existing:
            return {**batch_summary(existing), "deduplicated": True}
        row = CandleImport(
            id=identity,
            snapshot_id=metadata["snapshot_id"],
            instrument_key=request.instrument_key,
            instrument_type=metadata["instrument_type"],
            interval=request.interval,
            from_date=request.from_date,
            to_date=request.to_date,
            source_url=prepared.source_url,
            response_sha256=prepared.response_sha256,
            canonical_sha256=digest,
            retrieved_at=prepared.retrieved_at,
            imported_at=datetime.now(UTC),
            row_count=len(prepared.bars),
            gap_count=prepared.gap_count,
            source_order=prepared.source_order,
            canonical_payload=prepared.canonical,
        )
        try:
            db.add(row)
            db.flush()
            batch: list[dict[str, Any]] = []
            for bar in prepared.bars:
                batch.append(
                    {
                        "import_id": identity,
                        "opened_at": bar.opened_at,
                        "closed_at": bar.closed_at,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "open_interest": bar.open_interest,
                    }
                )
                if len(batch) == 500:
                    db.execute(insert(Candle), batch)
                    batch.clear()
            if batch:
                db.execute(insert(Candle), batch)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.get(CandleImport, identity)
            if existing:
                return {**batch_summary(existing), "deduplicated": True}
            raise
        return {**batch_summary(row), "deduplicated": False}


def history_status(engine: Engine) -> dict[str, Any]:
    with Session(engine) as db:
        row = db.scalar(select(CandleImport).order_by(CandleImport.imported_at.desc()).limit(1))
        return {
            "latest_import": batch_summary(row) if row else None,
            "state": "IMPORTED" if row else "NOT_IMPORTED",
            "entries_enabled": False,
            "live_enabled": False,
            "observation_started_at": None,
        }


def read_batch(
    engine: Engine, identity: str, limit: int, after: datetime | None
) -> dict[str, Any] | None:
    if after is not None and after.tzinfo is None:
        raise CandleError("NAIVE_CURSOR_TIME")
    with Session(engine) as db:
        row = db.get(CandleImport, identity)
        if row is None:
            return None
        query = select(Candle).where(Candle.import_id == identity)
        if after:
            query = query.where(Candle.opened_at > after.astimezone(UTC))
        rows = list(db.scalars(query.order_by(Candle.opened_at).limit(limit + 1)))
        page = rows[:limit]
        return {
            "import": batch_summary(row),
            "candles": [
                {
                    "opened_at": aware(bar.opened_at),
                    "closed_at": aware(bar.closed_at),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": bar.volume,
                    "open_interest": bar.open_interest,
                }
                for bar in page
            ],
            "next_after": aware(page[-1].opened_at) if len(rows) > limit and page else None,
        }
