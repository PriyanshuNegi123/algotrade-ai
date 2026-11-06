"""Explicit host-side chain capture; credentials only from protected environment."""

import argparse
import asyncio
import json
from datetime import date

from backend.app.brokers.upstox import BrokerError, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.option_chain import (
    ChainError,
    archive_chain,
    resolve_chain,
    validate_chain,
)
from backend.app.market_data.option_contracts import ChainRequest


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying-key", required=True)
    parser.add_argument("--expiry-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    request = ChainRequest(underlying_key=args.underlying_key, expiry_date=args.expiry_date)
    settings = Settings()
    engine = build_engine(settings)
    try:
        context = resolve_chain(engine, request)
        payload = await ReadOnlyUpstox(settings).option_chain(request)
        result = archive_chain(engine, request, validate_chain(request, payload, context), context)
        print(json.dumps(result, default=str))
    except (BrokerError, ChainError) as error:
        raise SystemExit(f"Option-chain capture rejected: {error}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
