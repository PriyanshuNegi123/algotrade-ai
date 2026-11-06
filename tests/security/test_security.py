import logging

import pytest

from backend.app.security.logging import SafeJSONFormatter
from tests.conftest import ORIGIN, PASSWORD


def test_csrf_and_origin_validation(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 403
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    csrf = login.json()["csrf_token"]
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/overview").status_code == 200


def test_login_rate_limit(client):
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", json={"password": "incorrect-password"}, headers=ORIGIN
            ).status_code
            == 401
        )
    response = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_injection_is_not_authentication(client):
    assert (
        client.post(
            "/api/auth/login", json={"password": "' OR 1=1 -- password"}, headers=ORIGIN
        ).status_code
        == 401
    )
    client.cookies.set("admin_session", "' OR 1=1 --")
    assert client.get("/api/overview").status_code == 401


@pytest.mark.parametrize("path", ["/api/orders", "/api/live/activate", "/api/risk", "/api/kill"])
def test_execution_and_mutation_routes_do_not_exist(client, path):
    assert client.post(path, json={"mode": "LIVE"}).status_code == 404


def test_headers_and_host(client):
    response = client.get("/")
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/.env").status_code == 404
    assert client.get("/docs").status_code == 404


def test_logs_cannot_emit_secrets_or_injected_messages():
    record = logging.LogRecord(
        "algotrade", logging.ERROR, "", 0, "access_token=TOP_SECRET", (), None
    )
    record.authorization = "TOP_SECRET"
    record.password = "TOP_SECRET"
    formatted = SafeJSONFormatter().format(record)
    assert "TOP_SECRET" not in formatted
    assert "application_event" in formatted


def test_invalid_payload_never_echoes_password(client):
    response = client.post("/api/auth/login", json={"password": "tiny-secret"}, headers=ORIGIN)
    assert response.status_code == 422
    assert "tiny-secret" not in response.text
