"""Explicit bounded LTPC research session; durable research events, no signals or orders."""

import argparse
import asyncio
import json
from dataclasses import asdict

from backend.app.brokers.upstox import ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.feed import FeedRequest, resolve_feed
from backend.app.market_data.feed_lifecycle import FeedEvent, FeedRunner, LifecyclePolicy
from backend.app.market_data.observations import ObservationWriter, recover_abandoned, start_session


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--duration", type=int, default=60, choices=range(1, 301), metavar="1..300")
    args = parser.parse_args()
    request = FeedRequest(instrument_keys=tuple(args.instrument_key))
    settings = Settings()
    engine = build_engine(settings)

    policy = LifecyclePolicy(duration_seconds=args.duration)
    await asyncio.to_thread(recover_abandoned, engine)
    identity = await asyncio.to_thread(start_session, engine, request, policy, "UPSTOX_V3")
    writer = ObservationWriter(engine, identity)
    print(json.dumps({"observation_session_id": identity}), flush=True)

    async def plan_loader():
        return await asyncio.to_thread(resolve_feed, engine, request)

    async def output(event: FeedEvent):
        await writer.append(event)
        # Only allowlisted normalized events. Never print raw frames, grants or exceptions.
        print(json.dumps(asdict(event), default=str), flush=True)

    try:
        runner = FeedRunner(
            ReadOnlyUpstox(settings),
            plan_loader,
            output,
            policy=policy,
        )
        try:
            result = await runner.run()
        except asyncio.CancelledError:
            await writer.finish("CANCELLED", runner.elapsed_ms())
            raise
        else:
            await writer.finish(str(result["reason"]), int(result["run_elapsed_ms"]))
            print(json.dumps({"observation_session_id": identity, **result}), flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        raise SystemExit("Feed session stopped") from None
    except Exception:
        raise SystemExit(
            "Feed recording failed; inspect database readiness and protected local configuration"
        ) from None
