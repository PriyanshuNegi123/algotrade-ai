import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.candles import get_history_broker
from backend.app.instruments.service import archive, prepare
from backend.app.market_data.history import (
    CandleError,
    archive_candles,
    history_status,
    read_batch,
    resolve_instrument,
    validate_history,
)
from backend.app.market_data.models import Candle, CandleImport
from tests.candle_fixtures import TOKEN, candle_payload, history_adapter, history_request
from tests.conftest import ORIGIN, PASSWORD
from tests.instrument_fixtures import metadata_download


def seed(client):
    archive(client.app.state.engine, prepare(metadata_download()))
    request = history_request()
    return request, resolve_instrument(client.app.state.engine, request)


def test_fixed_broker_history_path_and_no_retry():
    calls = []
    request = history_request()

    def handler(actual):
        calls.append(actual)
        assert actual.method == "GET"
        assert actual.url.host == "api.upstox.com"
        assert b"NSE_INDEX%7CSynthetic%20index/minutes/1/" in actual.url.raw_path
        assert actual.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200, content=candle_payload(request).body, headers={"Content-Type": "application/json"}
        )

    payload = asyncio.run(history_adapter(httpx.MockTransport(handler)).historical_candles(request))
    assert len(validate_history(request, payload).bars) == 3
    assert len(calls) == 1


def test_archive_dedup_and_bounded_utc_pagination(client):
    request, metadata = seed(client)
    prepared = validate_history(request, candle_payload(request))
    first = archive_candles(client.app.state.engine, request, prepared, metadata)
    second = archive_candles(client.app.state.engine, request, prepared, metadata)
    assert first["id"] == second["id"] and second["deduplicated"] is True
    assert first["retrieved_at"] == second["retrieved_at"]
    page = read_batch(client.app.state.engine, first["id"], 2, None)
    assert len(page["candles"]) == 2 and page["next_after"].tzinfo is not None
    remaining = read_batch(client.app.state.engine, first["id"], 2, page["next_after"])
    assert len(remaining["candles"]) == 1 and remaining["next_after"] is None
    assert first["signal_eligible"] is False and first["execution_eligible"] is False
    assert first["identity_binding"] == "REQUEST_PATH_ONLY"
    assert "canonical_payload" not in page


def test_unknown_metadata_and_expired_contract_rejected(client):
    with pytest.raises(CandleError, match="INSTRUMENT_NOT_IN_CATALOG"):
        resolve_instrument(client.app.state.engine, history_request())
    request, metadata = seed(client)
    with pytest.raises(CandleError, match="INSTRUMENT_IDENTITY_MISMATCH"):
        archive_candles(
            client.app.state.engine,
            request,
            validate_history(request, candle_payload()),
            {**metadata, "instrument_key": "NSE_INDEX|Other"},
        )


def test_candle_transaction_rollback(client):
    request, metadata = seed(client)
    engine = client.app.state.engine

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO candles "):
            raise SQLAlchemyError("simulated candle storage failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            archive_candles(engine, request, validate_history(request, candle_payload()), metadata)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as db:
        assert db.scalar(select(CandleImport)) is None
        assert db.scalar(select(Candle)) is None


def test_private_import_csrf_and_pagination_api(client):
    request, _ = seed(client)
    calls = []

    def handler(actual):
        calls.append(actual)
        return httpx.Response(
            200, content=candle_payload(request).body, headers={"Content-Type": "application/json"}
        )

    client.app.dependency_overrides[get_history_broker] = lambda: history_adapter(
        httpx.MockTransport(handler)
    )
    assert client.get("/api/candles/status").status_code == 401
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    body = request.model_dump(mode="json")
    assert client.post("/api/candles/import", json=body, headers=ORIGIN).status_code == 403
    headers = {**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    result = client.post("/api/candles/import", json=body, headers=headers)
    assert result.status_code == 200
    identity = result.json()["import"]["id"]
    assert client.get("/api/candles/status").json()["latest_import"]["row_count"] == 3
    page = client.get(f"/api/candles/batches/{identity}", params={"limit": 2}).json()
    assert len(page["candles"]) == 2 and page["next_after"]
    assert TOKEN not in result.text
    assert client.post("/api/candles/import", json=body, headers=headers).status_code == 429
    assert len(calls) == 1
    assert (
        client.get(
            f"/api/candles/batches/{identity}", params={"after": "2020-01-01T00:00:00"}
        ).status_code
        == 422
    )
    assert client.get("/api/candles/batches/" + "0" * 64).status_code == 404


def test_missing_credential_does_not_import_or_send_http(client):
    request, _ = seed(client)
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    result = client.post(
        "/api/candles/import",
        json=request.model_dump(mode="json"),
        headers={**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert result.status_code == 503 and result.json()["detail"] == "NOT_CONFIGURED"
    assert history_status(client.app.state.engine)["latest_import"] is None


def test_option_identity_is_preserved_and_expired_endpoint_not_assumed(client):
    from backend.app.instruments.models import Instrument

    seed(client)
    request = history_request(instrument_key="NSE_FO|synthetic-option")
    metadata = resolve_instrument(client.app.state.engine, request)
    result = archive_candles(
        client.app.state.engine,
        request,
        validate_history(request, candle_payload(request)),
        metadata,
    )
    assert result["instrument_type"] == "CE"
    assert result["historical_metadata_verified"] is False
    with Session(client.app.state.engine) as db:
        row = db.get(Instrument, (metadata["snapshot_id"], request.instrument_key))
        row.expiry = datetime.now(UTC) - timedelta(days=3)
        db.commit()
    with pytest.raises(CandleError, match="EXPIRED_CONTRACT_UNSUPPORTED"):
        resolve_instrument(client.app.state.engine, request)
