"""Verify real TLS/WebSocket framing on loopback with synthetic grants and ephemeral certs."""

import asyncio
import json
import logging
import ssl
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from backend.app.brokers import feed_transport
from backend.app.brokers.feed_authorization import parse_grant
from backend.app.market_data.feed import FeedPlan
from backend.app.market_data.feed_lifecycle import FeedRunner, LifecyclePolicy
from backend.vendor.upstox import MarketDataFeed_pb2 as pb

KEY = "NSE_INDEX|Synthetic verification"
URL = (
    "wss://feed.upstox.com/market-data-feeder/v3/upstox-developer-api/feeds"
    "?requestId=11111111-1111-1111-1111-111111111111&code=22222222-2222-2222-2222-222222222222"
)


class SyntheticAuthorizer:
    def credential_state(self):
        return "UNVERIFIED"

    async def authorize_feed(self):
        return parse_grant(
            json.dumps(
                {
                    "status": "success",
                    "data": {"authorized_redirect_uri": URL},
                }
            ).encode()
        )


async def exercise(server_ssl, client_ssl):
    logger = logging.Logger("verification.silent")
    logger.disabled = True
    events = []
    pong_seen = asyncio.Event()

    async def handler(socket):
        subscription = await socket.recv()
        assert isinstance(subscription, bytes)
        assert json.loads(subscription)["data"] == {"mode": "ltpc", "instrumentKeys": [KEY]}
        status = pb.FeedResponse(
            type=pb.market_info, currentTs=int(datetime.now(UTC).timestamp() * 1000)
        )
        status.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_OPEN
        await socket.send(status.SerializeToString())
        data = pb.FeedResponse(
            type=pb.live_feed, currentTs=int(datetime.now(UTC).timestamp() * 1000)
        )
        data.feeds[KEY].ltpc.CopyFrom(pb.LTPC(ltp=100, cp=99, ltt=data.currentTs, ltq=1))
        pong = await socket.ping()
        await asyncio.wait_for(pong, 1)
        pong_seen.set()
        await socket.send(data.SerializeToString())
        await socket.wait_closed()

    async def load():
        return FeedPlan("a" * 64, (KEY,))

    async def sink(event):
        events.append(event)

    original = feed_transport.NoRedirectConnect
    async with serve(handler, "127.0.0.1", 0, ssl=server_ssl, logger=logger) as server:
        port = server.sockets[0].getsockname()[1]

        class LoopbackConnect(original):
            def __init__(self, uri, **options):
                super().__init__(uri, **options, ssl=client_ssl, host="127.0.0.1", port=port)

        with patch.object(feed_transport, "NoRedirectConnect", LoopbackConnect):
            runner = FeedRunner(
                SyntheticAuthorizer(),
                load,
                sink,
                policy=LifecyclePolicy(max_frames=2, max_attempts=1),
            )
            result = await runner.run()
            assert result["reason"] == "FRAME_LIMIT", result
            await asyncio.wait_for(pong_seen.wait(), 1)
        assert result["reason"] == "FRAME_LIMIT", result
        assert [event.kind for event in events] == ["PLAN", "MARKET_INFO", "SNAPSHOT"]
        assert events[-1].observations[0].freshness == "RECENT_TRADE"
        assert not result["live_enabled"]
    # A real 302 handshake must never cause a second dial or expose Location in the result.
    redirect_calls = []

    async def redirect(connection, request):
        redirect_calls.append(1)
        return Response(302, "Found", Headers({"Location": URL}), b"")

    async with serve(
        handler, "127.0.0.1", 0, ssl=server_ssl, logger=logger, process_request=redirect
    ) as server:
        port = server.sockets[0].getsockname()[1]
        with patch.object(feed_transport, "NoRedirectConnect", LoopbackConnect):
            result = await FeedRunner(
                SyntheticAuthorizer(), load, sink, policy=LifecyclePolicy(max_attempts=1)
            ).run()
        assert result["reason"] == "FEED_REDIRECT_BLOCKED" and redirect_calls == [1], result
        assert URL not in json.dumps(result)
    print(
        "Loopback TLS checks passed: binary subscribe, Protobuf ordering, server ping/client pong, "
        "bounded close, real redirect rejection; no broker request."
    )


def main():
    with tempfile.TemporaryDirectory(prefix="algotrade-feed-verify-") as temporary:
        directory = Path(temporary)
        config = directory / "cert.cnf"
        config.write_text(
            "[req]\ndistinguished_name=dn\nx509_extensions=extensions\nprompt=no\n"
            "[dn]\nCN=feed.upstox.com\n[extensions]\nsubjectAltName=DNS:feed.upstox.com\n"
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-keyout",
                str(directory / "key.pem"),
                "-out",
                str(directory / "cert.pem"),
                "-config",
                str(config),
            ],
            check=True,
            capture_output=True,
        )
        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.load_cert_chain(directory / "cert.pem", directory / "key.pem")
        client_ssl = ssl.create_default_context(cafile=str(directory / "cert.pem"))
        asyncio.run(exercise(server_ssl, client_ssl))
    print("Ephemeral certificates and loopback servers removed.")


if __name__ == "__main__":
    main()
