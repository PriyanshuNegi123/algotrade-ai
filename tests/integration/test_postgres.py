"""Opt-in real PostgreSQL checks isolated in a fresh schema per test."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.app.auth.service import digest
from backend.app.database import AdminSession
from backend.app.main import create_app
from tests.conftest import ORIGIN, PASSWORD


def sign_in(client):
    response = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_postgres_initial_observation_report(postgres_config, coverage_clock):
    from backend.app.market_data.initial_report import initial_observation_report
    from tests.integration.test_coverage import recorded, report_request

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        recorded(engine)
        genuine = initial_observation_report(engine, report_request("UPSTOX_V3"))
        synthetic = initial_observation_report(engine, report_request())
        assert genuine["session_ids"] == []
        assert synthetic["recorded_session_count"] == 1
        assert synthetic["counts"]["events"] == 4
        assert genuine["qualifying_observation_days"] == 0
        assert synthetic["assessment"] == "NOT_CERTIFIED"
        assert not synthetic["live_enabled"]
        assert not genuine["window_progress"]["review_complete"]
        assert not synthetic["window_progress"]["phase2_complete"]
        assert "SYNTHETIC_SOURCE" in synthetic["window_progress"]["review_blockers"]
        assert "SYNTHETIC_SOURCE" not in genuine["window_progress"]["review_blockers"]


def test_postgres_migration_auth_and_restart(postgres_config):
    with TestClient(create_app(postgres_config)) as first:
        assert first.get("/health/ready").status_code == 200
        sign_in(first)
        token = first.cookies.get("admin_session")
    with TestClient(create_app(postgres_config)) as second:
        second.cookies.set("admin_session", token)
        state = second.get("/api/overview").json()
        assert state["live_enabled"] is False
        assert state["entries_enabled"] is False
        assert state["balance"] is None


def test_postgres_timezone_and_expiry(postgres_config):
    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        with Session(client.app.state.engine) as db:
            session = db.get(AdminSession, digest(client.cookies.get("admin_session")))
            assert session.expires_at.tzinfo is not None
            remaining = session.expires_at - datetime.now(UTC)
            assert timedelta(minutes=14) < remaining <= timedelta(minutes=15)
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert client.get("/api/overview").status_code == 401
        sign_in(client)
        with Session(client.app.state.engine) as db:
            # Successful reauthentication purges the expired session.
            assert db.execute(text("SELECT count(*) FROM admin_sessions")).scalar() == 1


def test_postgres_csrf_logout_revokes_persistent_session(postgres_config):
    with TestClient(create_app(postgres_config)) as client:
        csrf = sign_in(client)
        token = client.cookies.get("admin_session")
        assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 403
        assert client.get("/api/overview").status_code == 200
        assert (
            client.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": csrf}).status_code
            == 204
        )
    with TestClient(create_app(postgres_config)) as restarted:
        restarted.cookies.set("admin_session", token)
        assert restarted.get("/api/overview").status_code == 401


def test_postgres_migration_downgrade_upgrade(postgres_config):
    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        token = client.cookies.get("admin_session")
        command.downgrade(Config("alembic.ini"), "base")
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.get("/api/overview").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        client.cookies.set("admin_session", token)
        assert client.get("/api/overview").status_code == 401


def test_postgres_instrument_archive_roundtrip(postgres_config):
    from backend.app.instruments.service import archive, lookup, prepare
    from tests.instrument_fixtures import metadata_download

    with TestClient(create_app(postgres_config)) as client:
        first = archive(client.app.state.engine, prepare(metadata_download()))
        assert first["selected_records"] == 2
        record = lookup(client.app.state.engine, "NSE_FO|synthetic-option", datetime.now(UTC))
        assert record["lot_size"] == 50
        assert record["tick_size_raw"] == "5.00000000"
        assert record["expiry"].tzinfo is not None
        snapshot_id = first["id"]
    with TestClient(create_app(postgres_config)) as restarted:
        sign_in(restarted)
        result = restarted.get("/api/instruments/status")
        assert result.status_code == 200
        assert result.json()["snapshot"]["id"] == snapshot_id
        assert "raw_gzip" not in result.text


def test_postgres_instrument_atomic_rollback(postgres_config):
    from sqlalchemy import event, select
    from sqlalchemy.exc import SQLAlchemyError

    from backend.app.instruments.models import InstrumentSnapshot
    from backend.app.instruments.service import archive, prepare
    from tests.instrument_fixtures import metadata_download

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine

        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO instruments "):
                raise SQLAlchemyError("simulated PostgreSQL write failure")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(SQLAlchemyError):
                archive(engine, prepare(metadata_download()))
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        with Session(engine) as db:
            assert db.scalar(select(InstrumentSnapshot)) is None


def test_postgres_upgrade_preserves_sessions_and_requires_new_schema(postgres_config):
    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        command.downgrade(Config("alembic.ini"), "0001_sessions")
        assert client.get("/api/overview").status_code == 200
        assert client.get("/health/ready").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        assert client.get("/api/overview").status_code == 200


def test_postgres_candle_archive_and_restart(postgres_config):
    from backend.app.instruments.service import archive, prepare
    from backend.app.market_data.history import (
        archive_candles,
        read_batch,
        resolve_instrument,
        validate_history,
    )
    from tests.candle_fixtures import candle_payload, history_request
    from tests.instrument_fixtures import metadata_download

    request = history_request()
    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        archive(engine, prepare(metadata_download()))
        result = archive_candles(
            engine,
            request,
            validate_history(request, candle_payload()),
            resolve_instrument(engine, request),
        )
        page = read_batch(engine, result["id"], 2, None)
        assert page["candles"][0]["close"] == "101.25000000"
        assert page["candles"][0]["opened_at"].tzinfo is not None
        identity = result["id"]
    with TestClient(create_app(postgres_config)) as restarted:
        sign_in(restarted)
        result = restarted.get("/api/candles/status")
        assert result.json()["latest_import"]["id"] == identity
        assert result.json()["latest_import"]["signal_eligible"] is False


def test_postgres_candle_transaction_rollback(postgres_config):
    from sqlalchemy import event, select
    from sqlalchemy.exc import SQLAlchemyError

    from backend.app.instruments.service import archive, prepare
    from backend.app.market_data.history import (
        archive_candles,
        resolve_instrument,
        validate_history,
    )
    from backend.app.market_data.models import CandleImport
    from tests.candle_fixtures import candle_payload, history_request
    from tests.instrument_fixtures import metadata_download

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        archive(engine, prepare(metadata_download()))
        request = history_request()
        metadata = resolve_instrument(engine, request)

        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO candles "):
                raise SQLAlchemyError("simulated PostgreSQL candle write failure")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(SQLAlchemyError):
                archive_candles(
                    engine, request, validate_history(request, candle_payload()), metadata
                )
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        with Session(engine) as db:
            assert db.scalar(select(CandleImport)) is None


def test_postgres_history_schema_upgrade_preserves_catalog(postgres_config):
    from backend.app.instruments.service import archive, catalog_status, prepare
    from tests.instrument_fixtures import metadata_download

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        first = archive(client.app.state.engine, prepare(metadata_download()))
        command.downgrade(Config("alembic.ini"), "0002_instruments")
        assert client.get("/health/ready").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        assert catalog_status(client.app.state.engine)["snapshot"]["id"] == first["id"]
        assert client.get("/api/overview").status_code == 200


def test_postgres_option_chain_durability(postgres_config):
    from decimal import Decimal

    from backend.app.instruments.service import archive, prepare
    from backend.app.market_data.option_chain import (
        archive_chain,
        read_chain,
        resolve_chain,
        validate_chain,
    )
    from tests.chain_fixtures import chain_metadata, chain_payload, chain_request

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        archive(engine, prepare(chain_metadata()))
        request = chain_request()
        context = resolve_chain(engine, request)
        result = archive_chain(
            engine, request, validate_chain(request, chain_payload(), context), context
        )
        page = read_chain(engine, result["id"], 1, None)
        assert Decimal(page["legs"][0]["greeks"]["gamma"]) == Decimal("1e-10")
        assert page["legs"][0]["spread"] == "1.00000000"
        identity = result["id"]
    with TestClient(create_app(postgres_config)) as restarted:
        sign_in(restarted)
        result = restarted.get("/api/option-chain/status")
        assert result.json()["latest_snapshot"]["id"] == identity
        assert result.json()["latest_snapshot"]["freshness"] == "UNKNOWN"


def test_postgres_chain_atomic_rollback(postgres_config):
    from sqlalchemy import event, select
    from sqlalchemy.exc import SQLAlchemyError

    from backend.app.instruments.service import archive, prepare
    from backend.app.market_data.option_chain import archive_chain, resolve_chain, validate_chain
    from backend.app.market_data.option_models import ChainSnapshot
    from tests.chain_fixtures import chain_metadata, chain_payload, chain_request

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        archive(engine, prepare(chain_metadata()))
        request = chain_request()
        context = resolve_chain(engine, request)

        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO option_chain_legs "):
                raise SQLAlchemyError("simulated PostgreSQL chain interruption")

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


def test_postgres_chain_migration_preserves_catalog_and_sessions(postgres_config):
    from backend.app.instruments.service import archive, catalog_status, prepare
    from tests.chain_fixtures import chain_metadata

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        snapshot = archive(client.app.state.engine, prepare(chain_metadata()))
        command.downgrade(Config("alembic.ini"), "0003_candles")
        assert client.get("/health/ready").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        assert catalog_status(client.app.state.engine)["snapshot"]["id"] == snapshot["id"]
        assert client.get("/api/overview").status_code == 200


def test_postgres_observation_restart_and_lineage(postgres_config):
    from backend.app.market_data.observations import append_event, finish_session, read_session
    from tests.integration.test_observations import sample_events, seed

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        token = client.cookies.get("admin_session")
        engine = client.app.state.engine
        identity, plan, now, _ = seed(engine)
        for item in sample_events(plan, now):
            append_event(engine, identity, item)
        finish_session(engine, identity, "FRAME_LIMIT", 2200)
    with TestClient(create_app(postgres_config)) as restarted:
        restarted.cookies.set("admin_session", token)
        response = restarted.get(f"/api/observations/sessions/{identity}")
        assert response.status_code == 200
        result = read_session(restarted.app.state.engine, identity, 50, 0)
        assert result["session"]["observed_interval_ms"] == 1000
        assert result["session"]["created_at"].tzinfo is not None
        assert result["session"]["ended_at"].tzinfo is not None
        assert result["attempts"][0]["catalog_snapshot_id"] == plan.catalog_snapshot_id
        assert result["events"][-1]["event"]["observations"][0]["tick"]["last_price"] == "102.0"
        assert result["session"]["qualifying_observation_days"] == 0


def test_postgres_observation_concurrent_receipt_is_idempotent(postgres_config):
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.market_data.observations import append_event, read_session
    from tests.integration.test_observations import sample_events, seed

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        identity, plan, now, _ = seed(engine)
        item = sample_events(plan, now)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(append_event, engine, identity, item) for _ in range(2)]
            assert [future.result(timeout=5) for future in futures] == [2, 2]
        assert read_session(engine, identity, 50, 0)["session"]["event_count"] == 2


def test_postgres_observation_rollback_and_migration(postgres_config):
    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    from backend.app.market_data.observations import append_event, read_session
    from tests.integration.test_observations import sample_events, seed

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        engine = client.app.state.engine
        identity, plan, now, _ = seed(engine)
        before = read_session(engine, identity, 50, 0)

        def fail(connection, cursor, statement, parameters, context, many):
            if statement.startswith("INSERT INTO observation_events"):
                raise SQLAlchemyError("synthetic rollback")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(SQLAlchemyError):
                append_event(engine, identity, sample_events(plan, now)[0])
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        assert read_session(engine, identity, 50, 0) == before
        command.downgrade(Config("alembic.ini"), "0004_option_chain")
        assert client.get("/health/ready").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        assert (
            client.get("/api/instruments/status").json()["snapshot"]["id"]
            == plan.catalog_snapshot_id
        )
        assert client.get(f"/api/observations/sessions/{identity}").status_code == 404


def test_postgres_coverage_readonly_consistent_and_restart(postgres_config, coverage_clock):
    from backend.app.market_data.coverage import coverage_report
    from backend.app.market_data.observations import read_session
    from tests.integration.test_coverage import fixture_calendar, recorded, report_request

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        token = client.cookies.get("admin_session")
        engine = client.app.state.engine
        identity, _ = recorded(engine)
        before = read_session(engine, identity, 50, 0)
        result = coverage_report(engine, report_request(), policy=fixture_calendar())
        assert result["days"][0]["keys"][0]["sampled_interval_ms"] == 1000
        assert result["counts"]["events"] == 4
        assert read_session(engine, identity, 50, 0) == before
    with TestClient(create_app(postgres_config)) as restarted:
        restarted.cookies.set("admin_session", token)
        result = coverage_report(
            restarted.app.state.engine, report_request(), policy=fixture_calendar()
        )
        assert result["days"][0]["keys"][0]["sampled_interval_ms"] == 1000
        assert result["source"] == "SYNTHETIC" and result["qualifying_observation_days"] == 0


def test_postgres_coverage_corrupt_archive_fails_closed(postgres_config, coverage_clock):
    from sqlalchemy import update

    from backend.app.market_data.coverage import CoverageError, coverage_report
    from backend.app.market_data.observation_models import ObservationEvent
    from tests.integration.test_coverage import fixture_calendar, recorded, report_request

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        identity, _ = recorded(engine)
        with engine.begin() as connection:
            connection.execute(
                update(ObservationEvent)
                .where(ObservationEvent.session_id == identity, ObservationEvent.sequence == 1)
                .values(payload_sha256="0" * 64)
            )
        with pytest.raises(CoverageError, match="ARCHIVE_INVALID"):
            coverage_report(engine, report_request(), policy=fixture_calendar())


def test_postgres_capture_quota_concurrency_and_rollback(postgres_config):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime

    from sqlalchemy import event
    from sqlalchemy.exc import SQLAlchemyError

    from backend.app.instruments.service import archive, prepare
    from backend.app.market_data.feed import FeedRequest, resolve_feed
    from backend.app.market_data.feed_lifecycle import FeedEvent, LifecyclePolicy
    from backend.app.market_data.observations import append_event, read_session, start_session
    from backend.app.market_data.supervision_store import (
        CaptureError,
        CapturePolicy,
        create_capture,
        read_capture,
    )
    from tests.chain_fixtures import chain_metadata

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        archive(engine, prepare(chain_metadata()))
        request = FeedRequest(instrument_keys=("NSE_INDEX|Synthetic index",))
        plan = resolve_feed(engine, request)
        parent = create_capture(
            engine, request, CapturePolicy(max_sessions=2, max_events=1), "SYNTHETIC"
        )
        children = [
            start_session(engine, request, LifecyclePolicy(), "SYNTHETIC", parent) for _ in range(2)
        ]
        item = FeedEvent("PLAN", 1, plan=plan, observed_at=datetime.now(UTC), elapsed_ms=0)

        def fail(connection, cursor, statement, parameters, context, many):
            if statement.startswith("INSERT INTO observation_events"):
                raise SQLAlchemyError("synthetic rollback")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(SQLAlchemyError):
                append_event(engine, children[0], item)
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        assert read_capture(engine, parent)["capture"]["event_count"] == 0
        assert read_capture(engine, parent)["capture"]["payload_bytes"] == 0

        def attempt(child):
            try:
                return append_event(engine, child, item)
            except CaptureError:
                return "quota"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, children))
        assert outcomes.count(1) == 1 and outcomes.count("quota") == 1
        result = read_capture(engine, parent)
        assert result["capture"]["event_count"] == 1
        assert (
            sum(read_session(engine, child, 20, 0)["session"]["event_count"] for child in children)
            == 1
        )


def test_postgres_capture_restart_and_migration_preserve_observations(postgres_config):
    import asyncio

    from backend.app.market_data.supervision_store import read_capture
    from tests.integration.test_supervisor import build

    with TestClient(create_app(postgres_config)) as client:
        sign_in(client)
        token = client.cookies.get("admin_session")
        supervisor, _, _, _ = build(client.app.state.engine, 1)
        result = asyncio.run(supervisor.run())
        parent = result["capture"]["id"]
        child = result["sessions"][0]["id"]
    with TestClient(create_app(postgres_config)) as client:
        client.cookies.set("admin_session", token)
        assert client.get(f"/api/observations/captures/{parent}").status_code == 200
        assert read_capture(client.app.state.engine, parent)["capture"]["event_count"] == 3
        command.downgrade(Config("alembic.ini"), "0005_observations")
        assert client.get("/health/ready").status_code == 503
        command.upgrade(Config("alembic.ini"), "head")
        assert client.get("/health/ready").status_code == 200
        session = client.get(f"/api/observations/sessions/{child}").json()["session"]
        assert session["event_count"] == 3 and session["supervisor_id"] is None
        assert client.get(f"/api/observations/captures/{parent}").status_code == 404


def test_postgres_preflight_local_pass_does_not_write_or_certify(postgres_config):
    from backend.app.market_data.feed import FeedRequest
    from backend.app.market_data.preflight import capture_preflight
    from backend.app.market_data.supervision_store import CapturePolicy
    from tests.integration.test_preflight import KEY, configured, seed

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        seed(engine)
        result = capture_preflight(
            engine,
            configured(postgres_config),
            FeedRequest(instrument_keys=(KEY,)),
            CapturePolicy(),
        )
        assert result["state"] == "LOCAL_CHECKS_PASSED" and result["can_attempt_capture"]
        assert result["checks"]["write_privileges"] == "TABLE_GRANTS_PRESENT"
        assert result["catalog"]["state"] == "AVAILABLE"
        assert result["catalog"]["gate_result"] == "CURRENT_KEYS_RESOLVED"
        assert result["catalog"]["snapshot_id"] == result["catalog_snapshot_id"]
        assert not result["database_writes_verified"] and not result["broker_access_verified"]
        assert not result["recording_started"] and not result["live_enabled"]
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM capture_runs")) == 0
            assert connection.scalar(text("SELECT count(*) FROM observation_events")) == 0


def test_postgres_preflight_missing_write_privilege(postgres_config, postgres_restricted_role):
    from backend.app.market_data.feed import FeedRequest
    from backend.app.market_data.preflight import WRITE_PERMISSIONS, capture_preflight
    from backend.app.market_data.supervision_store import CapturePolicy
    from tests.integration.test_preflight import KEY, configured, seed

    owner, restricted, role = postgres_restricted_role
    seed(owner)
    with restricted.connect() as connection:
        identity = connection.execute(
            text(
                "SELECT current_user, session_user, r.rolsuper, r.rolcreaterole, r.rolbypassrls, "
                "c.relowner=r.oid AS owns_table, "
                "pg_has_role(current_user,c.relowner,'USAGE') AS inherits_owner "
                "FROM pg_roles r, pg_class c "
                "WHERE r.rolname=current_user AND c.oid='capture_runs'::regclass"
            )
        ).one()
        assert identity[0] == role and identity[1] != role
        assert not any(identity[2:])
        assert connection.scalar(
            text("SELECT has_table_privilege(current_user,'capture_runs','INSERT')")
        )
    baseline = capture_preflight(
        restricted,
        configured(postgres_config),
        FeedRequest(instrument_keys=(KEY,)),
        CapturePolicy(),
    )
    assert baseline["state"] == "LOCAL_CHECKS_PASSED"

    with owner.begin() as connection:
        # Role is generated by the fixture; quote it as an identifier, never interpolate input.
        quoted_role = owner.dialect.identifier_preparer.quote_identifier(role)
        connection.execute(text(f"REVOKE INSERT ON capture_runs FROM {quoted_role}"))
    with restricted.connect() as connection:
        for table, privilege in WRITE_PERMISSIONS:
            effective = connection.scalar(
                text("SELECT has_table_privilege(current_user,:table,:privilege)"),
                {"table": table, "privilege": privilege},
            )
            assert effective is ((table, privilege) != ("capture_runs", "INSERT"))
    # This zero-row statement still needs INSERT permission, but can never create a record.
    with pytest.raises(ProgrammingError) as denied, restricted.begin() as connection:
        connection.execute(text("INSERT INTO capture_runs SELECT * FROM capture_runs WHERE false"))
    assert denied.value.orig.sqlstate == "42501"

    result = capture_preflight(
        restricted,
        configured(postgres_config),
        FeedRequest(instrument_keys=(KEY,)),
        CapturePolicy(),
    )
    assert "DATABASE_PRIVILEGES_MISSING" in result["blockers"]
    assert result["blockers"] == ["DATABASE_PRIVILEGES_MISSING"]
    assert result["checks"]["write_privileges"] == "MISSING"
    assert not result["can_attempt_capture"]


def test_postgres_operator_stop_preserves_parent_quota_stats(postgres_config):
    from backend.app.market_data.feed import FeedRequest
    from backend.app.market_data.supervision_store import (
        CapturePolicy,
        capture_stop_requested,
        create_capture,
        finish_capture,
        read_capture,
        request_capture_stop,
    )

    with TestClient(create_app(postgres_config)) as client:
        engine = client.app.state.engine
        identity = create_capture(
            engine,
            FeedRequest(instrument_keys=("NSE_INDEX|Synthetic index",)),
            CapturePolicy(),
            "SYNTHETIC",
        )
        assert request_capture_stop(engine, identity)["stop_requested"]
        assert capture_stop_requested(engine, identity)
        first = read_capture(engine, identity)
        assert first["capture"]["event_count"] == 0 and first["capture"]["payload_bytes"] == 0
        assert request_capture_stop(engine, identity)["stop_requested"]
        assert read_capture(engine, identity) == first
        finish_capture(engine, identity, "COOPERATIVE_STOP")
        assert not request_capture_stop(engine, identity)["stop_requested"]
        assert read_capture(engine, identity)["capture"]["status"] == "CLOSED"
