import asyncio
import time
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from starlette.concurrency import run_in_threadpool

from backend.app.auth.service import require_admin
from backend.app.brokers.upstox import BrokerError, ReadOnlyUpstox
from backend.app.market_data.option_chain import (
    ChainError,
    archive_chain,
    available_expiries,
    chain_status,
    read_chain,
    resolve_chain,
    validate_chain,
)
from backend.app.market_data.option_contracts import ChainRequest

router = APIRouter(prefix="/api/option-chain", dependencies=[Depends(require_admin)])


class ChainGate:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.next_attempt = 0.0


def get_chain_broker(request: Request) -> ReadOnlyUpstox:
    return ReadOnlyUpstox(request.app.state.settings)


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    return chain_status(request.app.state.engine)


@router.get("/expiries")
def expiries(
    request: Request, underlying_key: Annotated[str, Query(min_length=11, max_length=160)]
) -> dict[str, object]:
    try:
        return available_expiries(request.app.state.engine, underlying_key)
    except ChainError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/capture")
async def capture(
    payload: ChainRequest,
    request: Request,
    broker: Annotated[ReadOnlyUpstox, Depends(get_chain_broker)],
) -> dict[str, object]:
    gate = cast(ChainGate, request.app.state.chain_gate)
    async with gate.lock:
        remaining = gate.next_attempt - time.monotonic()
        if remaining > 0:
            raise HTTPException(
                429, "CHAIN_COOLDOWN", headers={"Retry-After": str(int(remaining) + 1)}
            )
        try:
            context = await run_in_threadpool(resolve_chain, request.app.state.engine, payload)
            gate.next_attempt = time.monotonic() + 30
            source = await broker.option_chain(payload)
            prepared = await run_in_threadpool(validate_chain, payload, source, context)
            snapshot = await run_in_threadpool(
                archive_chain, request.app.state.engine, payload, prepared, context
            )
            return {"snapshot": snapshot, "entries_enabled": False, "live_enabled": False}
        except BrokerError as error:
            if error.code == "RATE_LIMITED":
                gate.next_attempt = max(gate.next_attempt, time.monotonic() + error.retry_after)
            code = 429 if error.code == "RATE_LIMITED" else 503
            headers = {"Retry-After": str(error.retry_after)} if code == 429 else None
            raise HTTPException(code, error.code, headers=headers) from None
        except ChainError as error:
            raise HTTPException(422, str(error)) from None


@router.get("/snapshots/{identity}")
def snapshot(
    identity: Annotated[str, Path(pattern="^[0-9a-f]{64}$")],
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    after: Annotated[str | None, Query(max_length=160)] = None,
) -> dict[str, object]:
    result = read_chain(request.app.state.engine, identity, limit, after)
    if result is None:
        raise HTTPException(404, "CHAIN_SNAPSHOT_NOT_FOUND")
    return result
