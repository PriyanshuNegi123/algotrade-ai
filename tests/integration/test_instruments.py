from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.api.instruments import get_source
from backend.app.instruments.models import Instrument, InstrumentSnapshot
from backend.app.instruments.service import archive, catalog_status, lookup, prepare
from backend.app.instruments.source import InstrumentError
from tests.conftest import ORIGIN, PASSWORD
from tests.instrument_fixtures import metadata_download, metadata_rows


def test_immutable_archive_dedup_and_asof_lookup(client):
    engine = client.app.state.engine
    before = datetime.now(UTC) - timedelta(seconds=1)
    prepared = prepare(metadata_download())
    first = archive(engine, prepared)
    second = archive(engine, prepared)
    assert first["id"] == second["id"]
    assert first["deduplicated"] is False and second["deduplicated"] is True
    assert first["retrieved_at"] == second["retrieved_at"]
    assert lookup(engine, "NSE_FO|synthetic-option", before) is None
    result = lookup(engine, "NSE_FO|synthetic-option", datetime.now(UTC))
    assert result["lot_size"] == 50 and result["tick_size_raw"] == "5.00000000"
    assert result["tick_size_unit"] == "BROKER_UNVERIFIED" and result["execution_eligible"] is False
    index = lookup(engine, "NSE_INDEX|Synthetic index", datetime.now(UTC))
    assert index["lot_size"] is None
    with Session(engine) as db:
        assert db.scalar(select(InstrumentSnapshot)).raw_gzip == prepared.download.body


def test_metadata_changes_preserve_prior_snapshot_and_removed_contracts_stay_removed(client):
    engine = client.app.state.engine
    first = archive(engine, prepare(metadata_download()))
    cutoff = datetime.now(UTC)
    changed = metadata_rows(lot_size=75, option_key="NSE_FO|replacement-option")
    second = archive(engine, prepare(metadata_download(changed, modified_at=datetime.now(UTC))))
    assert first["id"] != second["id"]
    assert lookup(engine, "NSE_FO|synthetic-option", cutoff)["lot_size"] == 50
    assert lookup(engine, "NSE_FO|synthetic-option", datetime.now(UTC)) is None
    assert lookup(engine, "NSE_FO|replacement-option", datetime.now(UTC))["lot_size"] == 75


@pytest.mark.parametrize(
    "changes",
    [
        {"lot_size": 0},
        {"lot_size": True},
        {"tick_size": -1},
        {"expiry": None},
        {"strike_price": 0},
        {"underlying_key": "NSE_INDEX|Missing"},
        {"expiry": int((datetime.now(UTC) - timedelta(days=3)).timestamp() * 1000)},
    ],
)
def test_invalid_contract_does_not_replace_current_snapshot(client, changes):
    engine = client.app.state.engine
    original = archive(engine, prepare(metadata_download()))
    rows = metadata_rows()
    rows[1].update(changes)
    with pytest.raises(InstrumentError):
        archive(engine, prepare(metadata_download(rows)))
    assert catalog_status(engine)["snapshot"]["id"] == original["id"]


def test_duplicate_key_and_stale_source_rejected(client):
    rows = metadata_rows()
    rows.append(rows[1].copy())
    with pytest.raises(InstrumentError, match="DUPLICATE_INSTRUMENT_KEY"):
        prepare(metadata_download(rows))
    with pytest.raises(InstrumentError, match="STALE_SOURCE"):
        prepare(metadata_download(modified_at=datetime.now(UTC) - timedelta(days=3)))
    assert catalog_status(client.app.state.engine)["snapshot"] is None


def test_database_failure_rolls_back_archive_and_entries(client):
    engine = client.app.state.engine

    def break_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO instruments "):
            raise SQLAlchemyError("simulated database interruption")

    event.listen(engine, "before_cursor_execute", break_insert)
    try:
        with pytest.raises(SQLAlchemyError):
            archive(engine, prepare(metadata_download()))
    finally:
        event.remove(engine, "before_cursor_execute", break_insert)
    with Session(engine) as db:
        assert (
            db.scalar(select(InstrumentSnapshot)) is None and db.scalar(select(Instrument)) is None
        )


def test_private_sync_origin_csrf_cooldown_and_lookup(client):
    calls = []

    class SyntheticSource:
        def download(self):
            calls.append(True)
            return metadata_download()

    client.app.dependency_overrides[get_source] = lambda: SyntheticSource()
    assert client.get("/api/instruments/status").status_code == 401
    assert client.post("/api/instruments/sync").status_code == 401
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert client.get("/api/instruments/status").json()["state"] == "NOT_IMPORTED"
    assert client.post("/api/instruments/sync", headers=ORIGIN).status_code == 403
    headers = {**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    result = client.post("/api/instruments/sync", headers=headers)
    assert result.status_code == 200 and result.json()["snapshot"]["selected_records"] == 2
    assert client.post("/api/instruments/sync", headers=headers).status_code == 429
    assert len(calls) == 1
    lookup_result = client.get(
        "/api/instruments/lookup", params={"instrument_key": "NSE_FO|synthetic-option"}
    )
    assert lookup_result.status_code == 200 and "raw_gzip" not in lookup_result.text
    assert (
        client.get("/api/instruments/lookup", params={"instrument_key": "' OR 1=1 --"}).status_code
        == 404
    )
    assert (
        client.get(
            "/api/instruments/lookup",
            params={"instrument_key": "NSE_FO|synthetic-option", "as_of": "2025-01-01T00:00:00"},
        ).status_code
        == 422
    )


def test_missing_catalog_table_and_old_revision_not_ready(client):
    config = Config("alembic.ini")
    command.downgrade(config, "0001_sessions")
    assert client.get("/health/ready").status_code == 503
    command.upgrade(config, "head")
    assert client.get("/health/ready").status_code == 200
    with client.app.state.engine.begin() as db:
        db.execute(text("DROP TABLE instruments"))
    assert client.get("/health/ready").status_code == 503


def test_asof_offset_and_stale_catalog_are_explicit(client):
    from zoneinfo import ZoneInfo

    engine = client.app.state.engine
    summary = archive(engine, prepare(metadata_download()))
    before = summary["imported_at"] - timedelta(seconds=1)
    assert (
        lookup(engine, "NSE_FO|synthetic-option", before.astimezone(ZoneInfo("Asia/Kolkata")))
        is None
    )
    current = lookup(engine, "NSE_FO|synthetic-option", datetime.now(ZoneInfo("Asia/Kolkata")))
    assert current["as_of"].utcoffset() == timedelta(0)
    with Session(engine) as db:
        snapshot = db.get(InstrumentSnapshot, summary["id"])
        snapshot.source_modified_at = datetime.now(UTC) - timedelta(days=3)
        db.commit()
    assert catalog_status(engine)["state"] == "STALE_METADATA"


def test_import_in_progress_does_not_start_a_second_download(client):
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    gate = client.app.state.instrument_gate
    gate.lock.acquire()
    try:
        result = client.post(
            "/api/instruments/sync", headers={**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
        )
    finally:
        gate.lock.release()
    assert result.status_code == 409
