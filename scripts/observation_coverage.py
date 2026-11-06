"""Read-only bounded NSE derivatives sampled-coverage report from stored observations."""

import argparse
import json
from datetime import date

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.coverage import CoverageRequest, coverage_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--source", choices=("UPSTOX_V3", "SYNTHETIC"), default="UPSTOX_V3")
    args = parser.parse_args()
    request = CoverageRequest(
        from_date=args.from_date,
        to_date=args.to_date,
        instrument_keys=tuple(args.instrument_key),
        source=args.source,
    )
    engine = build_engine(Settings())
    try:
        print(json.dumps(coverage_report(engine, request), default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Coverage report unavailable; check range, keys, schema and source evidence"
        ) from None
