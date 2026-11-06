"""Allowlisted canonical archive contract; no credential-bearing URL or raw broker body."""

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from backend.app.market_data.feed import FeedRequest

Freshness = Literal[
    "AWAITING_FIRST_TICK",
    "DELAYED_FRAME",
    "UNKNOWN_TRADE_TIME",
    "STALE_TRADE",
    "ZERO_OR_MISSING_PRICE",
    "RECENT_TRADE",
]
Key = Annotated[str, Field(min_length=1, max_length=160)]
Age = Annotated[float, Field(ge=0, le=1e12, allow_inf_nan=False)]
Price = Annotated[Decimal, Field(ge=0, lt=1e16, allow_inf_nan=False)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class CapturedTick(Record):
    instrument_key: Key
    last_price: Price
    last_trade_at: AwareDatetime | None
    last_quantity: int = Field(ge=0, le=9_223_372_036_854_775_807)
    close_price: Price
    indicative_price: Price | None
    quality_flags: tuple[
        Literal[
            "PROTO3_SCALAR_PRESENCE_UNKNOWN",
            "WIRE_DOUBLE_PRICE",
            "ZERO_OR_MISSING_PRICE",
            "ZERO_OR_MISSING_CLOSE",
            "MISSING_TRADE_TIME",
        ],
        ...,
    ] = Field(max_length=5)
    freshness: Literal["NOT_EVALUATED"]
    signal_eligible: Literal[False]
    execution_eligible: Literal[False]


class CapturedObservation(Record):
    tick: CapturedTick
    trade_age_seconds: Age | None
    freshness: Freshness


class CapturedHealth(Record):
    instrument_key: Key
    freshness: Freshness
    trade_age_seconds: Age | None
    frame_age_seconds: Age | None


class CapturedPlan(FeedRequest):
    catalog_snapshot_id: str = Field(pattern="^[0-9a-f]{64}$")
    mode: Literal["ltpc"]


class CapturedFrame(Record):
    catalog_snapshot_id: str = Field(pattern="^[0-9a-f]{64}$")
    message_type: Literal["initial_feed", "live_feed", "market_info"]
    generated_at: AwareDatetime
    received_at: AwareDatetime
    market_status: tuple[
        tuple[
            Annotated[str, Field(pattern="^[A-Z][A-Z0-9_]{0,39}$")],
            Literal[
                "PRE_OPEN_START",
                "PRE_OPEN_END",
                "NORMAL_OPEN",
                "NORMAL_CLOSE",
                "CLOSING_START",
                "CLOSING_END",
            ],
        ],
        ...,
    ] = Field(max_length=64)
    signal_eligible: Literal[False]
    execution_eligible: Literal[False]


class CapturedEvent(Record):
    kind: Literal[
        "PLAN",
        "MARKET_INFO",
        "SNAPSHOT",
        "UPDATE",
        "IDLE",
        "OUT_OF_ORDER",
        "DISCONNECTED",
        "BACKOFF",
    ]
    attempt: int = Field(ge=1, le=3)
    frame: CapturedFrame | None
    observations: tuple[CapturedObservation, ...] = Field(max_length=100)
    duplicates: int = Field(ge=0, le=100)
    out_of_order: int = Field(ge=0, le=100)
    detail: str | None = Field(max_length=64)
    signal_eligible: Literal[False]
    execution_eligible: Literal[False]
    health: tuple[CapturedHealth, ...] = Field(max_length=100)
    plan: CapturedPlan | None
    observed_at: AwareDatetime
    elapsed_ms: int = Field(ge=0, le=330_000)

    @model_validator(mode="after")
    def shape(self) -> "CapturedEvent":
        if (self.kind == "PLAN") != (self.plan is not None):
            raise ValueError("Plan event required")
        if (self.kind in {"MARKET_INFO", "SNAPSHOT", "UPDATE"}) != (self.frame is not None):
            raise ValueError("Frame/event mismatch")
        if self.observations and self.kind not in {"SNAPSHOT", "UPDATE"}:
            raise ValueError("Unexpected ticks")
        if self.frame:
            if (self.kind == "MARKET_INFO") != (self.frame.message_type == "market_info"):
                raise ValueError("Market status mismatch")
            if self.frame.generated_at > self.frame.received_at + timedelta(seconds=5):
                raise ValueError("Future generation")
            if self.frame.received_at > self.observed_at + timedelta(seconds=5):
                raise ValueError("Future receipt")
            if any(
                item.tick.last_trade_at
                and item.tick.last_trade_at > (self.frame.generated_at + timedelta(seconds=5))
                for item in self.observations
            ):
                raise ValueError("Future trade")
        return self


SAFE_REASONS = frozenset(
    {
        "FRAME_LIMIT",
        "DURATION_LIMIT",
        "CANCELLED",
        "LEASE_EXPIRED",
        "UNCLASSIFIED_STOP",
        "FEED_SINK_TIMEOUT",
        "FEED_SINK_FAILED",
        "FEED_INTERNAL_ERROR",
        "FEED_ALREADY_RUNNING",
        "FEED_CREDENTIAL_UNAVAILABLE",
        "MARKET_INFO_REQUIRED",
        "BINARY_FEED_REQUIRED",
        "NOT_CONFIGURED",
        "EXPIRED",
        "AUTH_REQUIRED",
        "ACCESS_DENIED",
        "RATE_LIMITED",
        "UNAVAILABLE",
        "INVALID_RESPONSE",
        "INVALID_FEED_GRANT",
        "FEED_GRANT_UNAVAILABLE",
        "CURRENT_CATALOG_REQUIRED",
        "FEED_KEY_NOT_IN_CATALOG",
        "UNSUPPORTED_FEED_INSTRUMENT",
        "EXPIRED_FEED_INSTRUMENT",
        "INVALID_FEED_FRAME_SIZE",
        "NAIVE_FEED_RECEIPT",
        "INVALID_FEED_PLAN",
        "INVALID_FEED_PROTOBUF",
        "INVALID_FEED_TIMESTAMP",
        "FUTURE_FEED_TIMESTAMP",
        "UNSUPPORTED_FEED_TYPE",
        "FEED_KEY_LIMIT_EXCEEDED",
        "INVALID_MARKET_INFO",
        "MARKET_SEGMENT_LIMIT_EXCEEDED",
        "UNSUPPORTED_MARKET_STATUS",
        "UNEXPECTED_MARKET_INFO",
        "UNSUBSCRIBED_FEED_KEY",
        "UNSUPPORTED_FEED_MODE",
        "FUTURE_TRADE_TIMESTAMP",
        "INVALID_FEED_QUANTITY",
        "INVALID_FEED_PRICE",
        "FEED_REDIRECT_BLOCKED",
        "FEED_ACCESS_DENIED",
        "FEED_RATE_LIMITED",
        "FEED_HANDSHAKE_FAILED",
        "FEED_TLS_FAILED",
        "FEED_DISCONNECTED",
        "FEED_UNAVAILABLE",
        "FEED_SUBSCRIBE_TIMEOUT",
        "FEED_INITIAL_TIMEOUT",
        "FEED_HEARTBEAT_TIMEOUT",
    }
)
