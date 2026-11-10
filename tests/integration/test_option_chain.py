import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.option_chain import get_chain_broker
from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.service import archive, prepare
from backend.app.market_data.option_chain import (
    ChainError,
    archive_chain,
    available_expiries,
    chain_status,
    read_chain,
    resolve_chain,
    validate_chain,
)
from backend.app.market_data.option_contracts import ChainRequest, chain_url
from backend.app.market_data.option_models import ChainLeg, ChainSnapshot
from tests.chain_fixtures import (
    TOKEN,
    chain_adapter,
    chain_metadata,
    chain_payload,
    chain_request,
    chain_rows,
)
from tests.conftest import ORIGIN, PASSWORD


def seed(engine):
    archive(engine, prepare(chain_metadata()))
    request = chain_request()
    return request, resolve_chain(engine, request)


@pytest.mark.parametrize(
    "changes",
    [
        {"underlying_key": "NSE_FO|synthetic-option"},
        {"underlying_key": "https://evil.example"},
        {"underlying_key": "NSE_INDEX|../private"},
        {"expiry_date": "current_week"},
        {"expiry_date": "2020-01-01"},
        {"enable_live": True},
    ],
)
def test_chain_request_fails_closed(changes):
    with pytest.raises(ValidationError):
        ChainRequest(**{**chain_request().model_dump(), **changes})


def test_fixed_encoded_chain_get_and_credential(client):
    request, _ = seed(client.app.state.engine)
    calls = []

    def handler(actual):
        calls.append(actual)
        assert actual.method == "GET" and actual.url.host == "api.upstox.com"
        assert actual.url.path == "/v2/option/chain"
        assert actual.url.params["instrument_key"] == request.underlying_key
        assert actual.url.params["expiry_date"] == request.expiry_date.isoformat()
        assert actual.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200, content=chain_payload(request).body, headers={"Content-Type": "application/json"}
        )

    payload = asyncio.run(chain_adapter(httpx.MockTransport(handler)).option_chain(request))
    assert payload.source_url == chain_url(request)
    assert len(calls) == 1


def test_identity_exact_greeks_and_unknown_freshness(client):
    request, context = seed(client.app.state.engine)
    prepared = validate_chain(request, chain_payload(request), context)
    result = archive_chain(client.app.state.engine, request, prepared, context)
    assert result["leg_count"] == 2 and result["freshness"] == "UNKNOWN"
    assert result["exchange_timestamp"] is None and result["execution_eligible"] is False
    page = read_chain(client.app.state.engine, result["id"], 1, None)
    assert len(page["legs"]) == 1 and page["next_after"]
    remaining = read_chain(client.app.state.engine, result["id"], 1, page["next_after"])
    assert len(remaining["legs"]) == 1 and remaining["next_after"] is None
    assert page["legs"][0]["lot_size"] == 50
    assert Decimal(page["legs"][0]["greeks"]["gamma"]) == Decimal("0.0000000001")
    assert page["legs"][0]["spread"] == "1.00000000"
    assert result["flagged_legs"] == 0


@pytest.mark.parametrize("iv", [0.127716064453125, 26.31, 262.31])
def test_unit_context_preserves_raw_values_and_canonical_bytes(client, iv):
    engine = client.app.state.engine
    request, context = seed(engine)
    rows = chain_rows(request)
    rows[0]["call_options"]["option_greeks"].update(iv=iv, theta=-2.5, vega=1.5, pop=45)
    prepared = validate_chain(request, chain_payload(request, rows), context)
    result = archive_chain(engine, request, prepared, context)
    statements = []

    def observe(_connection, _cursor, statement, *_):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        page = read_chain(engine, result["id"], 200, None)
        status = chain_status(engine)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    unit_context = page["snapshot"]["unit_context"]
    assert unit_context == status["latest_snapshot"]["unit_context"] == result["unit_context"]
    assert unit_context["status"] == "UNRESOLVED" and not unit_context["units_verified"]
    assert not unit_context["normalization_applied"]
    assert not unit_context["contract_multiplier_applied"]
    assert not unit_context["execution_eligible"]
    assert all(value == "BROKER_UNVERIFIED" for value in unit_context["greek_units"].values())
    assert unit_context["scope"] == "CURRENT_READ_CONTEXT_NOT_CAPTURE_TIME_CERTIFICATION"
    greeks = page["legs"][0]["greeks"]
    assert Decimal(greeks["iv"]) == Decimal(str(iv))
    assert greeks["theta"] == "-2.5" and greeks["vega"] == "1.5" and greeks["pop"] == "45"
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert not any("canonical_payload" in statement.lower() for statement in statements)
    with Session(engine) as db:
        archived = db.get(ChainSnapshot, result["id"])
        assert archived.canonical_payload == prepared.canonical
        assert hashlib.sha256(archived.canonical_payload).hexdigest() == result["canonical_sha256"]
        assert b"unit_context" not in archived.canonical_payload


@pytest.mark.parametrize("kind", ["missing-greeks", "empty"])
def test_unit_context_never_invents_missing_greeks(client, kind):
    engine = client.app.state.engine
    request, context = seed(engine)
    rows = chain_rows(request)
    if kind == "empty":
        rows = []
    else:
        rows[0]["call_options"].pop("option_greeks")
    prepared = validate_chain(request, chain_payload(request, rows), context)
    archived = archive_chain(engine, request, prepared, context)
    page = read_chain(engine, archived["id"], 200, None)
    assert page["snapshot"]["unit_context"]["status"] == "UNRESOLVED"
    if rows:
        assert all(value is None for value in page["legs"][0]["greeks"].values())
    else:
        assert page["legs"] == [] and page["snapshot"]["state"] == "EMPTY"


def test_response_context_cannot_mutate_later_reads(client):
    engine = client.app.state.engine
    request, context = seed(engine)
    archived = archive_chain(
        engine, request, validate_chain(request, chain_payload(request), context), context
    )
    page = read_chain(engine, archived["id"], 200, None)
    page["snapshot"]["unit_context"]["greek_units"]["iv"] = "synthetic-unapproved-unit"
    assert (
        read_chain(engine, archived["id"], 200, None)["snapshot"]["unit_context"]["greek_units"][
            "iv"
        ]
        == "BROKER_UNVERIFIED"
    )


def test_unit_context_postgres_preserves_archival_bytes(postgres_config):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        request, context = seed(engine)
        prepared = validate_chain(request, chain_payload(request), context)
        result = archive_chain(engine, request, prepared, context)
        page = read_chain(engine, result["id"], 200, None)
        assert page["snapshot"]["unit_context"]["normalization_applied"] is False
        assert page["legs"][0]["greeks"]["iv"] == "20"
        with Session(engine) as db:
            assert db.get(ChainSnapshot, result["id"]).canonical_payload == prepared.canonical


def test_missing_and_zero_fields_are_not_invented_or_selected(client):
    request, context = seed(client.app.state.engine)
    rows = chain_rows(request)
    rows[0]["call_options"]["market_data"] = {"bid_price": 10, "ask_price": 0, "volume": 0}
    rows[0]["put_options"].pop("option_greeks")
    prepared = validate_chain(request, chain_payload(request, rows), context)
    result = archive_chain(client.app.state.engine, request, prepared, context)
    page = read_chain(client.app.state.engine, result["id"], 200, None)
    assert "ZERO_QUOTE" in page["legs"][0]["quality_flags"]
    assert page["legs"][0]["oi"] is None
    assert page["legs"][0]["spread"] is None
    assert "MISSING_GREEKS" in page["legs"][1]["quality_flags"]
    assert all(not leg["signal_eligible"] for leg in page["legs"])


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda r: r[0].update(underlying_key="NSE_INDEX|Other"), "CHAIN_IDENTITY_MISMATCH"),
        (lambda r: r[0].update(expiry="2020-01-01"), "CHAIN_IDENTITY_MISMATCH"),
        (lambda r: r[0].update(strike_price=101), "CATALOG_LEG_MISMATCH"),
        (
            lambda r: r[0]["call_options"].update(instrument_key="NSE_FO|synthetic-put"),
            "CATALOG_LEG_MISMATCH",
        ),
        (lambda r: r.append(r[0].copy()), "DUPLICATE_CHAIN_STRIKE"),
        (lambda r: r[0].pop("put_options"), "MISSING_CHAIN_LEG"),
        (lambda r: r[0]["call_options"]["market_data"].update(bid_price=12), "CROSSED_MARKET"),
        (
            lambda r: r[0]["call_options"]["market_data"].update(ask_price=-1),
            "INVALID_MARKET_NUMBER",
        ),
        (lambda r: r[0]["call_options"]["market_data"].update(oi=True), "INVALID_QUANTITY"),
        (
            lambda r: r[0]["call_options"]["option_greeks"].update(delta=-0.5),
            "INVALID_OPTION_DELTA",
        ),
        (lambda r: r[0]["put_options"]["option_greeks"].update(delta=0.5), "INVALID_OPTION_DELTA"),
        (lambda r: r[0]["call_options"]["option_greeks"].update(iv=-1), "INVALID_OPTION_GREEKS"),
    ],
)
def test_bad_chain_preserves_prior_snapshot(client, mutation, code):
    engine = client.app.state.engine
    request, context = seed(engine)
    first = archive_chain(
        engine, request, validate_chain(request, chain_payload(), context), context
    )
    rows = chain_rows(request)
    mutation(rows)
    with pytest.raises(ChainError, match=code):
        validate_chain(request, chain_payload(request, rows), context)
    assert chain_status(engine)["latest_snapshot"]["id"] == first["id"]


def test_receipt_versions_idempotence_and_sanitized_archive(client):
    engine = client.app.state.engine
    request, context = seed(engine)
    rows = chain_rows(request)
    rows[0]["ignored_secret"] = TOKEN
    rows[0]["call_options"]["option_greeks"]["ignored_secret"] = TOKEN
    payload = chain_payload(request, rows)
    prepared = validate_chain(request, payload, context)
    first = archive_chain(engine, request, prepared, context)
    duplicate = archive_chain(engine, request, prepared, context)
    assert duplicate["deduplicated"] is True
    assert duplicate["retrieved_at"] == first["retrieved_at"]
    later = replace(payload, retrieved_at=payload.retrieved_at + timedelta(microseconds=1))
    second = archive_chain(engine, request, validate_chain(request, later, context), context)
    assert second["id"] != first["id"]
    with Session(engine) as db:
        assert TOKEN.encode() not in db.get(ChainSnapshot, first["id"]).canonical_payload


def test_catalog_expiry_staleness_and_pair_lots_fail_before_network(client):
    engine = client.app.state.engine
    with pytest.raises(ChainError, match="UNDERLYING_NOT_IN_CATALOG"):
        resolve_chain(engine, chain_request())
    request, context = seed(engine)
    assert available_expiries(engine, request.underlying_key)["expiry_dates"] == [
        request.expiry_date
    ]
    with pytest.raises(ChainError, match="EXPIRY_NOT_IN_CATALOG"):
        resolve_chain(engine, chain_request(expiry_date=request.expiry_date + timedelta(days=1)))
    with Session(engine) as db:
        put = db.get(Instrument, (context.snapshot_id, "NSE_FO|synthetic-put"))
        put.lot_size = 75
        db.commit()
    with pytest.raises(ChainError, match="INCONSISTENT_PAIR_LOT"):
        resolve_chain(engine, request)
    with Session(engine) as db:
        snapshot = db.get(InstrumentSnapshot, context.snapshot_id)
        snapshot.source_modified_at = datetime.now(UTC) - timedelta(days=3)
        db.commit()
    with pytest.raises(ChainError, match="STALE_INSTRUMENT_CATALOG"):
        resolve_chain(engine, request)


def test_chain_storage_rollback(client):
    engine = client.app.state.engine
    request, context = seed(engine)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO option_chain_legs "):
            raise SQLAlchemyError("simulated chain write interruption")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SQLAlchemyError):
            archive_chain(
                engine, request, validate_chain(request, chain_payload(), context), context
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as db:
        assert db.scalar(select(ChainSnapshot)) is None
        assert db.scalar(select(ChainLeg)) is None


def test_empty_response_and_invalid_source_bounds(client, monkeypatch):
    from backend.app.market_data import option_chain

    request, context = seed(client.app.state.engine)
    result = archive_chain(
        client.app.state.engine,
        request,
        validate_chain(request, chain_payload(rows=[]), context),
        context,
    )
    assert result["state"] == "EMPTY" and result["leg_count"] == 0
    with pytest.raises(ChainError, match="SOURCE_IDENTITY_MISMATCH"):
        validate_chain(
            request, replace(chain_payload(), source_url="https://evil.example"), context
        )
    monkeypatch.setattr(option_chain, "MAX_STRIKES", 0)
    with pytest.raises(ChainError, match="STRIKE_LIMIT"):
        validate_chain(request, chain_payload(), context)


def test_private_capture_csrf_cooldown_and_pagination(client):
    request, _ = seed(client.app.state.engine)
    calls = []

    def handler(actual):
        calls.append(actual)
        return httpx.Response(
            200, content=chain_payload(request).body, headers={"Content-Type": "application/json"}
        )

    client.app.dependency_overrides[get_chain_broker] = lambda: chain_adapter(
        httpx.MockTransport(handler)
    )
    assert client.get("/api/option-chain/status").status_code == 401
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    body = request.model_dump(mode="json")
    assert client.post("/api/option-chain/capture", json=body, headers=ORIGIN).status_code == 403
    assert client.get(
        "/api/option-chain/expiries", params={"underlying_key": request.underlying_key}
    ).json()["expiry_dates"] == [request.expiry_date.isoformat()]
    headers = {**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    result = client.post("/api/option-chain/capture", json=body, headers=headers)
    assert result.status_code == 200 and result.json()["snapshot"]["freshness"] == "UNKNOWN"
    assert result.json()["snapshot"]["unit_context"]["status"] == "UNRESOLVED"
    identity = result.json()["snapshot"]["id"]
    page = client.get(f"/api/option-chain/snapshots/{identity}", params={"limit": 1}).json()
    assert len(page["legs"]) == 1 and page["next_after"]
    assert client.post("/api/option-chain/capture", json=body, headers=headers).status_code == 429
    assert len(calls) == 1 and TOKEN not in result.text
    assert client.get("/api/option-chain/snapshots/" + "0" * 64).status_code == 404


def test_missing_token_never_fetches_or_records(client):
    request, _ = seed(client.app.state.engine)
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    response = client.post(
        "/api/option-chain/capture",
        json=request.model_dump(mode="json"),
        headers={**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    assert response.status_code == 503 and response.json()["detail"] == "NOT_CONFIGURED"
    assert chain_status(client.app.state.engine)["latest_snapshot"] is None
