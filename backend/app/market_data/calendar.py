"""Versioned NSE derivatives schedule evidence; no assertion of amendment completeness."""

import hashlib
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.market_data.contracts import IST

DATA = Path(__file__).with_name("calendar_data")


class CalendarError(Exception):
    pass


class SpecialWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opens: time
    closes: time
    source: str = Field(max_length=80)


class CalendarPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    kind: Literal["OFFICIAL_BASELINE", "SYNTHETIC_FIXTURE"]
    segment: Literal["NSE_FO"]
    reviewed_at: AwareDatetime
    valid_from: date
    valid_through: date
    regular_from: date
    regular_open: time
    regular_close: time
    holidays: dict[date, str]
    special: dict[date, SpecialWindow]
    evidence_sha256: dict[str, str]

    @model_validator(mode="after")
    def boundaries(self) -> "CalendarPolicy":
        if not self.valid_from <= self.regular_from <= self.valid_through:
            raise ValueError("Invalid calendar validity")
        if (self.valid_through - self.valid_from).days > 366:
            raise ValueError("Calendar year bound")
        times = [(self.regular_open, self.regular_close)] + [
            (window.opens, window.closes) for window in self.special.values()
        ]
        if any(start.tzinfo or end.tzinfo or start >= end for start, end in times):
            raise ValueError("Invalid local session window")
        if any(
            not self.valid_from <= day <= self.valid_through
            for day in (*self.holidays, *self.special)
        ):
            raise ValueError("Calendar date outside validity")
        return self

    @property
    def identity(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def day(self, day: date) -> dict[str, Any]:
        opened = closed = None
        source: str | None = None
        if not self.valid_from <= day <= self.valid_through:
            state = "UNKNOWN_CALENDAR"
        elif day in self.special:
            window = self.special[day]
            opened, closed, source = window.opens, window.closes, window.source
            state = "SPECIAL_SESSION"
        elif day in self.holidays:
            state, source = "HOLIDAY", self.holidays[day]
        elif day.weekday() >= 5:
            state = "WEEKEND"
        elif day < self.regular_from:
            state = "UNKNOWN_HOURS"
        else:
            state, source = "REGULAR_BASELINE", "market-timings.html"
            opened, closed = self.regular_open, self.regular_close
        return {
            "date": day,
            "state": state,
            "source_ref": source,
            "opens_at": datetime.combine(day, opened, IST).astimezone(UTC) if opened else None,
            "closes_at": datetime.combine(day, closed, IST).astimezone(UTC) if closed else None,
        }

    def provenance(self) -> dict[str, Any]:
        return {
            "id": self.identity,
            "kind": self.kind,
            "segment": self.segment,
            "timezone": "Asia/Kolkata",
            "reviewed_at": self.reviewed_at,
            "valid_from": self.valid_from,
            "valid_through": self.valid_through,
            "regular_hours_review_from": self.regular_from,
            "evidence_sha256": self.evidence_sha256,
            "amendment_completeness_verified": False,
            "realtime_calendar": False,
            "source_urls": {
                name: (
                    "https://www.nseindia.com/static/market-data/market-timings"
                    if name == "market-timings.html"
                    else "https://nsearchives.nseindia.com/content/circulars/" + name
                )
                for name in self.evidence_sha256
                if name != "sources.json"
            },
        }


@lru_cache(maxsize=1)
def load_calendar() -> CalendarPolicy:
    try:
        policy = CalendarPolicy.model_validate_json((DATA / "nse_fo_2026.json").read_bytes())
        allowed = {
            "sources.json",
            "FAOP71777.pdf",
            "FAOP72262.pdf",
            "FAOP76940.pdf",
            "market-timings.html",
        }
        if set(policy.evidence_sha256) != allowed:
            raise ValueError
        for name, digest in policy.evidence_sha256.items():
            if hashlib.sha256((DATA / name).read_bytes()).hexdigest() != digest:
                raise ValueError
        return policy
    except (OSError, ValueError):
        raise CalendarError("CALENDAR_EVIDENCE_INVALID") from None


def calendar_days(start: date, end: date, policy: CalendarPolicy | None = None) -> dict[str, Any]:
    if end < start or (end - start).days >= 31:
        raise CalendarError("CALENDAR_RANGE_LIMIT")
    policy = policy or load_calendar()
    return {
        "calendar": policy.provenance(),
        "days": [policy.day(start + timedelta(days=i)) for i in range((end - start).days + 1)],
        "qualifying_observation_days": 0,
        "signal_eligible": False,
        "execution_eligible": False,
    }
