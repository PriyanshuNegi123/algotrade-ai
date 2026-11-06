from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.auth.service import require_admin
from backend.app.brokers.upstox import BrokerError, BrokerMonitor, BrokerSnapshot

router = APIRouter(prefix="/api/broker", dependencies=[Depends(require_admin)])


def get_monitor(request: Request) -> BrokerMonitor:
    return cast(BrokerMonitor, request.app.state.broker_monitor)


@router.get("/status")
def status(monitor: Annotated[BrokerMonitor, Depends(get_monitor)]) -> BrokerSnapshot:
    return monitor.snapshot()


@router.post("/check")
async def check(monitor: Annotated[BrokerMonitor, Depends(get_monitor)]) -> BrokerSnapshot:
    try:
        return await monitor.check()
    except BrokerError as error:
        code = 429 if error.code == "RATE_LIMITED" else 503
        headers = {"Retry-After": str(error.retry_after)} if code == 429 else None
        raise HTTPException(code, error.code, headers=headers) from None
