import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from backend.app.brokers import oauth_probe as probe
from backend.app.brokers.oauth import OAuthToken, configured_app, daily_cutoff
from backend.app.brokers.oauth_store import OAuthTokenStore
from backend.app.config import Settings

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
TOKEN = "synthetic-quarantined-oauth-bearer"


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(probe, "utc_now", lambda: NOW)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite://",
        trading_mode="OBSERVATION",
        live_enabled=False,
        upstox_client_id="synthetic-probe-client",
        upstox_client_secret=SecretStr("synthetic-probe-private-value"),
        upstox_redirect_uri="http://127.0.0.1:8000/auth/upstox/callback",
        upstox_oauth_vault_dir=str(tmp_path / "vault"),
        upstox_analytics_token=SecretStr("synthetic-unchanged-analytics"),
        upstox_analytics_expires_at=NOW + timedelta(days=365),
    )
    store = OAuthTokenStore(tmp_path / "vault", clock=lambda: NOW)
    store.save(configured_app(settings), OAuthToken(SecretStr(TOKEN), NOW, NOW, daily_cutoff(NOW)))
    return settings, store


def payload(**changes):
    return {
        "status": "success",
        "data": {
            "exchange": "NSE",
            "status": "NORMAL_CLOSE",
            "last_updated": int(NOW.timestamp() * 1000),
            **changes,
        },
    }


def run(context, response):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and str(request.url) == probe.STATUS_URL
        assert request.headers["authorization"] == "Bearer " + TOKEN
        assert request.headers["accept-encoding"] == "identity"
        return response

    result = asyncio.run(
        probe.check_oauth_access(context[0], transport=httpx.MockTransport(handler))
    )
    assert len(requests) == 1
    assert TOKEN not in result.model_dump_json()
    return result


def test_success_is_endpoint_only_and_preserves_vault_and_analytics(context):
    settings, store = context
    before = {p.name: p.read_bytes() for p in store._directory.iterdir()}
    result = run(context, httpx.Response(200, json=payload(profile="synthetic-private-profile")))
    assert result.state == "CHECKED" and result.endpoint_response_verified
    assert result.market_status == "NORMAL_CLOSE"
    assert not result.account_permissions_verified and not result.credential_promoted
    assert not result.live_enabled and not result.entries_enabled and not result.recording_started
    assert "synthetic-private-profile" not in result.model_dump_json()
    assert before == {p.name: p.read_bytes() for p in store._directory.iterdir()}
    assert settings.upstox_analytics_token.get_secret_value() == "synthetic-unchanged-analytics"


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (401, "AUTH_REQUIRED"),
        (403, "ACCESS_DENIED"),
        (429, "RATE_LIMITED"),
        (500, "UNAVAILABLE"),
        (302, "UNAVAILABLE"),
    ],
)
def test_status_failures_never_retry_or_follow_redirect(context, status, state):
    result = run(
        context,
        httpx.Response(
            status,
            headers={"location": "https://untrusted.invalid/"},
            text="synthetic-private-response",
        ),
    )
    assert result.state == state and not result.endpoint_response_verified
    assert "synthetic-private-response" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", 1), ("9999", 3600), ("-1", 60), ("999999", 60), ("١", 60), ("nonsense", 60)],
)
def test_retry_after_is_bounded_and_never_automatically_retried(context, value, expected):
    # Headers are bytes because httpx's string-header constructor forbids non-ASCII.
    result = run(context, httpx.Response(429, headers=[(b"retry-after", value.encode())]))
    assert result.retry_after == expected


@pytest.mark.parametrize(
    "headers",
    [
        {"content-type": "text/html"},
        {"content-type": "application/json", "content-encoding": "gzip"},
        {"content-type": "application/json", "content-length": "65537"},
        {"content-type": "application/json", "content-length": "-1"},
        {"content-type": "application/json", "content-length": "unknown"},
    ],
)
def test_unsafe_media_and_length_rejected(context, headers):
    response = httpx.Response(200, headers=headers, stream=httpx.ByteStream(b"{}"))
    assert run(context, response).state == "INVALID_RESPONSE"


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"status":"success","status":"success","data":{}}',
        json.dumps(payload(status="UNKNOWN")).encode(),
        json.dumps(payload(exchange="OTHER")).encode(),
        json.dumps(payload(last_updated=True)).encode(),
        json.dumps(
            payload(last_updated=int((NOW + timedelta(hours=1)).timestamp() * 1000))
        ).encode(),
        b"[" * 2000 + b"0" + b"]" * 2000,
    ],
)
def test_malformed_ambiguous_or_future_response_is_not_verified(context, body):
    assert (
        run(
            context, httpx.Response(200, headers={"content-type": "application/json"}, content=body)
        ).state
        == "INVALID_RESPONSE"
    )


@pytest.mark.parametrize("extra", [0, 1])
def test_streaming_response_limit_and_cleanup(context, extra):
    data = json.dumps(payload()).encode()
    data += b" " * (probe.MAX_RESPONSE_BYTES - len(data) + extra)

    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            for start in range(0, len(data), 8192):
                yield data[start : start + 8192]

        async def aclose(self):
            self.closed = True

    stream = Stream()
    result = run(
        context, httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)
    )
    assert result.state == ("CHECKED" if extra == 0 else "INVALID_RESPONSE")
    assert stream.closed


@pytest.mark.parametrize(
    "kind", ["missing-config", "missing-vault", "relative-vault", "expired", "paper"]
)
def test_local_gates_send_no_broker_request(context, monkeypatch, kind):
    settings, store = context
    if kind == "missing-config":
        settings = settings.model_copy(update={"upstox_client_id": ""})
    elif kind == "missing-vault":
        settings = settings.model_copy(update={"upstox_oauth_vault_dir": ""})
    elif kind == "relative-vault":
        settings = settings.model_copy(update={"upstox_oauth_vault_dir": "relative"})
    elif kind == "expired":
        monkeypatch.setattr(probe, "utc_now", lambda: daily_cutoff(NOW))
    elif kind == "paper":
        settings = settings.model_copy(update={"trading_mode": "PAPER"})

    def blocked(_):
        raise AssertionError("Broker request must not run")

    result = asyncio.run(probe.check_oauth_access(settings, transport=httpx.MockTransport(blocked)))
    assert not result.endpoint_response_verified and result.state != "CHECKED"


def test_network_error_is_safe_and_not_retried(context, caplog):
    calls = []

    def failed(request):
        calls.append(request)
        raise httpx.ConnectError(TOKEN + " synthetic network failure")

    result = asyncio.run(
        probe.check_oauth_access(context[0], transport=httpx.MockTransport(failed))
    )
    assert result.state == "UNAVAILABLE" and len(calls) == 1
    assert TOKEN not in caplog.text and TOKEN not in result.model_dump_json()


def test_total_timeout_cancels_without_retry(context, monkeypatch):
    original = asyncio.timeout
    monkeypatch.setattr(probe.asyncio, "timeout", lambda _: original(0.01))
    calls = []

    async def stalled(request):
        calls.append(request)
        await asyncio.sleep(10)

    result = asyncio.run(
        probe.check_oauth_access(context[0], transport=httpx.MockTransport(stalled))
    )
    assert result.state == "UNAVAILABLE" and len(calls) == 1


def test_expiry_during_request_never_returns_checked(context, monkeypatch):
    def handler(_):
        monkeypatch.setattr(probe, "utc_now", lambda: daily_cutoff(NOW))
        return httpx.Response(200, json=payload())

    result = asyncio.run(
        probe.check_oauth_access(context[0], transport=httpx.MockTransport(handler))
    )
    assert result.state == "REAUTHORIZE_REQUIRED" and not result.endpoint_response_verified


def test_cli_rejects_secret_like_arguments_without_echo(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["oauth_probe", "synthetic-private-argument"])
    assert probe.main() == 2
    assert "synthetic-private-argument" not in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["corrupt", "unsafe-mode", "missing-token"])
def test_unsafe_or_missing_storage_cannot_send_request(context, kind):
    settings, store = context
    path = store._directory / "token.enc"
    if kind == "corrupt":
        path.write_bytes(b"synthetic-corrupt-ciphertext")
    elif kind == "unsafe-mode":
        path.chmod(0o644)
    else:
        path.unlink()

    def forbidden(_):
        raise AssertionError("Broker request must not run")

    result = asyncio.run(
        probe.check_oauth_access(settings, transport=httpx.MockTransport(forbidden))
    )
    assert result.state == "LOCAL_STORAGE_UNAVAILABLE"


def test_client_disables_proxy_environment_and_redirects(context, monkeypatch):
    original = httpx.AsyncClient
    seen = []

    def client(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(probe.httpx, "AsyncClient", client)
    assert run(context, httpx.Response(200, json=payload())).state == "CHECKED"
    assert len(seen) == 1
    assert seen[0]["trust_env"] is False and seen[0]["follow_redirects"] is False
    assert seen[0]["timeout"].read == 5
