"""Private container CLI: inspect or request cooperative stop; never starts recording."""

import argparse
import json
import re

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.supervision_store import (
    list_captures,
    read_capture,
    request_capture_stop,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "stop"))
    parser.add_argument("--capture-id")
    args = parser.parse_args()
    if args.capture_id and re.fullmatch(r"[0-9a-f]{32}", args.capture_id) is None:
        raise ValueError("INVALID_CAPTURE_ID")
    engine = build_engine(Settings())
    try:
        if args.action == "stop":
            if not args.capture_id:
                raise ValueError("CAPTURE_ID_REQUIRED")
            report = request_capture_stop(engine, args.capture_id)
        elif args.capture_id:
            report = read_capture(engine, args.capture_id)
            if report is None:
                raise ValueError("CAPTURE_NOT_FOUND")
        else:
            report = list_captures(engine, 20, None)
        print(json.dumps(report, default=str), flush=True)
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("CAPTURE_CONTROL_FAILED: sensitive details withheld") from None
