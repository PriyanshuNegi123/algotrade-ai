import asyncio
import time
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from starlette.concurrency import run_in_threadpool

from backend.app.auth.service import require_admin
from backend.app.brokers.upstox import BrokerError, ReadOnlyUpstox
from backend.app.market_data.contracts import CandleRequest
from backend.app.market_data.history import (
    CandleError,
    archive_candles,
    history_status,
    read_batch,
    resolve_instrument,
    validate_history,
)

router = APIRouter(prefix="/api/candles", dependencies=[Depends(require_admin)])


class HistoryGate:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.next_attempt = 0.0


def get_history_broker(request: Request) -> ReadOnlyUpstox:
    return ReadOnlyUpstox(request.app.state.settings)


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    return history_status(request.app.state.engine)


@router.post("/import")
async def import_history(
    payload: CandleRequest,
    request: Request,
    broker: Annotated[ReadOnlyUpstox, Depends(get_history_broker)],
) -> dict[str, object]:
    gate = cast(HistoryGate, request.app.state.history_gate)
    async with gate.lock:
        remaining = gate.next_attempt - time.monotonic()
        if remaining > 0:
            raise HTTPException(
                429, "HISTORY_COOLDOWN", headers={"Retry-After": str(int(remaining) + 1)}
            )
        try:
            metadata = await run_in_threadpool(
                resolve_instrument, request.app.state.engine, payload
            )
            gate.next_attempt = time.monotonic() + 30
            downloaded = await broker.historical_candles(payload)
            prepared = await run_in_threadpool(validate_history, payload, downloaded)
            result = await run_in_threadpool(
                archive_candles, request.app.state.engine, payload, prepared, metadata
            )
            return {"import": result, "entries_enabled": False, "live_enabled": False}
        except BrokerError as error:
            if error.code == "RATE_LIMITED":
                gate.next_attempt = max(gate.next_attempt, time.monotonic() + error.retry_after)
            code = 429 if error.code == "RATE_LIMITED" else 503
            headers = {"Retry-After": str(error.retry_after)} if code == 429 else None
            raise HTTPException(code, error.code, headers=headers) from None
        except CandleError as error:
            raise HTTPException(422, str(error)) from None


@router.get("/batches/{identity}")
def batch(
    identity: Annotated[str, Path(pattern="^[0-9a-f]{64}$")],
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    after: datetime | None = None,
) -> dict[str, object]:
    try:
        result = read_batch(request.app.state.engine, identity, limit, after)
    except CandleError as error:
        raise HTTPException(422, str(error)) from None
    if result is None:
        raise HTTPException(404, "CANDLE_IMPORT_NOT_FOUND")
    return result
