"""Validate and atomically archive immutable, first-observed instrument snapshots."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.source import (
    SOURCE_URL,
    Download,
    InstrumentError,
    decoded_chunks,
    json_records,
    validate_publication,
)

IST = ZoneInfo("Asia/Kolkata")
PositiveInt = Annotated[int, Field(gt=0, le=2_147_483_647)]
MoneyNumber = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=8)]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, hide_input_in_errors=True)
    instrument_key: str = Field(min_length=3, max_length=160)
    segment: Literal["NSE_INDEX", "NSE_FO"]
    instrument_type: Literal["INDEX", "CE", "PE", "FUT"]
    trading_symbol: str = Field(min_length=1, max_length=160)
    underlying_key: str | None = Field(default=None, max_length=160)
    lot_size: PositiveInt | None = None
    minimum_lot: PositiveInt | None = None
    tick_size: MoneyNumber | None = None
    expiry: Annotated[int, Field(gt=0, le=253402300799999)] | None = None
    strike_price: MoneyNumber | None = None

    @field_validator("tick_size", "strike_price", mode="before")
    @classmethod
    def decimal_number(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        if type(value) is int or isinstance(value, Decimal):
            return Decimal(value)
        raise ValueError("Expected an exact JSON number")

    @model_validator(mode="after")
    def contract_shape(self) -> "Metadata":
        prefix = f"{self.segment}|"
        if (
            not self.instrument_key.startswith(prefix)
            or not self.instrument_key[len(prefix) :].strip()
        ):
            raise ValueError("Instrument key/segment mismatch")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.instrument_key):
            raise ValueError("Invalid instrument key")
        if self.segment == "NSE_INDEX":
            if self.instrument_type != "INDEX" or any(
                value is not None
                for value in (
                    self.lot_size,
                    self.tick_size,
                    self.expiry,
                    self.underlying_key,
                )
            ):
                raise ValueError("Index metadata must not invent derivative fields")
        else:
            if (
                self.instrument_type == "INDEX"
                or not self.underlying_key
                or not self.underlying_key.startswith("NSE_INDEX|")
            ):
                raise ValueError("Only index derivatives are supported")
            if not self.lot_size or not self.tick_size or not self.expiry:
                raise ValueError("Derivative metadata is incomplete")
            if self.instrument_type in {"CE", "PE"} and not self.strike_price:
                raise ValueError("Option strike must be positive")
        return self


class PreparedSnapshot(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    download: Download
    records: list[Metadata]
    source_records: int


def prepare(download: Download) -> PreparedSnapshot:
    validate_publication(download.modified_at, download.retrieved_at)
    if download.retrieved_at > datetime.now(UTC) + timedelta(minutes=5):
        raise InstrumentError("FUTURE_RETRIEVAL_TIME")
    keys: set[str] = set()
    selected: list[Metadata] = []
    count = 0
    try:
        for raw in json_records(decoded_chunks(download.body)):
            count += 1
            if not isinstance(raw.get("segment"), str) or not isinstance(
                raw.get("instrument_type"), str
            ):
                raise InstrumentError("INVALID_RECORD_SCHEMA")
            if raw["segment"] != "NSE_INDEX" and not (
                raw["segment"] == "NSE_FO" and raw.get("underlying_type") == "INDEX"
            ):
                continue
            record = Metadata.model_validate(raw)
            if record.instrument_key in keys:
                raise InstrumentError("DUPLICATE_INSTRUMENT_KEY")
            keys.add(record.instrument_key)
            if record.expiry is not None:
                expiry = datetime.fromtimestamp(record.expiry / 1000, UTC)
                if expiry.astimezone(IST).date() < download.modified_at.astimezone(IST).date():
                    raise InstrumentError("EXPIRED_SOURCE_CONTRACT")
            selected.append(record)
            if len(selected) > 50_000:
                raise InstrumentError("SELECTED_RECORD_LIMIT_EXCEEDED")
    except (ValidationError, ValueError, OverflowError):
        raise InstrumentError("INVALID_RECORD_SCHEMA") from None
    indices = {row.instrument_key for row in selected if row.instrument_type == "INDEX"}
    if not indices or not any(row.instrument_type in {"CE", "PE"} for row in selected):
        raise InstrumentError("INCOMPLETE_INSTRUMENT_UNIVERSE")
    if any(row.underlying_key and row.underlying_key not in indices for row in selected):
        raise InstrumentError("MISSING_UNDERLYING_INDEX")
    return PreparedSnapshot(download=download, records=selected, source_records=count)


def aware(value: datetime) -> datetime:
    # Test-only SQLite loses timezone metadata; all application timestamps are UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def snapshot_summary(row: InstrumentSnapshot) -> dict[str, Any]:
    now = datetime.now(UTC)
    current = aware(row.source_modified_at).astimezone(IST).date() == now.astimezone(
        IST
    ).date() and now - aware(row.retrieved_at) <= timedelta(hours=24)
    return {
        "id": row.id,
        "source_url": row.source_url,
        "sha256": row.sha256,
        "source_modified_at": aware(row.source_modified_at),
        "retrieved_at": aware(row.retrieved_at),
        "imported_at": aware(row.imported_at),
        "source_records": row.source_records,
        "selected_records": row.selected_records,
        "state": "CURRENT_METADATA" if current else "STALE_METADATA",
        "tick_size_unit": "BROKER_UNVERIFIED",
        "execution_eligible": False,
    }


def archive(engine: Engine, prepared: PreparedSnapshot) -> dict[str, Any]:
    source = prepared.download
    identity = hashlib.sha256(
        f"{SOURCE_URL}\n{source.modified_at.astimezone(UTC).isoformat()}\n{source.sha256}".encode()
    ).hexdigest()
    # One transaction inserts the archive and all normalized rows, or none of them.
    with Session(engine) as db:
        existing = db.get(InstrumentSnapshot, identity)
        if existing:
            return {**snapshot_summary(existing), "deduplicated": True}
        row = InstrumentSnapshot(
            id=identity,
            source_url=SOURCE_URL,
            source_modified_at=source.modified_at.astimezone(UTC),
            retrieved_at=source.retrieved_at.astimezone(UTC),
            imported_at=datetime.now(UTC),
            sha256=source.sha256,
            source_records=prepared.source_records,
            selected_records=len(prepared.records),
            raw_gzip=source.body,
        )
        try:
            db.add(row)
            db.flush()
            batch: list[dict[str, Any]] = []
            for record in prepared.records:
                batch.append(
                    {
                        "snapshot_id": identity,
                        "instrument_key": record.instrument_key,
                        "segment": record.segment,
                        "instrument_type": record.instrument_type,
                        "trading_symbol": record.trading_symbol,
                        "underlying_key": record.underlying_key,
                        "lot_size": record.lot_size,
                        "minimum_lot": record.minimum_lot,
                        "tick_size_raw": record.tick_size,
                        "tick_size_unit": "BROKER_UNVERIFIED",
                        "expiry": datetime.fromtimestamp(record.expiry / 1000, UTC)
                        if record.expiry
                        else None,
                        "strike_price": record.strike_price,
                    }
                )
                if len(batch) == 500:
                    db.execute(insert(Instrument), batch)
                    batch.clear()
            if batch:
                db.execute(insert(Instrument), batch)
            db.commit()
        except IntegrityError:
            db.rollback()
            # A concurrent identical import may have committed first. Never overwrite it.
            existing = db.get(InstrumentSnapshot, identity)
            if existing is not None:
                return {**snapshot_summary(existing), "deduplicated": True}
            raise
        return {**snapshot_summary(row), "deduplicated": False}


def catalog_status(engine: Engine) -> dict[str, Any]:
    with Session(engine) as db:
        row = db.scalar(
            select(InstrumentSnapshot)
            .order_by(
                InstrumentSnapshot.source_modified_at.desc(), InstrumentSnapshot.imported_at.desc()
            )
            .limit(1)
        )
        return {
            "snapshot": snapshot_summary(row) if row else None,
            "state": snapshot_summary(row)["state"] if row else "NOT_IMPORTED",
            "entries_enabled": False,
            "live_enabled": False,
            "observation_started_at": None,
        }


def lookup(engine: Engine, instrument_key: str, as_of: datetime) -> dict[str, Any] | None:
    if as_of.tzinfo is None or as_of > datetime.now(UTC) + timedelta(seconds=1):
        raise InstrumentError("INVALID_AS_OF_TIME")
    as_of = as_of.astimezone(UTC)
    with Session(engine) as db:
        # Choose the universe before looking up a key: removed contracts must not reappear
        # from an older snapshot just because the latest universe does not contain them.
        snapshot = db.scalar(
            select(InstrumentSnapshot)
            .where(InstrumentSnapshot.imported_at <= as_of)
            .order_by(
                InstrumentSnapshot.source_modified_at.desc(), InstrumentSnapshot.imported_at.desc()
            )
            .limit(1)
        )
        if snapshot is None:
            return None
        record = db.get(Instrument, (snapshot.id, instrument_key))
        if record is None:
            return None
        return {
            "snapshot_id": snapshot.id,
            "source_modified_at": aware(snapshot.source_modified_at),
            "known_at": aware(snapshot.imported_at),
            "as_of": as_of,
            "instrument_key": record.instrument_key,
            "segment": record.segment,
            "instrument_type": record.instrument_type,
            "trading_symbol": record.trading_symbol,
            "underlying_key": record.underlying_key,
            "lot_size": record.lot_size,
            "minimum_lot": record.minimum_lot,
            "tick_size_raw": str(record.tick_size_raw)
            if record.tick_size_raw is not None
            else None,
            "tick_size_unit": record.tick_size_unit,
            "strike_price": str(record.strike_price) if record.strike_price is not None else None,
            "expiry": aware(record.expiry) if record.expiry else None,
            "expiry_date": aware(record.expiry).astimezone(IST).date() if record.expiry else None,
            "expired": bool(record.expiry and aware(record.expiry) <= as_of),
            "execution_eligible": False,
        }
