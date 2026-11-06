"""Bounded, read-only per-key sampled coverage. Unsampled time never becomes certified days."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, undefer

from backend.app.market_data.calendar import CalendarPolicy, load_calendar
from backend.app.market_data.contracts import IST
from backend.app.market_data.observation_models import ObservationEvent, ObservationSession
from backend.app.market_data.observation_schema import CapturedEvent

MAX_SESSIONS = 100
MAX_EVENTS = 20_000
MAX_BYTES = 8 * 1024 * 1024


class CoverageError(Exception):
    pass


class CoverageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    from_date: date
    to_date: date
    instrument_keys: tuple[
        Annotated[str, Field(pattern=r"^NSE_FO\|[^|/\\?#\x00-\x1f\x7f]{1,153}$")], ...
    ] = Field(min_length=1, max_length=20)
    source: Literal["UPSTOX_V3", "SYNTHETIC"] = "UPSTOX_V3"

    @field_validator("instrument_keys")
    @classmethod
    def distinct(cls, keys: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(keys)) != len(keys) or any(key != key.strip() for key in keys):
            raise ValueError("Duplicate or padded keys")
        return keys

    @model_validator(mode="after")
    def bounds(self) -> "CoverageRequest":
        if (
            self.from_date.year < 1970
            or self.to_date.year > 9998
            or self.to_date < self.from_date
            or (self.to_date - self.from_date).days >= 7
        ):
            raise ValueError("Coverage range exceeds seven dates")
        return self


def _ms(delta: timedelta) -> int:
    return int(delta.total_seconds() * 1000)


def _union(intervals: list[tuple[datetime, datetime]]) -> int:
    total = 0
    end: datetime | None = None
    for left, right in sorted(intervals):
        if end is None or left > end:
            total += _ms(right - left)
            end = right
        elif right > end:
            total += _ms(right - end)
            end = right
    return total


@dataclass
class Samples:
    previous: dict[str, tuple[datetime, int, int]] = field(default_factory=dict)
    intervals: dict[tuple[date, str], list[tuple[datetime, datetime]]] = field(default_factory=dict)
    counts: dict[tuple[date, str], int] = field(default_factory=dict)
    outside: int = 0

    def accept(
        self, event: CapturedEvent, request: CoverageRequest, policy: CalendarPolicy, now: datetime
    ) -> None:
        frame = event.frame
        if not frame or event.kind not in {"SNAPSHOT", "UPDATE"} or not event.observations:
            self.previous.clear()
            return
        received = frame.received_at.astimezone(UTC)
        day = received.astimezone(IST).date()
        window = policy.day(day)
        opened, closed = window["opens_at"], window["closes_at"]
        if (
            not request.from_date <= day <= request.to_date
            or not opened
            or not closed
            or not opened <= received < min(closed, now)
            or not 0 <= (received - frame.generated_at).total_seconds() <= 10
        ):
            self.previous.clear()
            self.outside += 1
            return
        accepted = set()
        for observation in event.observations:
            tick = observation.tick
            key, trade = tick.instrument_key, tick.last_trade_at
            if key not in request.instrument_keys or not trade or tick.last_price <= 0:
                continue
            if not 0 <= (received - trade).total_seconds() <= 15:
                continue
            accepted.add(key)
            self.counts[(day, key)] = self.counts.get((day, key), 0) + 1
            previous = self.previous.get(key)
            if previous:
                prior, elapsed, attempt = previous
                delta = event.elapsed_ms - elapsed
                wall = _ms(received - prior)
                if (
                    attempt == event.attempt
                    and prior.astimezone(IST).date() == day
                    and 0 < delta <= 10_000
                    and 0 < wall <= 10_000
                ):
                    left = max(opened, received - timedelta(milliseconds=min(delta, wall)))
                    self.intervals.setdefault((day, key), []).append(
                        (left, min(received, closed, now))
                    )
            self.previous[key] = (received, event.elapsed_ms, event.attempt)
        # A frame which omits a requested key cannot bridge its missing evidence interval.
        for key in set(self.previous) - accepted:
            del self.previous[key]


def coverage_report(
    engine: Engine,
    request: CoverageRequest,
    *,
    policy: CalendarPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy, now = policy or load_calendar(), now or datetime.now(UTC)
    if now.tzinfo is None:
        raise CoverageError("AWARE_REPORT_TIME_REQUIRED")
    start = datetime.combine(request.from_date, time.min, IST).astimezone(UTC)
    end = datetime.combine(request.to_date + timedelta(days=1), time.min, IST).astimezone(UTC)
    isolation = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"
    samples = Samples()
    session_ids = []
    counters = {"events": 0, "duplicates": 0, "out_of_order": 0, "disconnects": 0}
    with engine.connect().execution_options(isolation_level=isolation) as connection:
        with connection.begin(), Session(bind=connection) as db:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                connection.execute(text("SET TRANSACTION READ ONLY"))
            sessions = list(
                db.scalars(
                    select(ObservationSession)
                    .where(
                        ObservationSession.source == request.source,
                        ObservationSession.created_at < end,
                        ObservationSession.lease_expires_at >= start,
                    )
                    .order_by(ObservationSession.id)
                    .limit(MAX_SESSIONS + 1)
                )
            )
            sessions = (
                [row for row in sessions if set(row.requested_keys) & set(request.instrument_keys)]
                if len(sessions) <= MAX_SESSIONS
                else sessions
            )
            if (
                len(sessions) > MAX_SESSIONS
                or sum(row.payload_bytes for row in sessions) > MAX_BYTES
            ):
                raise CoverageError("COVERAGE_REPORT_LIMIT")
            for row in sessions:
                session_ids.append(row.id)
                samples.previous.clear()  # Never bridge distinct processes/sessions.
                events = list(
                    db.scalars(
                        select(ObservationEvent)
                        .options(undefer(ObservationEvent.payload))
                        .where(ObservationEvent.session_id == row.id)
                        .order_by(ObservationEvent.sequence)
                        .limit(MAX_EVENTS - counters["events"] + 1)
                    )
                )
                if counters["events"] + len(events) > MAX_EVENTS:
                    raise CoverageError("COVERAGE_REPORT_LIMIT")
                for stored in events:
                    try:
                        canonical = json.dumps(
                            stored.payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                        ).encode()
                    except (ValueError, TypeError):
                        raise CoverageError("COVERAGE_ARCHIVE_INVALID") from None
                    if hashlib.sha256(canonical).hexdigest() != stored.payload_sha256:
                        raise CoverageError("COVERAGE_ARCHIVE_INVALID")
                    try:
                        item = CapturedEvent.model_validate(stored.payload)
                    except ValidationError:
                        raise CoverageError("COVERAGE_ARCHIVE_INVALID") from None
                    counters["events"] += 1
                    counters["duplicates"] += item.duplicates
                    counters["out_of_order"] += item.out_of_order
                    counters["disconnects"] += int(item.kind == "DISCONNECTED")
                    samples.accept(item, request, policy, now)
    days = []
    for index in range((request.to_date - request.from_date).days + 1):
        day = request.from_date + timedelta(days=index)
        window = policy.day(day)
        opened, closed = window["opens_at"], window["closes_at"]
        scheduled = (
            _ms(closed - opened)
            if opened and closed
            else (0 if window["state"] in {"HOLIDAY", "WEEKEND"} else None)
        )
        elapsed = max(0, _ms(min(now, closed) - opened)) if opened and closed else scheduled
        keys = []
        for key in request.instrument_keys:
            covered = _union(samples.intervals.get((day, key), []))
            keys.append(
                {
                    "instrument_key": key,
                    "accepted_samples": samples.counts.get((day, key), 0),
                    "sampled_interval_ms": covered,
                    "uncovered_elapsed_ms": max(0, elapsed - covered)
                    if elapsed is not None
                    else None,
                    "sampled_fraction": covered / elapsed if elapsed else None,
                    "state": "SAMPLED_EVIDENCE" if covered else "NO_RECORDED_INTERVAL",
                }
            )
        days.append(
            {**window, "scheduled_ms": scheduled, "elapsed_scheduled_ms": elapsed, "keys": keys}
        )
    return {
        "calendar": policy.provenance(),
        "as_of": now,
        "source": request.source,
        "session_ids": session_ids,
        "counts": counters,
        "outside_or_unusable_frames": samples.outside,
        "days": days,
        "coverage_kind": "CONSERVATIVE_SAMPLED_SPANS",
        "calendar_verified": False,
        "qualifying_observation_days": 0,
        "signal_eligible": False,
        "execution_eligible": False,
        "live_enabled": False,
    }
