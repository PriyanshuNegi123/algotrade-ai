"""Read-only local capture checks. No broker requests, writes, tokens or URLs in arguments."""

import argparse
import json

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.feed import FeedRequest
from backend.app.market_data.preflight import capture_preflight
from backend.app.market_data.supervision_store import CapturePolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--total-seconds", type=int, default=600)
    parser.add_argument("--session-seconds", type=int, default=300)
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-payload-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--max-events", type=int, default=20_000)
    args = parser.parse_args()
    try:
        request = FeedRequest(instrument_keys=tuple(args.instrument_key))
        policy = CapturePolicy(
            total_seconds=args.total_seconds,
            session_seconds=args.session_seconds,
            max_sessions=args.max_sessions,
            max_payload_bytes=args.max_payload_bytes,
            max_events=args.max_events,
        )
        settings = Settings()
    except Exception:
        print(
            json.dumps(
                {
                    "state": "BLOCKED",
                    "can_attempt_capture": False,
                    "blockers": ["LOCAL_CONFIGURATION_OR_REQUEST_INVALID"],
                    "recording_started": False,
                    "live_enabled": False,
                    "next_actions": [
                        "Review protected local settings and requested key/quota formats."
                    ],
                }
            )
        )
        return 2
    engine = None
    try:
        engine = build_engine(settings)
        result = capture_preflight(engine, settings, request, policy)
        print(json.dumps(result, default=str))
        return 0 if result["can_attempt_capture"] else 2
    except Exception:
        print(
            json.dumps(
                {
                    "state": "BLOCKED",
                    "can_attempt_capture": False,
                    "blockers": ["LOCAL_PREFLIGHT_UNAVAILABLE"],
                    "recording_started": False,
                    "live_enabled": False,
                }
            )
        )
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
