"""Bounded read-only feed sessions. No persistence, signal engine or automatic startup."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.feed_authorization import FeedAuthorizationError, FeedGrant
from backend.app.brokers.feed_transport import FeedSocket, FeedTransportError, open_feed
from backend.app.brokers.upstox import BrokerError
from backend.app.market_data.feed import FeedError, FeedFrame, FeedPlan, FeedTick, decode_frame


class LifecycleError(Exception):
    pass


class LifecyclePolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    duration_seconds: float = Field(default=60, ge=1, le=300)
    max_attempts: int = Field(default=3, ge=1, le=3)
    max_frames: int = Field(default=10_000, ge=1, le=10_000)
    first_frame_seconds: float = Field(default=10, gt=0, le=10)
    poll_seconds: float = Field(default=5, gt=0, le=5)
    pong_seconds: float = Field(default=5, gt=0, le=5)
    sink_seconds: float = Field(default=2, gt=0, le=2)
    frame_age_seconds: float = Field(default=10, gt=0, le=10)
    trade_age_seconds: float = Field(default=15, gt=0, le=15)


class FeedAuthorizer(Protocol):
    def credential_state(self) -> str: ...
    async def authorize_feed(self) -> FeedGrant: ...


@dataclass(frozen=True)
class TickObservation:
    tick: FeedTick
    trade_age_seconds: float | None
    freshness: str


@dataclass(frozen=True)
class FeedHealth:
    instrument_key: str
    freshness: str
    trade_age_seconds: float | None
    frame_age_seconds: float | None


@dataclass(frozen=True)
class FeedEvent:
    kind: str
    attempt: int
    frame: FeedFrame | None = None
    observations: tuple[TickObservation, ...] = ()
    duplicates: int = 0
    out_of_order: int = 0
    detail: str | None = None
    signal_eligible: bool = False
    execution_eligible: bool = False
    health: tuple[FeedHealth, ...] = ()
    plan: FeedPlan | None = None
    observed_at: datetime | None = None
    elapsed_ms: int | None = None


class FeedTracker:
    """Per-connection watermarks; never mix subscriptions across reconnects."""

    def __init__(self, policy: LifecyclePolicy, keys: tuple[str, ...] = ()):
        self.policy = policy
        self.keys = keys
        self.source_times: dict[str, datetime] = {}
        self.seen_info = False
        self.seen_snapshot = False
        self.generated_at: datetime | None = None
        self.last_ticks: dict[str, FeedTick] = {}
        self.trade_times: dict[str, datetime] = {}

    def accept(self, frame: FeedFrame, attempt: int) -> FeedEvent:
        if not self.seen_info and frame.message_type != "market_info":
            raise LifecycleError("MARKET_INFO_REQUIRED")
        if self.generated_at and frame.generated_at < self.generated_at:
            return FeedEvent("OUT_OF_ORDER", attempt, out_of_order=len(frame.ticks) or 1)
        self.generated_at = frame.generated_at
        if frame.message_type == "market_info":
            self.seen_info = True
            return FeedEvent("MARKET_INFO", attempt, frame)
        initial = not self.seen_snapshot
        self.seen_snapshot = True  # The broker may label the snapshot live_feed.
        observations = []
        duplicates, out_of_order = 0, 0
        for tick in frame.ticks:
            previous_time = self.trade_times.get(tick.instrument_key)
            if tick.last_trade_at and previous_time and tick.last_trade_at < previous_time:
                out_of_order += 1
                continue
            self.source_times[tick.instrument_key] = frame.generated_at
            if tick == self.last_ticks.get(tick.instrument_key):
                duplicates += 1
                continue
            self.last_ticks[tick.instrument_key] = tick
            if tick.last_trade_at:
                self.trade_times[tick.instrument_key] = tick.last_trade_at
            age = (
                max(0.0, (frame.received_at - tick.last_trade_at).total_seconds())
                if tick.last_trade_at
                else None
            )
            delayed = (frame.received_at - frame.generated_at).total_seconds() > (
                self.policy.frame_age_seconds
            )
            quality = (
                "DELAYED_FRAME"
                if delayed
                else "UNKNOWN_TRADE_TIME"
                if age is None
                else "STALE_TRADE"
                if age > self.policy.trade_age_seconds
                else "ZERO_OR_MISSING_PRICE"
                if not tick.last_price
                else "RECENT_TRADE"
            )
            observations.append(TickObservation(tick, age, quality))
        return FeedEvent(
            "SNAPSHOT" if initial else "UPDATE",
            attempt,
            replace(frame, ticks=tuple(item.tick for item in observations)),
            tuple(observations),
            duplicates,
            out_of_order,
        )

    def health_at(self, now: datetime) -> tuple[FeedHealth, ...]:
        result = []
        for key in sorted(self.keys or tuple(self.last_ticks)):
            tick = self.last_ticks.get(key)
            source = self.source_times.get(key)
            age = (
                max(0.0, (now - tick.last_trade_at).total_seconds())
                if (tick and tick.last_trade_at)
                else None
            )
            source_age = max(0.0, (now - source).total_seconds()) if source else None
            quality = (
                "AWAITING_FIRST_TICK"
                if tick is None
                else "DELAYED_FRAME"
                if source_age is not None and source_age > self.policy.frame_age_seconds
                else "UNKNOWN_TRADE_TIME"
                if age is None
                else "STALE_TRADE"
                if age > self.policy.trade_age_seconds
                else "ZERO_OR_MISSING_PRICE"
                if not tick.last_price
                else "RECENT_TRADE"
            )
            result.append(FeedHealth(key, quality, age, source_age))
        return tuple(result)


class FeedRunner:
    def __init__(
        self,
        authorizer: FeedAuthorizer,
        plan_loader: Callable[[], Awaitable[FeedPlan]],
        sink: Callable[[FeedEvent], Awaitable[None]],
        *,
        policy: LifecyclePolicy | None = None,
        connector: Callable[[FeedGrant], AbstractAsyncContextManager[FeedSocket]] = open_feed,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = lambda: random.uniform(0, 5),
    ):
        self.authorizer, self.plan_loader, self.sink = authorizer, plan_loader, sink
        self.policy = policy or LifecyclePolicy()
        self.connector, self.sleep, self.jitter = connector, sleep, jitter
        self._lock = asyncio.Lock()
        self.state = "STOPPED"
        self.stop_reason: str | None = None
        self.retry_pending = False
        self._started = 0.0
        self.attempts = self.frames = 0

    async def _emit(self, event: FeedEvent) -> None:
        event = replace(
            event,
            observed_at=datetime.now(UTC),
            elapsed_ms=int((asyncio.get_running_loop().time() - self._started) * 1000),
        )
        try:
            async with asyncio.timeout(self.policy.sink_seconds):
                await self.sink(event)
        except TimeoutError:
            raise LifecycleError("FEED_SINK_TIMEOUT") from None
        except Exception:
            raise LifecycleError("FEED_SINK_FAILED") from None

    def _credential_check(self) -> None:
        state = self.authorizer.credential_state()
        if state != "UNVERIFIED":
            raise LifecycleError("FEED_CREDENTIAL_UNAVAILABLE")

    async def _session(self, socket: FeedSocket, plan: FeedPlan) -> None:
        self._credential_check()
        try:
            async with asyncio.timeout(self.policy.first_frame_seconds):
                await socket.send(plan.subscription())
        except TimeoutError:
            raise FeedTransportError("FEED_SUBSCRIBE_TIMEOUT") from None
        tracker = FeedTracker(self.policy, plan.instrument_keys)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.policy.first_frame_seconds
        self.state = "WAIT_MARKET_INFO"
        while self.frames < self.policy.max_frames:
            self._credential_check()
            remaining = deadline - loop.time()
            if not tracker.seen_snapshot and remaining <= 0:
                raise FeedTransportError("FEED_INITIAL_TIMEOUT")
            timeout = (
                self.policy.poll_seconds
                if tracker.seen_snapshot
                else min(self.policy.poll_seconds, remaining)
            )
            try:
                async with asyncio.timeout(timeout):
                    body = await socket.recv()
            except TimeoutError:
                if not tracker.seen_snapshot:
                    continue
                self.state = "IDLE"
                await self._emit(
                    FeedEvent(
                        "IDLE",
                        self.attempts,
                        detail="NO_NEW_FRAME",
                        health=tracker.health_at(datetime.now(UTC)),
                    )
                )
                try:
                    async with asyncio.timeout(self.policy.pong_seconds):
                        pong = await socket.ping()
                        await pong
                except TimeoutError:
                    raise FeedTransportError("FEED_HEARTBEAT_TIMEOUT") from None
                continue  # Pong proves transport health only; never refreshes market prices.
            self._credential_check()  # Do not process a frame received after credential expiry.
            if not isinstance(body, bytes):
                raise LifecycleError("BINARY_FEED_REQUIRED")
            frame = decode_frame(body, plan, datetime.now(UTC))
            self.frames += 1
            event = replace(
                tracker.accept(frame, self.attempts), health=tracker.health_at(datetime.now(UTC))
            )
            if self.state == "WAIT_MARKET_INFO" and tracker.seen_info:
                deadline = loop.time() + self.policy.first_frame_seconds
            self.state = "STREAMING" if tracker.seen_snapshot else "WAIT_SNAPSHOT"
            if tracker.seen_snapshot:
                self.retry_pending = False
            await self._emit(event)
        self.stop_reason = "FRAME_LIMIT"

    def elapsed_ms(self) -> int:
        return (
            int((asyncio.get_running_loop().time() - self._started) * 1000) if self._started else 0
        )

    async def run(self) -> dict[str, object]:
        if self._lock.locked():
            raise LifecycleError("FEED_ALREADY_RUNNING")
        async with self._lock:
            self.attempts = self.frames = 0
            self.stop_reason = None
            self.retry_pending = False
            self._started = asyncio.get_running_loop().time()
            try:
                async with asyncio.timeout(self.policy.duration_seconds):
                    for attempt in range(1, self.policy.max_attempts + 1):
                        self.attempts = attempt
                        self.state = "AUTHORIZING"
                        try:
                            self._credential_check()
                            plan = await self.plan_loader()  # Re-resolve current catalog each time.
                            await self._emit(FeedEvent("PLAN", attempt, plan=plan))
                            grant = await self.authorizer.authorize_feed()
                            async with self.connector(grant) as socket:
                                await self._session(socket, plan)
                            break
                        except (BrokerError, FeedTransportError) as error:
                            self.retry_pending = True
                            retry = (
                                error.code in {"UNAVAILABLE", "RATE_LIMITED"}
                                if isinstance(error, BrokerError)
                                else error.retryable
                            )
                            await self._emit(FeedEvent("DISCONNECTED", attempt, detail=error.code))
                            if not retry or attempt == self.policy.max_attempts:
                                self.stop_reason = error.code
                                break
                            delay = max(30 * 2 ** (attempt - 1), error.retry_after)
                            delay += max(0, min(self.jitter(), 5))
                            self.state = "BACKOFF"
                            await self._emit(FeedEvent("BACKOFF", attempt, detail=str(delay)))
                            await self.sleep(delay)
            except TimeoutError:
                self.stop_reason = "DURATION_LIMIT"
            except (FeedError, FeedAuthorizationError, LifecycleError) as error:
                self.stop_reason = str(error)
            except Exception:
                self.stop_reason = "FEED_INTERNAL_ERROR"
            except asyncio.CancelledError:
                self.stop_reason = "CANCELLED"
                raise
            finally:
                self.state = "STOPPED"
            return {
                "run_elapsed_ms": self.elapsed_ms(),
                "retry_pending": self.retry_pending,
                "state": self.state,
                "reason": self.stop_reason,
                "attempts": self.attempts,
                "frames": self.frames,
                "entries_enabled": False,
                "live_enabled": False,
                "observation_started_at": None,
            }
