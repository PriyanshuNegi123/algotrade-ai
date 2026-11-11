"""Both TestClient and broker-client default transports remain network-isolated."""

import importlib

import pytest


@pytest.mark.parametrize("library", ["httpx", "httpx2"])
def test_real_sync_http_transport_is_denied(library):
    client_module = importlib.import_module(library)
    with client_module.Client() as client:
        with pytest.raises(AssertionError, match="Real outbound HTTP is forbidden"):
            client.get("https://invalid.example/")


@pytest.mark.parametrize("library", ["httpx", "httpx2"])
def test_real_async_http_transport_is_denied(library):
    import asyncio

    client_module = importlib.import_module(library)

    async def request():
        async with client_module.AsyncClient() as client:
            with pytest.raises(AssertionError, match="Real outbound HTTP is forbidden"):
                await client.get("https://invalid.example/")

    asyncio.run(request())
