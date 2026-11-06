"""Explicit host-side historical import; credentials come only from server environment."""

import argparse
import asyncio
import json
from datetime import date

from backend.app.brokers.upstox import BrokerError, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.contracts import CandleRequest
from backend.app.market_data.history import (
    CandleError,
    archive_candles,
    resolve_instrument,
    validate_history,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", required=True)
    parser.add_argument("--interval", type=int, choices=[1, 5, 15], default=1)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    request = CandleRequest(
        instrument_key=args.instrument_key,
        interval=args.interval,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    settings = Settings()
    engine = build_engine(settings)
    try:
        metadata = resolve_instrument(engine, request)
        payload = await ReadOnlyUpstox(settings).historical_candles(request)
        result = archive_candles(engine, request, validate_history(request, payload), metadata)
        print(json.dumps(result, default=str))
    except (BrokerError, CandleError) as error:
        raise SystemExit(f"History import rejected: {error}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
