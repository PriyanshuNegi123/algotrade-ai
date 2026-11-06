import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sqlalchemy import text, update

from backend.app.instruments.models import InstrumentSnapshot
from backend.app.instruments.service import archive, prepare
from backend.app.market_data.calendar import CalendarError
from backend.app.market_data.contracts import IST
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.preflight import capture_preflight
from backend.app.market_data.supervision_store import CapturePolicy, create_capture, read_capture
from tests.chain_fixtures import chain_metadata
from tests.conftest import ORIGIN, PASSWORD

KEY = "NSE_INDEX|Synthetic index"
TOKEN = "synthetic-preflight-credential"


def configured(settings, **changes):
    return settings.model_copy(
        update={
            "upstox_analytics_token": SecretStr(TOKEN),
            "upstox_analytics_expires_at": datetime.now(UTC) + timedelta(hours=2),
            **changes,
        }
    )


def inspect(engine, settings, **kwargs):
    return capture_preflight(
        engine,
        settings,
        FeedRequest(instrument_keys=(KEY,)),
        kwargs.pop("policy", CapturePolicy()),
        **kwargs,
    )


def seed(engine):
    archive(engine, prepare(chain_metadata()))


def test_missing_token_test_db_and_no_writes_or_secret_echo(client):
    engine = client.app.state.engine
    seed(engine)
    result = inspect(engine, client.app.state.settings)
    assert result["state"] == "BLOCKED" and "CREDENTIAL_MISSING" in result["blockers"]
    assert "DATABASE_TEST_ONLY" in result["blockers"]
    assert result["checks"]["metadata"] == "CURRENT_KEYS_RESOLVED"
    configured_result = inspect(engine, configured(client.app.state.settings))
    serialized = json.dumps(configured_result, default=str)
    assert TOKEN not in serialized
    assert client.app.state.settings.admin_password_hash.get_secret_value() not in serialized
    assert client.app.state.settings.database_url.get_secret_value() not in serialized
    assert (
        not configured_result["broker_access_verified"]
        and not configured_result["recording_started"]
    )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM capture_runs")) == 0
        assert connection.scalar(text("SELECT count(*) FROM observation_sessions")) == 0


@pytest.mark.parametrize(
    "expiry,code", [(-1, "CREDENTIAL_EXPIRED"), (30, "CREDENTIAL_WINDOW_TOO_SHORT")]
)
def test_expiry_window_checks(client, expiry, code):
    settings = configured(
        client.app.state.settings,
        upstox_analytics_expires_at=datetime.now(UTC) + timedelta(seconds=expiry),
    )
    result = inspect(client.app.state.engine, settings)
    assert code in result["blockers"] and not result["can_attempt_capture"]


def test_schema_mismatch_never_migrates(client):
    engine = client.app.state.engine
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='0005_observations'"))
    with patch("alembic.command.upgrade", side_effect=AssertionError("Must not migrate")):
        result = inspect(engine, configured(client.app.state.settings))
    assert "SCHEMA_REVISION_MISMATCH" in result["blockers"]
    assert result["checks"]["metadata"] == "NOT_CHECKED"


def test_missing_table_safe_failure(client):
    engine = client.app.state.engine
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE observation_events"))
    result = inspect(engine, configured(client.app.state.settings))
    assert "SCHEMA_UNAVAILABLE" in result["blockers"]


def test_unavailable_database_redacts_error(client, monkeypatch):
    engine = client.app.state.engine
    from sqlalchemy.exc import OperationalError

    def broken():
        raise OperationalError(TOKEN, None, Exception(TOKEN))

    monkeypatch.setattr(engine, "connect", broken)
    result = inspect(engine, configured(client.app.state.settings))
    assert "DATABASE_UNAVAILABLE" in result["blockers"] and TOKEN not in json.dumps(
        result, default=str
    )
    assert result["catalog"] is None


def test_catalog_diagnostics_missing_never_invents_provenance(client):
    result = inspect(client.app.state.engine, configured(client.app.state.settings))
    assert result["catalog"] == {"state": "NOT_IMPORTED", "gate_result": "CURRENT_CATALOG_REQUIRED"}
    assert result["catalog_snapshot_id"] is None
    assert "CURRENT_CATALOG_REQUIRED" in result["blockers"]


def test_catalog_diagnostics_excludes_raw_archive_and_source_fields(client):
    from sqlalchemy import event

    engine = client.app.state.engine
    seed(engine)
    marker = "synthetic-private-source-marker"
    with engine.begin() as connection:
        connection.execute(
            update(InstrumentSnapshot).values(source_url=marker, raw_gzip=marker.encode())
        )
        before = connection.execute(
            text(
                "SELECT id, source_modified_at, retrieved_at, imported_at FROM instrument_snapshots"
            )
        ).all()
    statements = []

    def observed_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observed_sql)
    try:
        result = inspect(engine, configured(client.app.state.settings))
    finally:
        event.remove(engine, "before_cursor_execute", observed_sql)
    assert marker not in json.dumps(result, default=str)
    assert all("raw_gzip" not in statement for statement in statements)
    assert set(result["catalog"]) == {
        "state",
        "snapshot_id",
        "source_modified_at",
        "source_publication_date_ist",
        "retrieved_at",
        "imported_at",
        "checked_date_ist",
        "gate_result",
    }
    assert result["catalog"]["state"] == "AVAILABLE"
    assert result["catalog"]["gate_result"] == "CURRENT_KEYS_RESOLVED"
    assert result["catalog"]["snapshot_id"] == result["catalog_snapshot_id"]
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT id, source_modified_at, retrieved_at, imported_at "
                    "FROM instrument_snapshots"
                )
            ).all()
            == before
        )


def test_stale_diagnostics_explain_ist_dates_without_changing_gate(client):
    engine = client.app.state.engine
    seed(engine)
    published = datetime.now(UTC) - timedelta(days=2)
    with engine.begin() as connection:
        connection.execute(update(InstrumentSnapshot).values(source_modified_at=published))
    result = inspect(engine, configured(client.app.state.settings))
    context = result["catalog"]
    assert context["source_modified_at"] == published
    assert context["source_publication_date_ist"] == published.astimezone(IST).date()
    assert context["checked_date_ist"] == result["checked_at"].astimezone(IST).date()
    assert context["gate_result"] == "CURRENT_CATALOG_REQUIRED"
    assert "CURRENT_CATALOG_REQUIRED" in result["blockers"]
    assert not result["can_attempt_capture"] and not result["recording_started"]


def test_stale_catalog_and_unsupported_keys(client):
    engine = client.app.state.engine
    seed(engine)
    settings = configured(client.app.state.settings)
    request = FeedRequest(instrument_keys=("NSE_FO|missing",))
    result = capture_preflight(engine, settings, request, CapturePolicy())
    assert "FEED_KEY_NOT_IN_CATALOG" in result["blockers"]
    with engine.begin() as connection:
        connection.execute(
            update(InstrumentSnapshot).values(
                source_modified_at=datetime.now(UTC) - timedelta(days=2)
            )
        )
    assert "CURRENT_CATALOG_REQUIRED" in inspect(engine, settings)["blockers"]


def test_active_run_not_recovered_or_mutated(client):
    engine = client.app.state.engine
    seed(engine)
    identity = create_capture(
        engine, FeedRequest(instrument_keys=(KEY,)), CapturePolicy(), "SYNTHETIC"
    )
    before = read_capture(engine, identity)
    assert (
        "LOCAL_CAPTURE_PRESENT"
        in inspect(engine, configured(client.app.state.settings))["blockers"]
    )
    assert read_capture(engine, identity) == before


def test_policy_reserve_and_mode(client):
    engine = client.app.state.engine
    seed(engine)
    settings = configured(client.app.state.settings, trading_mode="PAPER")
    result = inspect(engine, settings, policy=CapturePolicy(max_events=1, max_payload_bytes=1))
    assert {
        "OBSERVATION_MODE_REQUIRED",
        "EVENT_QUOTA_BELOW_INITIAL_SEQUENCE",
        "BYTE_QUOTA_BELOW_PLAN_RESERVE",
    }.issubset(result["blockers"])
    assert result["plan_reserve_bytes"] > 1 and not result["live_enabled"]


def test_calendar_integrity_failure_is_explicit(client):
    with patch("backend.app.market_data.preflight.load_calendar", side_effect=CalendarError("bad")):
        result = inspect(client.app.state.engine, configured(client.app.state.settings))
    assert "CALENDAR_EVIDENCE_INVALID" in result["blockers"]


def test_fo_unknown_calendar_and_index_scope_are_distinct(client):
    settings = configured(
        client.app.state.settings, upstox_analytics_expires_at=datetime(2030, 1, 1, tzinfo=UTC)
    )
    now = datetime(2027, 1, 4, tzinfo=UTC)
    result = capture_preflight(
        client.app.state.engine,
        settings,
        FeedRequest(instrument_keys=("NSE_FO|missing",)),
        CapturePolicy(),
        now=now,
    )
    assert "CALENDAR_UNKNOWN" in result["blockers"]
    index = inspect(client.app.state.engine, settings, now=now)
    assert "CALENDAR_UNKNOWN" not in index["blockers"]
    assert "INDEX_REFERENCE_CALENDAR_UNVERIFIED" in index["warnings"]


def test_private_endpoint_validation_and_no_mutation(client):
    params = {"instrument_key": KEY}
    assert client.get("/api/observations/preflight", params=params).status_code == 401
    client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    response = client.get("/api/observations/preflight", params=params)
    assert response.status_code == 200 and response.json()["state"] == "BLOCKED"
    assert (
        client.get(
            "/api/observations/preflight", params={**params, "max_events": 100001}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/observations/preflight", params={"instrument_key": "https://evil.example"}
        ).status_code
        == 422
    )
    assert client.post("/api/observations/preflight", json={}).status_code == 405


def test_cli_invalid_configuration_safe_json(capsys, monkeypatch):
    from scripts import capture_preflight as command

    monkeypatch.setattr(sys, "argv", ["preflight", "--instrument-key", KEY])
    with patch.object(command, "Settings", side_effect=ValueError(TOKEN)):
        assert command.main() == 2
    output = capsys.readouterr().out
    assert TOKEN not in output and json.loads(output)["state"] == "BLOCKED"


def test_supervisor_cli_blocked_preflight_never_starts(client, capsys, monkeypatch):
    from scripts import supervise_capture as command

    monkeypatch.setattr(sys, "argv", ["supervise", "--instrument-key", KEY])
    with (
        patch.object(command, "Settings", return_value=client.app.state.settings),
        patch.object(command, "build_engine", return_value=client.app.state.engine),
        patch.object(
            command, "CaptureSupervisor", side_effect=AssertionError("Must not start capture")
        ),
    ):
        with pytest.raises(SystemExit) as exit_code:
            asyncio.run(command.main())
    assert exit_code.value.code == 2
    assert json.loads(capsys.readouterr().out)["recording_started"] is False
