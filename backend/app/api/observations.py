from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from backend.app.auth.service import require_admin
from backend.app.market_data.calendar import CalendarError, calendar_days
from backend.app.market_data.coverage import CoverageError, CoverageRequest, coverage_report
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.observations import list_sessions, read_session
from backend.app.market_data.preflight import capture_preflight
from backend.app.market_data.supervision_store import CapturePolicy, list_captures, read_capture

router = APIRouter(prefix="/api/observations", dependencies=[Depends(require_admin)])


@router.get("/sessions")
def sessions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    after: Annotated[str | None, Query(pattern="^[0-9a-f]{32}$")] = None,
) -> dict[str, object]:
    return list_sessions(request.app.state.engine, limit, after)


@router.get("/sessions/{identity}")
def session(
    identity: Annotated[str, Path(pattern="^[0-9a-f]{32}$")],
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    after: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    result = read_session(request.app.state.engine, identity, limit, after)
    if result is None:
        raise HTTPException(404, "OBSERVATION_NOT_FOUND")
    return result


@router.get("/calendar")
def calendar(
    from_date: date,
    to_date: date,
) -> dict[str, object]:
    try:
        return calendar_days(from_date, to_date)
    except CalendarError as error:
        raise HTTPException(
            503 if str(error) == "CALENDAR_EVIDENCE_INVALID" else 422, str(error)
        ) from None


@router.get("/coverage")
def coverage(
    request: Request,
    from_date: date,
    to_date: date,
    instrument_key: Annotated[list[str], Query(min_length=1, max_length=20)],
    source: Literal["UPSTOX_V3", "SYNTHETIC"] = "UPSTOX_V3",
) -> dict[str, object]:
    try:
        payload = CoverageRequest(
            from_date=from_date,
            to_date=to_date,
            instrument_keys=tuple(instrument_key),
            source=source,
        )
        return coverage_report(request.app.state.engine, payload)
    except ValidationError:
        raise HTTPException(422, "INVALID_COVERAGE_REQUEST") from None
    except CalendarError:
        raise HTTPException(503, "CALENDAR_EVIDENCE_INVALID") from None
    except CoverageError as error:
        raise HTTPException(
            503 if str(error) == "COVERAGE_ARCHIVE_INVALID" else 422, str(error)
        ) from None
    except SQLAlchemyError:
        raise HTTPException(503, "COVERAGE_DATABASE_UNAVAILABLE") from None


@router.get("/captures/{identity}")
def capture(
    identity: Annotated[str, Path(pattern="^[0-9a-f]{32}$")], request: Request
) -> dict[str, object]:
    result = read_capture(request.app.state.engine, identity)
    if result is None:
        raise HTTPException(404, "CAPTURE_NOT_FOUND")
    return result


@router.get("/captures")
def captures(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    after: Annotated[str | None, Query(pattern="^[0-9a-f]{32}$")] = None,
) -> dict[str, object]:
    return list_captures(request.app.state.engine, limit, after)


@router.get("/preflight")
def preflight(
    request: Request,
    instrument_key: Annotated[list[str], Query(min_length=1, max_length=100)],
    total_seconds: int = 600,
    session_seconds: int = 300,
    max_sessions: int = 3,
    max_payload_bytes: int = 8 * 1024 * 1024,
    max_events: int = 20_000,
) -> dict[str, object]:
    try:
        payload = FeedRequest(instrument_keys=tuple(instrument_key))
        policy = CapturePolicy(
            total_seconds=total_seconds,
            session_seconds=session_seconds,
            max_sessions=max_sessions,
            max_payload_bytes=max_payload_bytes,
            max_events=max_events,
        )
    except ValidationError:
        raise HTTPException(422, "INVALID_PREFLIGHT_REQUEST") from None
    return capture_preflight(request.app.state.engine, request.app.state.settings, payload, policy)
