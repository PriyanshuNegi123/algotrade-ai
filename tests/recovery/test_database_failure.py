from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.conftest import ORIGIN, PASSWORD


def test_missing_schema_disables_authentication_but_liveness_survives(client):
    with client.app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE admin_sessions"))
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 503
    assert ready.json()["entries_enabled"] is False
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert login.status_code == 503
    assert "sqlite" not in login.text


def test_migration_round_trip(client):
    command.downgrade(Config("alembic.ini"), "base")
    assert client.get("/health/ready").status_code == 503
    command.upgrade(Config("alembic.ini"), "head")
    assert client.get("/health/ready").status_code == 200


def test_wrong_schema_revision_not_ready(client):
    with client.app.state.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'outdated'"))
    assert client.get("/health/ready").status_code == 503
