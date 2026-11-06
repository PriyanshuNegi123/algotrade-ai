"""Catalog-bound option-chain research observations; receipt time is not quote freshness."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.brokers.upstox import BrokerPayload
from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.service import aware, lookup, snapshot_summary
from backend.app.market_data.contracts import IST
from backend.app.market_data.option_contracts import ChainRequest, chain_url
from backend.app.market_data.option_models import ChainLeg, ChainSnapshot
from backend.app.market_data.validation import MarketDataError, quantity, strict_json

MAX_STRIKES = 2_000


class ChainError(MarketDataError):
    pass


class MarketNumber(BaseModel):
    value: Decimal = Field(ge=0, max_digits=24, decimal_places=8, allow_inf_nan=False)


class GreekNumber(BaseModel):
    value: Decimal = Field(max_digits=30, decimal_places=16, allow_inf_nan=False)


@dataclass(frozen=True)
class CatalogOption:
    instrument_key: str
    option_type: str
    strike_price: Decimal
    lot_size: int


@dataclass(frozen=True)
class ChainContext:
    snapshot_id: str
    underlying_key: str
    expiry_date: date
    contracts: dict[str, CatalogOption]


@dataclass(frozen=True)
class PreparedChain:
    legs: tuple[dict[str, Any], ...]
    canonical: bytes
    response_sha256: str
    retrieved_at: datetime
    source_url: str


def _underlying(engine: Engine, key: str) -> dict[str, Any]:
    try:
        ChainRequest.index_key(key)
    except ValueError:
        raise ChainError("INVALID_UNDERLYING_KEY") from None
    metadata = lookup(engine, key, datetime.now(UTC))
    if metadata is None or metadata["instrument_type"] != "INDEX":
        raise ChainError("UNDERLYING_NOT_IN_CATALOG")
    with Session(engine) as db:
        snapshot = db.get(InstrumentSnapshot, metadata["snapshot_id"])
        if snapshot is None or snapshot_summary(snapshot)["state"] != "CURRENT_METADATA":
            raise ChainError("STALE_INSTRUMENT_CATALOG")
    return metadata


def available_expiries(engine: Engine, key: str) -> dict[str, Any]:
    metadata = _underlying(engine, key)
    today = datetime.now(UTC).astimezone(IST).date()
    with Session(engine) as db:
        dates = db.scalars(
            select(Instrument.expiry).where(
                Instrument.snapshot_id == metadata["snapshot_id"],
                Instrument.underlying_key == key,
                Instrument.instrument_type.in_(["CE", "PE"]),
                Instrument.expiry.is_not(None),
            )
        )
        expiries = sorted(
            {
                aware(value).astimezone(IST).date()
                for value in dates
                if value is not None and aware(value).astimezone(IST).date() >= today
            }
        )
    return {
        "underlying_key": key,
        "catalog_snapshot_id": metadata["snapshot_id"],
        "expiry_dates": expiries,
        "signal_eligible": False,
        "execution_eligible": False,
    }


def resolve_chain(engine: Engine, request: ChainRequest) -> ChainContext:
    metadata = _underlying(engine, request.underlying_key)
    start = datetime.combine(request.expiry_date, time.min, tzinfo=IST).astimezone(UTC)
    with Session(engine) as db:
        rows = db.scalars(
            select(Instrument).where(
                Instrument.snapshot_id == metadata["snapshot_id"],
                Instrument.underlying_key == request.underlying_key,
                Instrument.instrument_type.in_(["CE", "PE"]),
                Instrument.expiry >= start,
                Instrument.expiry < start + timedelta(days=1),
            )
        )
        contracts: dict[str, CatalogOption] = {}
        strikes: dict[Decimal, set[str]] = {}
        lots: dict[Decimal, int] = {}
        for row in rows:
            if row.strike_price is None or row.strike_price <= 0 or not row.lot_size:
                raise ChainError("INVALID_CATALOG_OPTION")
            kinds = strikes.setdefault(row.strike_price, set())
            if row.instrument_type in kinds:
                raise ChainError("AMBIGUOUS_CATALOG_OPTION")
            if row.strike_price in lots and lots[row.strike_price] != row.lot_size:
                raise ChainError("INCONSISTENT_PAIR_LOT")
            lots[row.strike_price] = row.lot_size
            kinds.add(row.instrument_type)
            contracts[row.instrument_key] = CatalogOption(
                row.instrument_key, row.instrument_type, row.strike_price, row.lot_size
            )
            if len(contracts) > 2 * MAX_STRIKES:
                raise ChainError("CATALOG_CHAIN_LIMIT_EXCEEDED")
    if not contracts:
        raise ChainError("EXPIRY_NOT_IN_CATALOG")
    if any(kinds != {"CE", "PE"} for kinds in strikes.values()):
        raise ChainError("INCOMPLETE_CATALOG_PAIRS")
    return ChainContext(
        metadata["snapshot_id"], request.underlying_key, request.expiry_date, contracts
    )


def _number(value: object, *, greek: bool = False) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not int and not isinstance(value, Decimal):
        raise ChainError("INVALID_MARKET_NUMBER")
    try:
        return (
            GreekNumber(value=Decimal(value)).value
            if greek
            else MarketNumber(value=Decimal(value)).value
        )
    except (ValueError, ValidationError):
        raise ChainError("INVALID_MARKET_NUMBER") from None


def _leg(
    raw: object,
    kind: str,
    strike: Decimal,
    spot: Decimal | None,
    pcr: Decimal | None,
    context: ChainContext,
    seen: set[str],
) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("instrument_key"), str):
        raise ChainError("MISSING_CHAIN_LEG")
    key = raw["instrument_key"]
    contract = context.contracts.get(key)
    if contract is None or contract.option_type != kind or contract.strike_price != strike:
        raise ChainError("CATALOG_LEG_MISMATCH")
    if key in seen:
        raise ChainError("DUPLICATE_CHAIN_LEG")
    seen.add(key)
    market = raw.get("market_data")
    greeks = raw.get("option_greeks")
    if (
        market is not None
        and not isinstance(market, dict)
        or greeks is not None
        and not isinstance(greeks, dict)
    ):
        raise ChainError("INVALID_LEG_SCHEMA")
    market, greeks = market or {}, greeks or {}
    values = {
        name: _number(market.get(name)) for name in ("ltp", "close_price", "bid_price", "ask_price")
    }
    counts = {
        name: quantity(market[name]) if market.get(name) is not None else None
        for name in ("bid_qty", "ask_qty", "volume", "oi", "prev_oi")
    }
    greek_values = {
        name: _number(greeks.get(name), greek=True)
        for name in ("delta", "gamma", "theta", "vega", "iv", "pop")
    }
    delta = greek_values["delta"]
    if delta is not None and not (
        Decimal(0) <= delta <= 1 if kind == "CE" else Decimal(-1) <= delta <= 0
    ):
        raise ChainError("INVALID_OPTION_DELTA")
    for name in ("gamma", "vega", "iv", "pop"):
        greek_value = greek_values[name]
        if greek_value is not None and greek_value < 0:
            raise ChainError("INVALID_OPTION_GREEKS")
    bid, ask = values["bid_price"], values["ask_price"]
    if bid and ask and bid > ask:
        raise ChainError("CROSSED_MARKET")
    spread = ask - bid if bid and ask else None
    flags = []
    if spread is not None and ask and spread / ask > Decimal("0.20"):
        flags.append("WIDE_SPREAD")
    if bid is None or ask is None:
        flags.append("MISSING_QUOTE")
    elif not bid or not ask:
        flags.append("ZERO_QUOTE")
    if not counts["bid_qty"] or not counts["ask_qty"]:
        flags.append("NO_QUOTED_LIQUIDITY")
    if counts["volume"] is None:
        flags.append("MISSING_VOLUME")
    elif counts["volume"] == 0:
        flags.append("ZERO_REPORTED_VOLUME")
    if counts["oi"] is None:
        flags.append("MISSING_OPEN_INTEREST")
    if any(greek_values[name] is None for name in ("delta", "gamma", "theta", "vega", "iv")):
        flags.append("MISSING_GREEKS")
    if not spot:
        flags.append("MISSING_UNDERLYING_PRICE")
    return {
        "instrument_key": key,
        "option_type": kind,
        "strike_price": strike,
        "lot_size": contract.lot_size,
        "underlying_spot": spot,
        "pcr": pcr,
        **values,
        **counts,
        "spread": spread,
        "greeks": {
            name: str(value) if value is not None else None for name, value in greek_values.items()
        },
        "quality_flags": sorted(flags),
    }


def validate_chain(
    request: ChainRequest, payload: BrokerPayload, context: ChainContext
) -> PreparedChain:
    if (
        request.underlying_key != context.underlying_key
        or request.expiry_date != context.expiry_date
    ):
        raise ChainError("CATALOG_REQUEST_MISMATCH")
    if payload.source_url != chain_url(request):
        raise ChainError("SOURCE_IDENTITY_MISMATCH")
    if payload.retrieved_at.tzinfo is None or payload.retrieved_at > datetime.now(UTC) + timedelta(
        minutes=5
    ):
        raise ChainError("INVALID_RETRIEVAL_TIME")
    if len(payload.body) > 3 * 1024 * 1024:
        raise ChainError("RESPONSE_LIMIT_EXCEEDED")
    try:
        body = strict_json(payload.body)
        if (
            not isinstance(body, dict)
            or body.get("status") != "success"
            or not isinstance(body.get("data"), list)
        ):
            raise ChainError("INVALID_CHAIN_ENVELOPE")
        rows = body["data"]
        if len(rows) > MAX_STRIKES:
            raise ChainError("STRIKE_LIMIT_EXCEEDED")
        strikes: set[Decimal] = set()
        seen: set[str] = set()
        legs = []
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("underlying_key") != request.underlying_key
                or row.get("expiry") != request.expiry_date.isoformat()
            ):
                raise ChainError("CHAIN_IDENTITY_MISMATCH")
            strike = _number(row.get("strike_price"))
            if strike is None or strike <= 0:
                raise ChainError("INVALID_STRIKE")
            if strike in strikes:
                raise ChainError("DUPLICATE_CHAIN_STRIKE")
            strikes.add(strike)
            spot, pcr = (
                _number(row.get("underlying_spot_price")),
                _number(row.get("pcr"), greek=True),
            )
            if pcr is not None and pcr < 0:
                raise ChainError("INVALID_PCR")
            legs.extend(
                [
                    _leg(row.get("call_options"), "CE", strike, spot, pcr, context, seen),
                    _leg(row.get("put_options"), "PE", strike, spot, pcr, context, seen),
                ]
            )
        legs.sort(key=lambda leg: (leg["strike_price"], leg["option_type"]))
        canonical = json.dumps(legs, default=str, sort_keys=True, separators=(",", ":")).encode()
        return PreparedChain(
            tuple(legs),
            canonical,
            hashlib.sha256(payload.body).hexdigest(),
            payload.retrieved_at.astimezone(UTC),
            payload.source_url,
        )
    except MarketDataError as error:
        if isinstance(error, ChainError):
            raise
        raise ChainError(str(error)) from None
    except (ValueError, TypeError, OverflowError):
        raise ChainError("INVALID_CHAIN_RESPONSE") from None


def snapshot_info(row: ChainSnapshot) -> dict[str, Any]:
    return {
        "id": row.id,
        "catalog_snapshot_id": row.catalog_snapshot_id,
        "underlying_key": row.underlying_key,
        "expiry_date": row.expiry_date,
        "source_url": row.source_url,
        "response_sha256": row.response_sha256,
        "canonical_sha256": row.canonical_sha256,
        "retrieved_at": aware(row.retrieved_at),
        "imported_at": aware(row.imported_at),
        "strike_count": row.strike_count,
        "leg_count": row.leg_count,
        "flagged_legs": row.flagged_legs,
        "state": "EMPTY" if row.leg_count == 0 else "RESEARCH_SNAPSHOT",
        "freshness": "UNKNOWN",
        "exchange_timestamp": None,
        "signal_eligible": False,
        "execution_eligible": False,
    }


def archive_chain(
    engine: Engine, request: ChainRequest, prepared: PreparedChain, context: ChainContext
) -> dict[str, Any]:
    if (
        request.underlying_key != context.underlying_key
        or request.expiry_date != context.expiry_date
    ):
        raise ChainError("CATALOG_REQUEST_MISMATCH")
    digest = hashlib.sha256(prepared.canonical).hexdigest()
    identity = hashlib.sha256(
        (
            context.snapshot_id
            + request.model_dump_json()
            + digest
            + prepared.retrieved_at.isoformat()
        ).encode()
    ).hexdigest()
    with Session(engine) as db:
        existing = db.get(ChainSnapshot, identity)
        if existing:
            return {**snapshot_info(existing), "deduplicated": True}
        row = ChainSnapshot(
            id=identity,
            catalog_snapshot_id=context.snapshot_id,
            underlying_key=request.underlying_key,
            expiry_date=request.expiry_date,
            source_url=prepared.source_url,
            response_sha256=prepared.response_sha256,
            canonical_sha256=digest,
            retrieved_at=prepared.retrieved_at,
            imported_at=datetime.now(UTC),
            strike_count=len(prepared.legs) // 2,
            leg_count=len(prepared.legs),
            flagged_legs=sum(bool(leg["quality_flags"]) for leg in prepared.legs),
            canonical_payload=prepared.canonical,
        )
        try:
            db.add(row)
            db.flush()
            for offset in range(0, len(prepared.legs), 500):
                db.execute(
                    insert(ChainLeg),
                    [
                        {"snapshot_id": identity, "catalog_snapshot_id": context.snapshot_id, **leg}
                        for leg in prepared.legs[offset : offset + 500]
                    ],
                )
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.get(ChainSnapshot, identity)
            if existing:
                return {**snapshot_info(existing), "deduplicated": True}
            raise
        return {**snapshot_info(row), "deduplicated": False}


def chain_status(engine: Engine) -> dict[str, Any]:
    with Session(engine) as db:
        row = db.scalar(select(ChainSnapshot).order_by(ChainSnapshot.retrieved_at.desc()).limit(1))
        return {
            "latest_snapshot": snapshot_info(row) if row else None,
            "state": "CAPTURED" if row else "NOT_CAPTURED",
            "freshness": "UNKNOWN",
            "entries_enabled": False,
            "live_enabled": False,
            "observation_started_at": None,
        }


def read_chain(
    engine: Engine, identity: str, limit: int, after: str | None
) -> dict[str, Any] | None:
    with Session(engine) as db:
        snapshot = db.get(ChainSnapshot, identity)
        if snapshot is None:
            return None
        query = select(ChainLeg).where(ChainLeg.snapshot_id == identity)
        if after:
            query = query.where(ChainLeg.instrument_key > after)
        rows = list(db.scalars(query.order_by(ChainLeg.instrument_key).limit(limit + 1)))
        page = rows[:limit]

        def serialize(row: ChainLeg) -> dict[str, Any]:
            result: dict[str, Any] = {
                "instrument_key": row.instrument_key,
                "option_type": row.option_type,
                "lot_size": row.lot_size,
                "greeks": row.greeks,
                "quality_flags": row.quality_flags,
                "freshness": "UNKNOWN",
                "signal_eligible": False,
                "execution_eligible": False,
            }
            for name in (
                "strike_price",
                "underlying_spot",
                "pcr",
                "ltp",
                "close_price",
                "bid_price",
                "ask_price",
                "spread",
            ):
                value = getattr(row, name)
                result[name] = str(value) if value is not None else None
            for name in ("bid_qty", "ask_qty", "volume", "oi", "prev_oi"):
                result[name] = getattr(row, name)
            return result

        return {
            "snapshot": snapshot_info(snapshot),
            "legs": [serialize(row) for row in page],
            "next_after": page[-1].instrument_key if len(rows) > limit and page else None,
        }
