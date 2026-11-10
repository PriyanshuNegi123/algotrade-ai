import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, text, update

from backend.app.api.oauth import components
from backend.app.brokers.oauth import OAuthError, UpstoxOAuth
from backend.app.database import AdminSession
from backend.app.main import create_app
from backend.app.security.oauth_privacy import OAuthPrivacyMiddleware
from tests.conftest import PASSWORD

ORIGIN = "http://127.0.0.1:8000"
TOKEN = "synthetic-callback-bearer"
CODE = "synthetic-callback-code"


@pytest.fixture
def oauth_client(client, tmp_path):
    settings = client.app.state.settings.model_copy(
        update={
            "allowed_origins": [ORIGIN],
            "upstox_client_id": "synthetic-client",
            "upstox_client_secret": SecretStr("synthetic-private-value"),
            "upstox_redirect_uri": ORIGIN + "/auth/upstox/callback",
            "upstox_oauth_vault_dir": str(tmp_path / "oauth-vault"),
        }
    )
    app = create_app(settings)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"access_token": TOKEN, "email": "synthetic-private-profile"}
        )

    app.state.oauth_client = UpstoxOAuth(transport=httpx.MockTransport(handler))
    with TestClient(app, base_url=ORIGIN) as result:
        yield result, requests


def login(client):
    result = client.post("/api/auth/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN})
    assert result.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": result.json()["csrf_token"]}


def begin(client, headers):
    response = client.post("/api/broker/oauth/start", headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert parse_qs(urlsplit(result["authorization_url"]).query)["state"] == [result["state"]]
    return result


def finish_body(flow, **changes):
    return {"state": flow["state"], "flow_nonce": flow["flow_nonce"], "code": CODE, **changes}


def test_default_app_disables_flow_without_initializing_storage(client):
    login_response = client.post(
        "/api/auth/login", json={"password": PASSWORD}, headers={"Origin": "http://testserver"}
    )
    headers = {"Origin": "http://testserver", "X-CSRF-Token": login_response.json()["csrf_token"]}
    status = client.get("/api/broker/oauth/status").json()
    assert status["state"] == "LOCAL_SETUP_REQUIRED" and not status["can_start"]
    assert client.post("/api/broker/oauth/start", headers=headers).status_code == 503
    assert client.get("/auth/upstox/callback?code=" + CODE + "&state=unused").status_code == 404


def test_authenticated_flow_preserves_strict_cookie_and_only_stores_encrypted_token(oauth_client):
    client, requests = oauth_client
    headers = login(client)
    response = client.post(
        "/api/auth/login", json={"password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert (
        "SameSite=strict" in response.headers["set-cookie"]
        and "HttpOnly" in response.headers["set-cookie"]
    )
    headers["X-CSRF-Token"] = response.json()["csrf_token"]
    directory = Path(client.app.state.settings.upstox_oauth_vault_dir)
    assert not directory.exists()
    assert client.get("/api/broker/oauth/status").json()["can_start"]
    assert not directory.exists()
    flow = begin(client, headers)
    assert (directory / "vault.key").is_file() and not (directory / "token.enc").exists()
    result = client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow))
    assert result.status_code == 200 and result.json()["state"] == "STORED_UNVERIFIED"
    assert len(requests) == 1 and TOKEN not in result.text and CODE not in result.text
    assert TOKEN.encode() not in (directory / "token.enc").read_bytes()
    assert client.get("/api/broker/oauth/status").json()["state"] == "STORED_UNVERIFIED"
    assert (
        client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow)).status_code
        == 400
    )
    assert len(requests) == 1
    _, _, _, store = components(client.app.state.settings)
    from backend.app.brokers.oauth import configured_app

    assert (
        store.load(configured_app(client.app.state.settings)).access_token.get_secret_value()
        == TOKEN
    )
    assert not client.get("/api/overview").json()["live_enabled"]
    assert not client.app.state.settings.upstox_analytics_token.get_secret_value()


def test_anonymous_callback_get_is_static_and_never_exchanges_or_writes_tokens(oauth_client):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)
    cookie = client.cookies.get("admin_session")
    client.cookies.clear()
    response = client.get("/auth/upstox/callback?code=" + CODE + "&state=" + flow["state"])
    assert (
        response.status_code == 200
        and CODE not in response.text
        and flow["state"] not in response.text
    )
    assert (
        not requests
        and not (Path(client.app.state.settings.upstox_oauth_vault_dir) / "token.enc").exists()
    )
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert "unsafe-inline" not in response.headers["Content-Security-Policy"]
    assert "set-cookie" not in response.headers
    client.cookies.set("admin_session", cookie, domain="127.0.0.1", path="/")
    assert (
        client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow)).status_code
        == 200
    )


@pytest.mark.parametrize("kind", ["anonymous", "origin", "csrf", "nonce", "session"])
def test_finish_requires_current_session_origin_csrf_and_browser_nonce(oauth_client, kind):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)
    body = finish_body(flow)
    if kind == "anonymous":
        client.cookies.clear()
    elif kind == "origin":
        headers["Origin"] = "https://evil.example"
    elif kind == "csrf":
        headers["X-CSRF-Token"] = "incorrect"
    elif kind == "nonce":
        body["flow_nonce"] = "x" * 43
    else:
        headers = login(client)
    result = client.post("/api/broker/oauth/finish", headers=headers, json=body)
    assert result.status_code in {400, 401, 403} and not requests
    assert CODE not in result.text


@pytest.mark.parametrize("kind", ["anonymous", "origin", "csrf"])
def test_start_requires_authenticated_same_origin_csrf_without_preparing_key(oauth_client, kind):
    client, requests = oauth_client
    headers = login(client)
    if kind == "anonymous":
        client.cookies.clear()
    elif kind == "origin":
        headers["Origin"] = "https://evil.example"
    else:
        headers.pop("X-CSRF-Token")
    assert client.post("/api/broker/oauth/start", headers=headers).status_code in {401, 403}
    assert not Path(client.app.state.settings.upstox_oauth_vault_dir).exists() and not requests


def test_provider_denial_and_user_cancel_burn_state_without_token_request(oauth_client):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)
    result = client.post(
        "/api/broker/oauth/finish", headers=headers, json=finish_body(flow, code=None, denied=True)
    )
    assert result.status_code == 200 and result.json()["state"] == "AUTHORIZATION_DENIED"
    assert not requests
    assert (
        client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow)).status_code
        == 400
    )


@pytest.mark.parametrize(
    "kind", ["logout-before", "logout-during", "expiry-during", "config-during", "new-flow-during"]
)
def test_revocation_expiry_and_changed_settings_cannot_persist_a_token(oauth_client, kind):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)

    def mutate():
        if kind == "config-during":
            client.app.state.settings.upstox_client_id = "changed-client"
        elif kind == "new-flow-during":
            from backend.app.auth.service import digest
            from backend.app.brokers.oauth import configured_app

            client.app.state.oauth_flows.begin(
                configured_app(client.app.state.settings),
                digest(client.cookies.get("admin_session")),
                datetime.now(UTC) + timedelta(minutes=15),
                storage_context=client.app.state.settings.upstox_oauth_vault_dir,
            )
        else:
            with client.app.state.engine.begin() as connection:
                if kind == "expiry-during":
                    connection.execute(
                        update(AdminSession).values(
                            expires_at=datetime.now(UTC) - timedelta(seconds=1)
                        )
                    )
                else:
                    connection.execute(delete(AdminSession))

    if kind == "logout-before":
        mutate()
    else:

        def handler(request):
            requests.append(request)
            mutate()
            return httpx.Response(200, json={"access_token": TOKEN})

        client.app.state.oauth_client = UpstoxOAuth(transport=httpx.MockTransport(handler))
    result = client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow))
    assert result.status_code in {400, 401, 503}
    assert not (Path(client.app.state.settings.upstox_oauth_vault_dir) / "token.enc").exists()
    assert len(requests) == (0 if kind == "logout-before" else 1)


def test_second_start_invalidates_previous_browser_flow(oauth_client):
    client, requests = oauth_client
    headers = login(client)
    old = begin(client, headers)
    new = begin(client, headers)
    assert (
        client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(old)).status_code
        == 400
    )
    assert not requests
    assert (
        client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(new)).status_code
        == 200
    )


@pytest.mark.parametrize("kind", ["body", "query", "invalid-json"])
def test_secret_bearing_invalid_requests_are_bounded_and_not_echoed(oauth_client, kind):
    client, requests = oauth_client
    headers = login(client)
    if kind == "body":
        result = client.post("/api/broker/oauth/finish", headers=headers, content=CODE * 2000)
    elif kind == "query":
        result = client.post("/api/broker/oauth/finish?code=" + CODE, headers=headers, json={})
    else:
        result = client.post(
            "/api/broker/oauth/finish", headers=headers, json={"code": CODE, "unknown": TOKEN}
        )
    assert (
        result.status_code in {400, 413, 422}
        and CODE not in result.text
        and TOKEN not in result.text
    )
    assert not requests
    assert result.headers["Cache-Control"] == "no-store"
    assert result.headers["Referrer-Policy"] == "no-referrer"


def test_privacy_middleware_scrubs_original_scope_and_never_logs_callback_query():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/upstox/callback",
        "raw_path": b"/auth/upstox/callback",
        "query_string": ("code=" + CODE + "&state=synthetic-state").encode(),
        "headers": [],
    }
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["query_string"])

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        pass

    asyncio.run(OAuthPrivacyMiddleware(app, [])(scope, receive, send))
    assert seen == [b""] and scope["query_string"] == b"" and CODE.encode() not in scope["raw_path"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/return",
        "/assets/return",
        "/health/return",
        "/docs",
        "/callback/",
        "/callback%2Freturn",
    ],
)
def test_callback_cannot_shadow_reserved_or_noncanonical_paths(client, tmp_path, path):
    settings = client.app.state.settings.model_copy(
        update={
            "allowed_origins": [ORIGIN],
            "upstox_client_id": "synthetic-client",
            "upstox_client_secret": SecretStr("synthetic-private-value"),
            "upstox_redirect_uri": ORIGIN + path,
            "upstox_oauth_vault_dir": str(tmp_path / "vault"),
        }
    )
    with pytest.raises(OAuthError):
        components(settings)


def test_application_logs_never_include_code_nonce_or_bearer(oauth_client, caplog):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)
    logger = logging.getLogger("algotrade")
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="algotrade"):
            client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow))
    finally:
        logger.removeHandler(caplog.handler)
    assert any(record.name == "algotrade" for record in caplog.records)
    # Application formatter only emits allowlisted operational fields; no request/body fields.
    from backend.app.security.logging import SafeJSONFormatter

    output = "".join(
        SafeJSONFormatter().format(record)
        for record in caplog.records
        if record.name == "algotrade"
    )
    assert CODE not in output and TOKEN not in output and flow["flow_nonce"] not in output


@pytest.mark.parametrize("revoke", [False, True])
def test_postgres_callback_final_session_check(postgres_config, tmp_path, revoke):
    settings = postgres_config.model_copy(
        update={
            "allowed_origins": [ORIGIN],
            "upstox_client_id": "synthetic-client",
            "upstox_client_secret": SecretStr("synthetic-private-value"),
            "upstox_redirect_uri": ORIGIN + "/auth/upstox/callback",
            "upstox_oauth_vault_dir": str(tmp_path / "pg-vault"),
        }
    )
    app = create_app(settings)
    calls = []

    def handler(request):
        calls.append(request)
        if revoke:
            with app.state.engine.begin() as connection:
                connection.execute(delete(AdminSession))
        return httpx.Response(200, json={"access_token": TOKEN})

    app.state.oauth_client = UpstoxOAuth(transport=httpx.MockTransport(handler))
    with TestClient(app, base_url=ORIGIN) as client:
        headers = login(client)
        flow = begin(client, headers)
        result = client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow))
        assert result.status_code == (401 if revoke else 200)
        assert len(calls) == 1
        assert (tmp_path / "pg-vault/token.enc").exists() is not revoke
        with app.state.engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM capture_runs")) == 0
            assert connection.scalar(text("SELECT count(*) FROM observation_events")) == 0


def test_unsafe_storage_blocks_start_before_broker_consent(oauth_client):
    client, requests = oauth_client
    headers = login(client)
    directory = Path(client.app.state.settings.upstox_oauth_vault_dir)
    directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    assert not client.get("/api/broker/oauth/status").json()["can_start"]
    result = client.post("/api/broker/oauth/start", headers=headers)
    assert result.status_code == 503 and result.json()["detail"] == "OAUTH_STORAGE_UNAVAILABLE"
    assert not requests and not list(directory.iterdir())
    assert not client.app.state.oauth_flows._bindings


def test_storage_location_change_after_start_invalidates_binding(oauth_client, tmp_path):
    client, requests = oauth_client
    headers = login(client)
    flow = begin(client, headers)
    replacement = tmp_path / "replacement-vault"
    client.app.state.settings.upstox_oauth_vault_dir = str(replacement)
    result = client.post("/api/broker/oauth/finish", headers=headers, json=finish_body(flow))
    assert result.status_code == 400 and result.json()["detail"] == "OAUTH_APP_CHANGED"
    assert not requests and not replacement.exists()
