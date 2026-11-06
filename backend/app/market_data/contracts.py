"""Bounded historical-minute request contract; no trading instructions."""

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IST = ZoneInfo("Asia/Kolkata")


class CandleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    instrument_key: str = Field(min_length=3, max_length=160)
    interval: Literal[1, 5, 15] = 1
    from_date: date
    to_date: date

    @field_validator("instrument_key")
    @classmethod
    def opaque_key(cls, value: str) -> str:
        if not value.startswith(("NSE_INDEX|", "NSE_FO|")) or any(
            character in "/\\?#%" or ord(character) < 32 for character in value
        ):
            raise ValueError("Use an opaque NSE catalog key, not a URL/path")
        return value

    @field_validator("interval", mode="before")
    @classmethod
    def integer_interval(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Interval must be a supported integer")
        return value

    @model_validator(mode="after")
    def supported_window(self) -> "CandleRequest":
        if isinstance(self.interval, bool):
            raise ValueError("Interval must be a supported minute count")
        if not timedelta(0) <= self.to_date - self.from_date <= timedelta(days=27):
            raise ValueError("Use an ordered window of at most28 calendar days")
        if self.from_date < date(2022, 1, 1):
            raise ValueError("Minute history predates supported availability")
        if self.to_date >= datetime.now(UTC).astimezone(IST).date():
            raise ValueError("Historical import ends before today's IST session")
        return self


def history_url(request: CandleRequest) -> str:
    from urllib.parse import quote

    return (
        "https://api.upstox.com/v3/historical-candle/"
        f"{quote(request.instrument_key, safe='')}/minutes/{request.interval}/"
        f"{request.to_date.isoformat()}/{request.from_date.isoformat()}"
    )
