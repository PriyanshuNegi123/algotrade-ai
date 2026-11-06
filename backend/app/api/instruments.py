import threading
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.auth.service import require_admin
from backend.app.instruments.service import archive, catalog_status, lookup, prepare
from backend.app.instruments.source import InstrumentError, InstrumentSource

router = APIRouter(prefix="/api/instruments", dependencies=[Depends(require_admin)])


class ImportGate:
    """One writer and one manual attempt per five minutes in the supported single worker."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.next_attempt = 0.0


def get_source() -> InstrumentSource:
    return InstrumentSource()


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    return catalog_status(request.app.state.engine)


@router.post("/sync")
def sync(
    request: Request, source: Annotated[InstrumentSource, Depends(get_source)]
) -> dict[str, object]:
    gate: ImportGate = request.app.state.instrument_gate
    if not gate.lock.acquire(blocking=False):
        raise HTTPException(409, "IMPORT_IN_PROGRESS")
    try:
        remaining = gate.next_attempt - time.monotonic()
        if remaining > 0:
            raise HTTPException(
                429, "IMPORT_COOLDOWN", headers={"Retry-After": str(int(remaining) + 1)}
            )
        gate.next_attempt = time.monotonic() + 300
        try:
            prepared = prepare(source.download())
            return {
                "snapshot": archive(request.app.state.engine, prepared),
                "entries_enabled": False,
                "live_enabled": False,
            }
        except InstrumentError as error:
            raise HTTPException(503, str(error)) from None
    finally:
        gate.lock.release()


@router.get("/lookup")
def instrument(
    request: Request,
    instrument_key: Annotated[str, Query(min_length=3, max_length=160)],
    as_of: datetime | None = None,
) -> dict[str, object]:
    try:
        record = lookup(request.app.state.engine, instrument_key, as_of or datetime.now(UTC))
    except InstrumentError as error:
        raise HTTPException(422, str(error)) from None
    if record is None:
        raise HTTPException(404, "INSTRUMENT_NOT_FOUND_AS_OF")
    return record
