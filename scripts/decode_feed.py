"""Decode an operator-supplied V3 LTPC binary frame offline against the local catalog."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.feed import (
    MAX_FRAME_BYTES,
    FeedError,
    FeedRequest,
    decode_frame,
    resolve_feed,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frame", type=Path)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--received-at", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    if args.received_at.tzinfo is None:
        parser.error("--received-at must include its original timezone offset")
    request = FeedRequest(instrument_keys=tuple(args.instrument_key))
    engine = build_engine(Settings())
    try:
        plan = resolve_feed(engine, request)
        with args.frame.open("rb") as stream:
            body = stream.read(MAX_FRAME_BYTES + 1)
        frame = decode_frame(body, plan, args.received_at)
        print(json.dumps(asdict(frame), default=str))
    except FeedError as error:
        raise SystemExit(f"Feed frame rejected: {error}") from None
    except OSError:
        raise SystemExit("Feed frame could not be read") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
