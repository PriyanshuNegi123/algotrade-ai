"""Only explicit catalog index keys and expiry dates; no rollover/trading instructions."""

from datetime import UTC, date, datetime
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.market_data.contracts import IST


class ChainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    underlying_key: str = Field(min_length=11, max_length=160)
    expiry_date: date

    @field_validator("underlying_key")
    @classmethod
    def index_key(cls, value: str) -> str:
        if (
            not value.startswith("NSE_INDEX|")
            or not value[10:].strip()
            or any(
                character in "/\\?#%" or ord(character) < 32 or ord(character) == 127
                for character in value
            )
        ):
            raise ValueError("Use an opaque imported NSE index key")
        return value

    @field_validator("expiry_date")
    @classmethod
    def unexpired_date(cls, value: date) -> date:
        if value < datetime.now(UTC).astimezone(IST).date():
            raise ValueError("Expired-chain requests are unsupported")
        return value


def chain_url(request: ChainRequest) -> str:
    return "https://api.upstox.com/v2/option/chain?" + urlencode(
        {
            "instrument_key": request.underlying_key,
            "expiry_date": request.expiry_date.isoformat(),
        }
    )
