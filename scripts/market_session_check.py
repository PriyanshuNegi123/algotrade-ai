"""Check private-runtime market-hours readiness; never starts recording or calls the broker."""

import argparse
import json
from pathlib import Path

from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.session_readiness import market_session_readiness
from backend.app.market_data.supervision_store import CapturePolicy
from scripts.bootstrap_local import ROOT
from scripts.capture_local import capture_local


def check_local(root: Path, request: FeedRequest, policy: CapturePolicy) -> dict:
    _, preflight = capture_local(root, request, policy, preflight_only=True)
    return market_session_readiness(preflight)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--total-seconds", type=int, default=20)
    parser.add_argument("--session-seconds", type=int, default=20)
    parser.add_argument("--max-sessions", type=int, default=1)
    parser.add_argument("--max-payload-bytes", type=int, default=65536)
    parser.add_argument("--max-events", type=int, default=20)
    args = parser.parse_args()
    request = FeedRequest(instrument_keys=tuple(args.instrument_key))
    policy = CapturePolicy(
        total_seconds=args.total_seconds,
        session_seconds=args.session_seconds,
        max_sessions=args.max_sessions,
        max_payload_bytes=args.max_payload_bytes,
        max_events=args.max_events,
    )
    result = check_local(ROOT, request, policy)
    print(json.dumps(result, default=str), flush=True)
    return 0 if result["can_attempt_market_hours_capture"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("SESSION_READINESS_UNAVAILABLE: sensitive details withheld") from None
