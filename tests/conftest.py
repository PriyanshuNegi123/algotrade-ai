import os
from datetime import UTC, datetime
from importlib import import_module
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.app.config import Settings
from backend.app.main import create_app

PASSWORD = "local-test-password-only"
ORIGIN = {"Origin": "http://testserver"}
COVERAGE_NOW = datetime(2026, 11, 6, 6, 30, tzinfo=UTC)  # Synthetic noon IST, never real evidence.


@pytest.fixture
def coverage_clock(monkeypatch):
    """Opt-in shared time for synthetic catalog/recording/coverage fixtures only.

    Authentication, unrelated tests, the OS clock and production policy are not frozen.
    Module attributes are restored by monkeypatch after each requesting test.
    """

    class FixtureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return COVERAGE_NOW.replace(tzinfo=None)
            return COVERAGE_NOW.astimezone(tz)

    for name in (
        "tests.instrument_fixtures",
        "tests.chain_fixtures",
        "backend.app.instruments.service",
        "backend.app.market_data.feed",
        "backend.app.market_data.observations",
        "backend.app.market_data.coverage",
    ):
        monkeypatch.setattr(import_module(name), "datetime", FixtureDatetime)
    return COVERAGE_NOW


@pytest.fixture(scope="session")
def password_hash():
    return PasswordHasher().hash(PASSWORD)


@pytest.fixture
def client(tmp_path, monkeypatch, password_hash):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=url,
        admin_password_hash=password_hash,
        allowed_origins=["http://testserver"],
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def prohibit_outbound_http(monkeypatch):
    """All real HTTP transports are forbidden in pytest; injected mocks remain usable."""
    import httpx
    from websockets.asyncio.client import connect

    def blocked(*args, **kwargs):
        raise AssertionError("Real outbound HTTP is forbidden in automated tests")

    async def async_blocked(*args, **kwargs):
        raise AssertionError("Real outbound HTTP is forbidden in automated tests")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)
    monkeypatch.setattr(connect, "create_connection", async_blocked)


@pytest.fixture
def postgres_config(monkeypatch, password_hash):
    raw_url = os.environ.get("TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("TEST_POSTGRES_URL not set; dedicated PostgreSQL required")
    url = make_url(raw_url)
    assert url.drivername == "postgresql+psycopg"
    # Never modify an existing schema, including public or another test's schema.
    schema = f"verify_{uuid4().hex}"
    root_engine = create_engine(url, hide_parameters=True)
    try:
        with root_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
        rendered_url = scoped_url.render_as_string(hide_password=False)
        monkeypatch.setenv("DATABASE_URL", rendered_url)
        monkeypatch.setenv("APP_ENV", "test")
        command.upgrade(Config("alembic.ini"), "head")
        yield Settings(
            _env_file=None,
            app_env="test",
            database_url=rendered_url,
            admin_password_hash=password_hash,
            allowed_origins=["http://testserver"],
        )
    finally:
        try:
            with root_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            root_engine.dispose()


@pytest.fixture
def postgres_restricted_role(postgres_config):
    """A disposable non-owner execution role, even when CI setup is a superuser.

    Only the disposable database setup login needs CREATEROLE. SET ROLE on each
    new connection exercises actual PostgreSQL permissions without another password.
    """
    from backend.app.market_data.preflight import WRITE_PERMISSIONS

    url = make_url(postgres_config.database_url.get_secret_value())
    owner = create_engine(url, hide_parameters=True)
    restricted = create_engine(url, hide_parameters=True)
    role = f"verify_restricted_{uuid4().hex}"
    quote = owner.dialect.identifier_preparer.quote_identifier
    created = False
    try:
        with owner.begin() as connection:
            schema = connection.scalar(text("SELECT current_schema()"))
            assert schema.startswith("verify_") and len(schema) == 39
            setup_user = connection.scalar(text("SELECT current_user"))
            assert connection.scalar(
                text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname=current_user")
            ), "Disposable PostgreSQL setup login requires CREATEROLE for role-isolation tests"
            connection.execute(
                text(
                    f"CREATE ROLE {quote(role)} NOLOGIN NOSUPERUSER NOCREATEDB "
                    "NOCREATEROLE NOINHERIT NOBYPASSRLS"
                )
            )
            connection.execute(text(f"GRANT USAGE ON SCHEMA {quote(schema)} TO {quote(role)}"))
            connection.execute(
                text(f"GRANT SELECT ON ALL TABLES IN SCHEMA {quote(schema)} TO {quote(role)}")
            )
            for table, privilege in WRITE_PERMISSIONS:
                connection.execute(
                    text(f"GRANT {privilege} ON {quote(schema)}.{quote(table)} TO {quote(role)}")
                )
            connection.execute(
                text(f"GRANT {quote(role)} TO {quote(setup_user)} WITH SET TRUE, INHERIT FALSE")
            )
        created = True

        @event.listens_for(restricted, "connect")
        def assume_restricted_role(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            dbapi_connection.commit()

        yield owner, restricted, role
    finally:
        restricted.dispose()
        try:
            if created:
                with owner.begin() as connection:
                    connection.execute(
                        text(
                            f"REVOKE ALL ON ALL TABLES IN SCHEMA {quote(schema)} FROM {quote(role)}"
                        )
                    )
                    connection.execute(
                        text(f"REVOKE USAGE ON SCHEMA {quote(schema)} FROM {quote(role)}")
                    )
                    # DROP ROLE also removes its memberships. Keep the creator's
                    # ADMIN option until then so non-superuser setup can drop it.
                    connection.execute(text(f"DROP ROLE {quote(role)}"))
                    assert not connection.scalar(
                        text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"),
                        {"role": role},
                    )
        finally:
            owner.dispose()
