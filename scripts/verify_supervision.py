"""Real loopback TLS plus durable synthetic multi-session supervision. Never dials a broker."""

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from websockets.asyncio.server import serve

from backend.app.brokers import feed_transport
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.instruments.service import archive, prepare
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.feed_lifecycle import LifecyclePolicy
from backend.app.market_data.supervision_store import CapturePolicy
from backend.app.market_data.supervisor import CaptureSupervisor
from backend.vendor.upstox import MarketDataFeed_pb2 as pb
from scripts import verify_feed_transport as transport_check
from tests.chain_fixtures import chain_metadata

KEY = "NSE_INDEX|Synthetic index"
original_exercise = transport_check.exercise


async def exercise(server_ssl, client_ssl):
    await original_exercise(server_ssl, client_ssl)
    with tempfile.TemporaryDirectory(prefix="algotrade-supervision-verify-") as temporary:
        url = "sqlite:///" + str(Path(temporary) / "verify.db")
        with patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": url}):
            command.upgrade(Config("alembic.ini"), "head")
        engine = build_engine(Settings(_env_file=None, app_env="test", database_url=url))
        try:
            archive(engine, prepare(chain_metadata()))

            async def handler(socket):
                request = await socket.recv()
                assert isinstance(request, bytes) and json.loads(request)["data"][
                    "instrumentKeys"
                ] == [KEY]
                status = pb.FeedResponse(
                    type=pb.market_info, currentTs=int(datetime.now(UTC).timestamp() * 1000)
                )
                status.marketInfo.segmentStatus["NSE_INDEX"] = pb.NORMAL_OPEN
                await socket.send(status.SerializeToString())
                data = pb.FeedResponse(
                    type=pb.live_feed, currentTs=int(datetime.now(UTC).timestamp() * 1000)
                )
                data.feeds[KEY].ltpc.CopyFrom(pb.LTPC(ltp=100, cp=99, ltt=data.currentTs, ltq=1))
                await socket.send(data.SerializeToString())
                await socket.wait_closed()

            async def no_wait(delay):
                assert delay == 30  # Verification skips real waiting, production does not.

            logger = logging.Logger("verification.silent")
            logger.disabled = True
            original = feed_transport.NoRedirectConnect
            async with serve(handler, "127.0.0.1", 0, ssl=server_ssl, logger=logger) as server:
                port = server.sockets[0].getsockname()[1]

                class LoopbackConnect(original):
                    def __init__(self, uri, **options):
                        super().__init__(
                            uri, **options, ssl=client_ssl, host="127.0.0.1", port=port
                        )

                with patch.object(feed_transport, "NoRedirectConnect", LoopbackConnect):
                    supervisor = CaptureSupervisor(
                        engine,
                        FeedRequest(instrument_keys=(KEY,)),
                        transport_check.SyntheticAuthorizer(),
                        source="SYNTHETIC",
                        policy=CapturePolicy(total_seconds=10, session_seconds=2, max_sessions=2),
                        sleep=no_wait,
                        child_policy=LifecyclePolicy(max_frames=2, max_attempts=1),
                    )
                    result = await supervisor.run()
                assert result["capture"]["reason"] == "SESSION_LIMIT", result
                assert result["capture"]["event_count"] == 6
                assert result["capture"]["stats"]["snapshots"] == 2
                assert len(result["sessions"]) == 2 and all(
                    child["status"] == "CLOSED" for child in result["sessions"]
                )
                assert result["capture"]["payload_bytes"] == sum(
                    child["payload_bytes"] for child in result["sessions"]
                )
                assert (
                    result["capture"]["source"] == "SYNTHETIC"
                    and not result["capture"]["live_enabled"]
                )
        finally:
            engine.dispose()
    print(
        "Supervision TLS checks passed: two durable synthetic sessions, parent quotas/health, "
        "fresh subscriptions and closure; temporary database removed."
    )


if __name__ == "__main__":
    with patch.object(transport_check, "exercise", exercise):
        transport_check.main()
