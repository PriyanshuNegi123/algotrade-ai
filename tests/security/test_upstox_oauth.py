import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.app.brokers.oauth import (
    AUTHORIZATION_URL,
    MAX_RESPONSE_BYTES,
    TOKEN_URL,
    OAuthApp,
    OAuthError,
    OAuthStates,
    UpstoxOAuth,
    daily_cutoff,
)
from backend.app.market_data.contracts import IST

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
SESSION = hashlib.sha256(b"synthetic-admin-session").hexdigest()
OTHER = hashlib.sha256(b"different-synthetic-session").hexdigest()
BEARER = "synthetic-oauth-bearer"
CODE = SecretStr("synthetic-authorization-code")


@pytest.fixture
def app():
    return OAuthApp(
        client_id="synthetic-client",
        redirect_uri="http://127.0.0.1:8000/auth/upstox/callback",
        client_secret=SecretStr("synthetic-private-value"),
    )


def begin(app, *, states=None, now=NOW, session=SESSION, expires=None):
    states = states or OAuthStates()
    authorization = states.begin(app, session, expires or now + timedelta(minutes=15), now=now)
    state = parse_qs(urlsplit(authorization.url.get_secret_value()).query)["state"][0]
    return states, authorization, state


def test_authorization_has_only_official_fields_and_exact_callback_and_redacted_repr(app):
    states, authorization, state = begin(app)
    url = urlsplit(authorization.url.get_secret_value())
    assert url.scheme + "://" + url.netloc + url.path == AUTHORIZATION_URL
    assert parse_qs(url.query) == {
        "response_type": ["code"],
        "client_id": [app.client_id],
        "redirect_uri": [app.redirect_uri],
        "state": [state],
    }
    assert authorization.expires_at == NOW + timedelta(minutes=5)
    assert state not in repr(authorization) and state not in repr(states._pending)
    assert app.client_secret.get_secret_value() not in repr(app)
    assert state not in states._pending


def test_wrong_session_cannot_consume_and_correct_session_can_consume_only_once(app):
    states, _, state = begin(app)
    with pytest.raises(OAuthError, match="SESSION_MISMATCH"):
        states.consume(app, state, OTHER, now=NOW)
    states.consume(app, state, SESSION, now=NOW)
    with pytest.raises(OAuthError, match="STATE_INVALID"):
        states.consume(app, state, SESSION, now=NOW)


def test_state_is_session_expiry_bounded_and_expires_at_exact_boundary(app):
    states, authorization, state = begin(app, expires=NOW + timedelta(seconds=20))
    assert authorization.expires_at == NOW + timedelta(seconds=20)
    with pytest.raises(OAuthError, match="STATE_EXPIRED"):
        states.consume(app, state, SESSION, now=authorization.expires_at)


def test_restart_and_new_flow_invalidate_old_state(app):
    states, _, old = begin(app)
    _, _, fresh = begin(app, states=states)
    with pytest.raises(OAuthError, match="STATE_INVALID"):
        states.consume(app, old, SESSION, now=NOW)
    with pytest.raises(OAuthError, match="STATE_INVALID"):
        OAuthStates().consume(app, fresh, SESSION, now=NOW)
    states.consume(app, fresh, SESSION, now=NOW)


def test_changed_app_configuration_and_clock_rollback_invalidate_state(app):
    for altered in (
        app.model_copy(update={"client_id": "other-client"}),
        app.model_copy(update={"client_secret": SecretStr("different-secret")}),
        app.model_copy(update={"redirect_uri": "https://example.test/other-callback"}),
    ):
        states, _, state = begin(app)
        with pytest.raises(OAuthError, match="APP_CHANGED"):
            states.consume(altered, state, SESSION, now=NOW)
    states, _, state = begin(app)
    with pytest.raises(OAuthError, match="CLOCK_INVALID"):
        states.consume(app, state, SESSION, now=NOW - timedelta(seconds=1))


def test_active_ledger_bound_and_expired_cleanup(app):
    states = OAuthStates()
    for number in range(32):
        begin(app, states=states, session=f"{number:064x}")
    with pytest.raises(OAuthError, match="PENDING_LIMIT"):
        begin(app, states=states, session="f" * 64)
    assert len(states._pending) == 32
    begin(app, states=states, now=NOW + timedelta(minutes=5))
    assert len(states._pending) == 1


def test_concurrent_callbacks_have_exactly_one_consumer(app):
    states, _, state = begin(app)

    def consume(_):
        try:
            states.consume(app, state, SESSION, now=NOW)
            return True
        except OAuthError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(consume, range(16))) == 1


@pytest.mark.parametrize(
    "redirect",
    [
        "http://remote.example/callback",
        "https://user:password@example.com/callback",
        "https://example.com/callback?next=evil",
        "https://example.com/callback#fragment",
        "https://example.com/callback?",
        "https://example.com/callback#",
        "https://example.com\\@evil.test/callback",
        "https://example.com/\ncallback",
        "//example.com/callback",
        "https://example.com:99999/callback",
    ],
)
def test_callback_configuration_rejects_unsafe_urls(app, redirect):
    with pytest.raises(ValidationError):
        OAuthApp(client_id=app.client_id, client_secret=app.client_secret, redirect_uri=redirect)


@pytest.mark.parametrize(
    "local,expected",
    [
        ("2026-11-10T02:30:00+05:30", "2026-11-10T03:30:00+05:30"),
        ("2026-11-10T03:30:00+05:30", "2026-11-11T03:30:00+05:30"),
        ("2026-11-10T20:00:00+05:30", "2026-11-11T03:30:00+05:30"),
    ],
)
def test_documented_daily_cutoff_including_before_dawn(local, expected):
    assert daily_cutoff(datetime.fromisoformat(local)).astimezone(IST).isoformat() == expected


def test_fixed_token_exchange_discards_profile_and_keeps_secrets_out_of_repr(app, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid-proxy.example")
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == TOKEN_URL and request.method == "POST"
        assert "authorization" not in request.headers
        assert parse_qs(request.content.decode()) == {
            "code": [CODE.get_secret_value()],
            "client_id": [app.client_id],
            "client_secret": [app.client_secret.get_secret_value()],
            "redirect_uri": [app.redirect_uri],
            "grant_type": ["authorization_code"],
        }
        return httpx.Response(
            200,
            json={
                "access_token": BEARER,
                "email": "synthetic-private-profile",
                "extended_token": "discard-me",
            },
        )

    states, _, state = begin(app)
    token = asyncio.run(
        UpstoxOAuth(transport=httpx.MockTransport(handler), clock=lambda: NOW).complete(
            app, states, state, SESSION, CODE
        )
    )
    assert len(requests) == 1 and token.access_token.get_secret_value() == BEARER
    assert token.requested_at == NOW and token.received_at == NOW
    assert token.expires_at == daily_cutoff(NOW)
    assert BEARER not in repr(token) and "synthetic-private-profile" not in repr(token)
    assert not hasattr(token, "extended_token")


@pytest.mark.parametrize(
    "status,code",
    [
        (302, "REDIRECT_REJECTED"),
        (400, "TOKEN_REQUEST_REJECTED"),
        (401, "TOKEN_REQUEST_REJECTED"),
        (429, "RATE_LIMITED"),
        (503, "TOKEN_SERVICE_UNAVAILABLE"),
    ],
)
def test_failed_exchange_has_no_retry_no_remote_error_echo_and_no_replay(app, status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://evil.example"}, json={"error": BEARER}
        )

    client = UpstoxOAuth(transport=httpx.MockTransport(handler), clock=lambda: NOW)
    states, _, state = begin(app)
    with pytest.raises(OAuthError, match=code) as error:
        asyncio.run(client.complete(app, states, state, SESSION, CODE))
    assert BEARER not in str(error.value) and len(calls) == 1
    with pytest.raises(OAuthError, match="STATE_INVALID"):
        asyncio.run(client.complete(app, states, state, SESSION, CODE))
    assert len(calls) == 1


@pytest.mark.parametrize(
    "body,headers",
    [
        (b'{"access_token":"first","access_token":"second"}', {}),
        (b'{"access_token":"invalid\\nvalue"}', {}),
        (b"{}", {}),
        (b"[]", {}),
        (b"not-json", {}),
        (b"{}", {"content-type": "text/html"}),
        (b"{}", {"content-encoding": "gzip"}),
        (b"x" * (MAX_RESPONSE_BYTES + 1), {}),
    ],
)
def test_malformed_compressed_duplicate_or_oversized_token_responses_fail_closed(
    app, body, headers
):
    # Unknown encodings are rejected before any untrusted decompression.
    headers = {"content-type": "application/json", **headers}

    def handler(request):
        # A stream prevents httpx from pre-decoding compressed fixture bytes.
        return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))

    states, _, state = begin(app)
    with pytest.raises(OAuthError):
        asyncio.run(
            UpstoxOAuth(transport=httpx.MockTransport(handler), clock=lambda: NOW).complete(
                app, states, state, SESSION, CODE
            )
        )


def test_exchange_cannot_outlive_session_or_daily_cutoff(app):
    for start, end in [
        (NOW, NOW + timedelta(minutes=6)),
        (datetime(2026, 11, 10, 21, 59, 59, tzinfo=UTC), datetime(2026, 11, 10, 22, 0, tzinfo=UTC)),
    ]:
        clock = iter([start, end])
        states, _, state = begin(app, now=start)
        client = UpstoxOAuth(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json={"access_token": BEARER})
            ),
            clock=lambda clock=clock: next(clock),
        )
        with pytest.raises(OAuthError, match="EXPIRED_DURING_EXCHANGE"):
            asyncio.run(client.complete(app, states, state, SESSION, CODE))


@pytest.mark.parametrize("kind", ["expired-session", "invalid-session", "naive-clock"])
def test_begin_requires_current_aware_authenticated_session_binding(app, kind):
    states = OAuthStates()
    with pytest.raises(OAuthError):
        states.begin(
            app,
            "raw-session-cookie-not-a-digest" if kind == "invalid-session" else SESSION,
            NOW - timedelta(seconds=1)
            if kind == "expired-session"
            else NOW + timedelta(minutes=15),
            now=NOW.replace(tzinfo=None) if kind == "naive-clock" else NOW,
        )
    assert not states._pending


@pytest.mark.parametrize("raw", ["", "bad\ncode", "x" * 8193])
def test_invalid_code_burns_state_without_any_network_request(app, raw):
    calls = []
    client = UpstoxOAuth(
        transport=httpx.MockTransport(lambda r: calls.append(r)), clock=lambda: NOW
    )
    states, _, state = begin(app)
    with pytest.raises(OAuthError, match="CODE_INVALID"):
        asyncio.run(client.complete(app, states, state, SESSION, SecretStr(raw)))
    with pytest.raises(OAuthError, match="STATE_INVALID"):
        asyncio.run(client.complete(app, states, state, SESSION, CODE))
    assert not calls


def test_network_error_is_fixed_safe_single_attempt_without_secret_echo(app):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError(BEARER, request=request)

    states, _, state = begin(app)
    with pytest.raises(OAuthError, match="^OAUTH_TOKEN_SERVICE_UNAVAILABLE$") as error:
        asyncio.run(
            UpstoxOAuth(transport=httpx.MockTransport(handler), clock=lambda: NOW).complete(
                app, states, state, SESSION, CODE
            )
        )
    assert BEARER not in str(error.value) and len(calls) == 1


@pytest.mark.parametrize("kind", ["missing", "partial", "invalid", "complete"])
def test_optional_settings_validation_never_replaces_analytics_or_echoes_secrets(app, kind):
    import json

    from backend.app.brokers.oauth import configuration_status, configured_app
    from backend.app.config import Settings

    settings = Settings(_env_file=None, app_env="test", database_url="sqlite://")
    if kind != "missing":
        settings = settings.model_copy(update={"upstox_client_id": app.client_id})
    if kind in {"invalid", "complete"}:
        settings = settings.model_copy(
            update={
                "upstox_client_secret": app.client_secret,
                "upstox_redirect_uri": app.redirect_uri
                if kind == "complete"
                else "http://remote.example/callback",
            }
        )
    original = settings.upstox_analytics_token
    status = configuration_status(settings)
    assert (
        status["state"]
        == {
            "missing": "NOT_CONFIGURED",
            "partial": "INCOMPLETE",
            "invalid": "INVALID",
            "complete": "CONFIGURED_OPERATOR_DECLARED",
        }[kind]
    )
    text = json.dumps(status)
    assert app.client_secret.get_secret_value() not in text and app.client_id not in text
    assert (
        not status["registration_verified"]
        and status["tokens_stored"] is None
        and status["token_storage_checked"] is False
        and status["browser_flow_implemented"] is True
        and not status["live_enabled"]
    )
    assert settings.upstox_analytics_token is original
    if kind == "complete":
        assert configured_app(settings) == app
    else:
        with pytest.raises(OAuthError):
            configured_app(settings)
