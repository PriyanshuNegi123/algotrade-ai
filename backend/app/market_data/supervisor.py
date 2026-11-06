"""Explicit bounded capture orchestration; no automatic service or trading activation."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, TypeVar

from sqlalchemy.engine import Engine

from backend.app.brokers.feed_authorization import FeedGrant
from backend.app.brokers.feed_transport import FeedSocket, open_feed
from backend.app.market_data.feed import FeedPlan, FeedRequest, resolve_feed
from backend.app.market_data.feed_lifecycle import (
    FeedAuthorizer,
    FeedEvent,
    FeedRunner,
    LifecyclePolicy,
)
from backend.app.market_data.observations import ObservationWriter, recover_abandoned, start_session
from backend.app.market_data.supervision_store import (
    CaptureError,
    CapturePolicy,
    capture_stop_requested,
    create_capture,
    finish_capture,
    read_capture,
    recover_captures,
)

T = TypeVar("T")


class CaptureSupervisor:
    def __init__(
        self,
        engine: Engine,
        request: FeedRequest,
        authorizer: FeedAuthorizer,
        *,
        policy: CapturePolicy | None = None,
        source: Literal["UPSTOX_V3", "SYNTHETIC"] = "UPSTOX_V3",
        stop: asyncio.Event | None = None,
        connector: Callable[[FeedGrant], AbstractAsyncContextManager[FeedSocket]] = open_feed,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        event_sink: Callable[[FeedEvent], Awaitable[None]] | None = None,
        child_policy: LifecyclePolicy | None = None,
    ):
        self.engine, self.request, self.authorizer = engine, request, authorizer
        self.policy, self.source = policy or CapturePolicy(), source
        self.stop = stop or asyncio.Event()
        self.connector, self.sleep, self.event_sink = connector, sleep, event_sink
        self.child_policy = child_policy or LifecyclePolicy()
        self._lock = asyncio.Lock()
        self._cancelled = False
        self.identity: str | None = None
        self.quota_error: str | None = None

    async def _db(self, function: Callable[..., T], *args: Any) -> T:
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Retain the created identity/result before acting on cancellation. No orphan
            # child is left merely because cancellation arrived during session creation.
            self._cancelled = True
            self.stop.set()
            return await asyncio.shield(task)

    async def _wait(self, task: asyncio.Future[Any], remaining: float) -> bool:
        stopped = asyncio.create_task(self.stop.wait())
        deadline = asyncio.get_running_loop().time() + max(0, remaining)
        try:
            while True:
                left = max(0, deadline - asyncio.get_running_loop().time())
                done, _ = await asyncio.wait(
                    {task, stopped}, timeout=min(left, 0.5), return_when=asyncio.FIRST_COMPLETED
                )
                if self.identity is not None:
                    requested: bool = await self._db(
                        capture_stop_requested, self.engine, self.identity
                    )
                    if requested:
                        self.stop.set()
                if self.stop.is_set():
                    return False
                if task in done:
                    return True
                if asyncio.get_running_loop().time() >= deadline:
                    return False
        except asyncio.CancelledError:
            self._cancelled = True
            self.stop.set()
            return False
        finally:
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)

    async def _cancel(self, task: asyncio.Future[Any]) -> None:
        task.cancel()
        results = await asyncio.gather(task, return_exceptions=True)
        if results and isinstance(results[0], Exception):
            raise CaptureError("CAPTURE_CHILD_CLEANUP_FAILED")

    async def run(self) -> dict[str, Any]:
        if self._lock.locked():
            raise CaptureError("CAPTURE_ALREADY_RUNNING")
        async with self._lock:
            self._cancelled, self.quota_error = False, None
            if self.stop.is_set():
                return {"capture": None, "reason": "COOPERATIVE_STOP", "live_enabled": False}
            started = asyncio.get_running_loop().time()
            await self._db(recover_captures, self.engine)
            await self._db(recover_abandoned, self.engine)
            if self.stop.is_set():
                if self._cancelled:
                    raise asyncio.CancelledError
                return {"capture": None, "reason": "COOPERATIVE_STOP", "live_enabled": False}
            self.identity = await self._db(
                create_capture, self.engine, self.request, self.policy, self.source
            )
            reason = "SESSION_LIMIT"
            task: asyncio.Future[Any] | None = None
            writer: ObservationWriter | None = None
            runner: FeedRunner | None = None
            try:
                for number in range(self.policy.max_sessions):
                    remaining = self.policy.total_seconds - (
                        asyncio.get_running_loop().time() - started
                    )
                    if self.stop.is_set() or remaining < 1:
                        reason = (
                            "CANCELLED"
                            if self._cancelled
                            else "COOPERATIVE_STOP"
                            if self.stop.is_set()
                            else "TOTAL_DURATION_LIMIT"
                        )
                        break
                    child_policy = self.child_policy.model_copy(
                        update={
                            "duration_seconds": min(self.policy.session_seconds, int(remaining))
                        }
                    )
                    identity = await self._db(
                        start_session,
                        self.engine,
                        self.request,
                        child_policy,
                        self.source,
                        self.identity,
                    )
                    active_writer = ObservationWriter(self.engine, identity)
                    writer = active_writer
                    snapshot_seen = False

                    async def load() -> FeedPlan:
                        return await asyncio.to_thread(resolve_feed, self.engine, self.request)

                    async def sink(
                        event: FeedEvent, current_writer: ObservationWriter = active_writer
                    ) -> None:
                        nonlocal snapshot_seen
                        try:
                            await current_writer.append(event)
                        except CaptureError as error:
                            self.quota_error = str(error)
                            raise
                        if event.kind == "SNAPSHOT":
                            snapshot_seen = True
                        if self.event_sink:
                            await self.event_sink(event)

                    active_runner = FeedRunner(
                        self.authorizer, load, sink, policy=child_policy, connector=self.connector
                    )

                    runner = active_runner

                    async def capture_child(
                        runner: FeedRunner = active_runner,
                        writer: ObservationWriter = active_writer,
                    ) -> dict[str, object]:
                        try:
                            result = await runner.run()
                        except asyncio.CancelledError:
                            await writer.finish("CANCELLED", runner.elapsed_ms())
                            raise
                        await writer.finish(str(result["reason"]), runner.elapsed_ms())
                        return result

                    if self.stop.is_set():
                        await writer.finish("CANCELLED", 0)
                        reason = "CANCELLED" if self._cancelled else "COOPERATIVE_STOP"
                        break
                    task = asyncio.create_task(capture_child())
                    remaining = self.policy.total_seconds - (
                        asyncio.get_running_loop().time() - started
                    )
                    completed = await self._wait(task, remaining)
                    if not completed:
                        await self._cancel(task)
                        task = None
                        reason = (
                            "CANCELLED"
                            if self._cancelled
                            else "COOPERATIVE_STOP"
                            if self.stop.is_set()
                            else "TOTAL_DURATION_LIMIT"
                        )
                        break
                    result = await task
                    task = None
                    if self.quota_error:
                        reason = self.quota_error
                        break
                    if (
                        result["reason"] not in {"FRAME_LIMIT", "DURATION_LIMIT"}
                        or result["retry_pending"]
                    ):
                        reason = "CHILD_FAILED"
                        break
                    if not snapshot_seen:
                        reason = "CHILD_NOT_STREAMING"
                        break
                    if number + 1 < self.policy.max_sessions:
                        # Rollover never resets authorization throttling with an immediate dial.
                        task = asyncio.ensure_future(self.sleep(30))
                        remaining = self.policy.total_seconds - (
                            asyncio.get_running_loop().time() - started
                        )
                        if not await self._wait(task, remaining):
                            await self._cancel(task)
                            task = None
                            reason = (
                                "CANCELLED"
                                if self._cancelled
                                else "COOPERATIVE_STOP"
                                if self.stop.is_set()
                                else "TOTAL_DURATION_LIMIT"
                            )
                            break
                        await task
                        task = None
            except asyncio.CancelledError:
                self._cancelled = True
                self.stop.set()
                reason = "CANCELLED"
            except CaptureError as error:
                reason = str(error)
            except Exception:
                reason = "INTERNAL_ERROR"
            finally:
                if task is not None:
                    await self._cancel(task)
                if writer is not None and runner is not None:
                    await writer.finish("CANCELLED", runner.elapsed_ms())
                await self._db(finish_capture, self.engine, self.identity, reason)
            if self._cancelled:
                raise asyncio.CancelledError
            final = await self._db(read_capture, self.engine, self.identity)
            if self._cancelled:
                raise asyncio.CancelledError
            if final is None:
                raise CaptureError("CAPTURE_NOT_FOUND")
            return final
