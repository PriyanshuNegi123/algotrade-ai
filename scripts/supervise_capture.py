"""Explicit bounded multi-session research capture; no auto-start or live execution."""

import argparse
import asyncio
import json
import signal

from backend.app.brokers.upstox import ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.preflight import capture_preflight
from backend.app.market_data.supervision_store import CapturePolicy
from backend.app.market_data.supervisor import CaptureSupervisor


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--total-seconds", type=int, default=600)
    parser.add_argument("--session-seconds", type=int, default=300)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-payload-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--max-events", type=int, default=20_000)
    args = parser.parse_args()
    request = FeedRequest(instrument_keys=tuple(args.instrument_key))
    policy = CapturePolicy(
        total_seconds=args.total_seconds,
        session_seconds=args.session_seconds,
        max_sessions=args.max_sessions,
        max_payload_bytes=args.max_payload_bytes,
        max_events=args.max_events,
    )
    settings = Settings()
    engine = build_engine(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    try:
        report = await asyncio.to_thread(capture_preflight, engine, settings, request, policy)
        if args.preflight_only or not report["can_attempt_capture"]:
            print(json.dumps(report, default=str), flush=True)
            if not report["can_attempt_capture"]:
                raise SystemExit(2)
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
            installed.append(sig)
        supervisor = CaptureSupervisor(
            engine, request, ReadOnlyUpstox(settings), policy=policy, stop=stop
        )
        print(json.dumps(await supervisor.run(), default=str), flush=True)
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)
        engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise SystemExit("Capture supervision stopped") from None
    except Exception:
        raise SystemExit(
            "Capture supervision failed; inspect local configuration and database readiness"
        ) from None
