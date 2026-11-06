import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.app.config import Settings
from backend.app.main import create_app

PASSWORD = "local-test-password-only"
ORIGIN = {"Origin": "http://testserver"}


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
