"""Synthetic protocol fixtures only; no recorded account data or live HTTP calls."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.app.api.broker import get_monitor
from backend.app.brokers.upstox import BrokerError, BrokerMonitor, ReadOnlyUpstox
from backend.app.config import Settings
from tests.conftest import ORIGIN, PASSWORD

TOKEN = "synthetic-analytics-test-credential"


def configured(**changes):
    values = {
        "upstox_analytics_token": TOKEN,
        "upstox_analytics_expires_at": datetime.now(UTC) + timedelta(hours=1),
        **changes,
    }
    return Settings(_env_file=None, **values)


def payload():
    return {
        "status": "success",
        "data": {
            "exchange": "NSE",
            "status": "NORMAL_OPEN",
            "last_updated": int(datetime.now(UTC).timestamp() * 1000),
        },
    }


def test_fixed_get_endpoint_and_filtered_success():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api.upstox.com/v2/market/status/NSE"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        body = payload()
        body["data"]["untrusted_extra"] = TOKEN
        return httpx.Response(200, json=body)

    monitor = BrokerMonitor(ReadOnlyUpstox(configured(), httpx.MockTransport(handler)))
    result = asyncio.run(monitor.check())
    assert result.state == "CHECKED"
    assert result.entries_enabled is False and result.live_enabled is False
    assert result.checked_at.tzinfo is not None
    assert TOKEN not in result.model_dump_json()
    assert "untrusted_extra" not in result.model_dump_json()
    assert len(requests) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "AUTH_REQUIRED"),
        (403, "ACCESS_DENIED"),
        (429, "RATE_LIMITED"),
        (500, "UNAVAILABLE"),
        (302, "UNAVAILABLE"),
    ],
)
def test_broker_errors_do_not_leak_body_or_follow_redirects(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            text=TOKEN,
            headers={
                "Location": "https://untrusted.example/collect",
                "Retry-After": "120",
            },
        )

    monitor = BrokerMonitor(ReadOnlyUpstox(configured(), httpx.MockTransport(handler)))
    with pytest.raises(BrokerError) as error:
        asyncio.run(monitor.check())
    assert error.value.code == code
    assert TOKEN not in str(error.value)
    assert len(calls) == 1
    assert monitor.snapshot().state == code
    assert monitor.snapshot().exchange is None
    if status == 429:
        assert error.value.retry_after == 120


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"status": "error", "data": {}},
        {
            "status": "success",
            "data": {"exchange": "BSE", "status": "NORMAL_OPEN", "last_updated": 1},
        },
        {"status": "success", "data": {"exchange": "NSE", "status": "invented", "last_updated": 1}},
        {
            "status": "success",
            "data": {"exchange": "NSE", "status": "NORMAL_OPEN", "last_updated": True},
        },
        {
            "status": "success",
            "data": {
                "exchange": "NSE",
                "status": "NORMAL_OPEN",
                "last_updated": 999999999999999999,
            },
        },
    ],
)
def test_malformed_or_unsupported_schema_rejected(bad):
    adapter = ReadOnlyUpstox(
        configured(), httpx.MockTransport(lambda _: httpx.Response(200, json=bad))
    )
    with pytest.raises(BrokerError, match="INVALID_RESPONSE"):
        asyncio.run(adapter.exchange_status())


@pytest.mark.parametrize(
    "body,media",
    [
        (b"not-json", "application/json"),
        (b"{}", "text/html"),
        (b"x" * 70_000, "application/json"),
    ],
)
def test_invalid_media_json_and_oversized_responses_rejected(body, media):
    adapter = ReadOnlyUpstox(
        configured(),
        httpx.MockTransport(
            lambda _: httpx.Response(200, content=body, headers={"Content-Type": media})
        ),
    )
    with pytest.raises(BrokerError, match="INVALID_RESPONSE"):
        asyncio.run(adapter.exchange_status())


def test_future_exchange_timestamp_rejected():
    body = payload()
    body["data"]["last_updated"] = int((datetime.now(UTC) + timedelta(hours=1)).timestamp() * 1000)
    adapter = ReadOnlyUpstox(
        configured(), httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    )
    with pytest.raises(BrokerError, match="INVALID_RESPONSE"):
        asyncio.run(adapter.exchange_status())


def test_timeout_does_not_retry():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(TOKEN, request=request)

    adapter = ReadOnlyUpstox(configured(), httpx.MockTransport(handler))
    with pytest.raises(BrokerError, match="UNAVAILABLE") as error:
        asyncio.run(adapter.exchange_status())
    assert TOKEN not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("credential_state", ["NOT_CONFIGURED", "EXPIRED"])
def test_missing_or_expired_credential_never_contacts_broker(credential_state):
    settings = (
        Settings(_env_file=None)
        if credential_state == "NOT_CONFIGURED"
        else configured(upstox_analytics_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    def forbidden(_):
        pytest.fail("Missing/expired credentials must never produce an HTTP request")

    monitor = BrokerMonitor(ReadOnlyUpstox(settings, httpx.MockTransport(forbidden)))
    assert asyncio.run(monitor.check()).state == credential_state


def test_concurrent_probes_are_serialized_and_throttled():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    async def run():
        monitor = BrokerMonitor(ReadOnlyUpstox(configured(), httpx.MockTransport(handler)))
        return await asyncio.gather(*(monitor.check() for _ in range(4)), return_exceptions=True)

    results = asyncio.run(run())
    assert len(calls) == 1
    assert sum(isinstance(result, BrokerError) for result in results) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"upstox_analytics_token": TOKEN},
        {"upstox_analytics_expires_at": "2027-01-01T00:00:00Z"},
        {"upstox_analytics_token": TOKEN, "upstox_analytics_expires_at": "2027-01-01"},
        {
            "upstox_analytics_token": "unsafe\r\nheader",
            "upstox_analytics_expires_at": "2027-01-01T00:00:00Z",
        },
    ],
)
def test_credential_configuration_fails_closed_without_secret_echo(changes):
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **changes)
    assert "unsafe" not in str(error.value)
    assert TOKEN not in str(error.value)


def test_private_broker_routes_and_csrf(client):
    assert client.get("/api/broker/status").status_code == 401
    assert client.post("/api/broker/check").status_code == 401
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert client.get("/api/broker/status").json()["state"] == "NOT_CONFIGURED"
    assert client.post("/api/broker/check", headers=ORIGIN).status_code == 403
    csrf = login.json()["csrf_token"]
    response = client.post("/api/broker/check", headers={**ORIGIN, "X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json()["state"] == "NOT_CONFIGURED"
    assert response.json()["entries_enabled"] is False


def test_admin_probe_uses_injected_mock_and_never_exposes_credential(client):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    monitor = BrokerMonitor(ReadOnlyUpstox(configured(), httpx.MockTransport(handler)))
    client.app.dependency_overrides[get_monitor] = lambda: monitor
    login = client.post("/api/auth/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert client.get("/api/broker/status").json()["state"] == "UNVERIFIED"
    assert calls == []
    headers = {**ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]}
    response = client.post("/api/broker/check", headers=headers)
    assert response.status_code == 200
    assert response.json()["state"] == "CHECKED"
    assert TOKEN not in response.text
    limited = client.post("/api/broker/check", headers=headers)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
    assert len(calls) == 1


def test_secret_is_masked_in_settings_representation():
    assert TOKEN not in repr(configured())
    assert TOKEN not in repr(SecretStr(TOKEN))


def test_compressed_response_rejected_before_streaming_body():
    import gzip
    import json

    def handler(request):
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200,
            content=gzip.compress(json.dumps(payload()).encode()),
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
        )

    adapter = ReadOnlyUpstox(configured(), httpx.MockTransport(handler))
    with pytest.raises(BrokerError, match="INVALID_RESPONSE"):
        asyncio.run(adapter.exchange_status())
