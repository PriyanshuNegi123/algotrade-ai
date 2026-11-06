from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.auth.service import digest
from backend.app.database import AdminSession
from tests.conftest import ORIGIN, PASSWORD


def signin(client):
    return client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)


def test_health_and_dashboard(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").status_code == 200
    response = client.get("/")
    assert response.status_code == 200
    assert "Observation first" in response.text
    assert client.get("/assets/js/app.js").status_code == 200
    assert client.get("/api/overview").status_code == 401


def test_login_private_state_logout_and_revocation(client):
    login = signin(client)
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]
    token = client.cookies.get("admin_session")
    with Session(client.app.state.engine) as db:
        session = db.get(AdminSession, digest(token))
        assert session is not None
        assert session.token_digest != token
    state = client.get("/api/overview").json()
    assert state["balance"] is None
    assert state["positions"] == []
    assert state["live_enabled"] is False
    assert state["entries_enabled"] is False
    csrf = login.json()["csrf_token"]
    assert (
        client.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": csrf}).status_code == 204
    )
    client.cookies.set("admin_session", token)
    assert client.get("/api/overview").status_code == 401


def test_expiry_is_enforced(client):
    signin(client)
    with Session(client.app.state.engine) as db:
        session = db.get(AdminSession, digest(client.cookies.get("admin_session")))
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/overview").status_code == 401


def test_unconfigured_admin_fails_closed(client):
    from pydantic import SecretStr

    client.app.state.settings.admin_password_hash = SecretStr("")
    assert client.get("/health/ready").status_code == 503
    assert signin(client).status_code == 503
