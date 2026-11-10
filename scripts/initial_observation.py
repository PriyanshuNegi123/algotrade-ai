"""Render bounded stored-data evidence; no capture, broker request or file write."""

import argparse
import json
import subprocess
from datetime import date

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.coverage import CoverageRequest
from backend.app.market_data.initial_report import (
    initial_observation_report,
    render_initial_observation,
)


def local_report(request: CoverageRequest) -> dict:
    # Host-only helpers are deliberately lazy: the container packages backend, not scripts.
    from scripts.bootstrap_local import ROOT
    from scripts.capture_local import RUN_SOURCE, local_container

    executable, container = local_container(ROOT)
    command = [
        executable,
        "exec",
        "-i",
        "--workdir",
        "/app",
        container,
        "python",
        "-c",
        RUN_SOURCE,
        "--from-date",
        request.from_date.isoformat(),
        "--to-date",
        request.to_date.isoformat(),
        "--source",
        request.source,
        "--format",
        "json",
    ]
    for key in request.instrument_keys:
        command.extend(["--instrument-key", key])
    result = subprocess.run(
        command,
        input=(ROOT / "scripts/initial_observation.py").read_text(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError("LOCAL_REPORT_UNAVAILABLE")
    report = json.loads(result.stdout)
    if not isinstance(report, dict) or report.get("report_kind") != "INITIAL_OBSERVATION_EVIDENCE":
        raise ValueError("LOCAL_REPORT_INVALID")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--instrument-key", action="append", required=True)
    parser.add_argument("--source", choices=("UPSTOX_V3", "SYNTHETIC"), default="UPSTOX_V3")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    request = CoverageRequest(
        from_date=args.from_date,
        to_date=args.to_date,
        instrument_keys=tuple(args.instrument_key),
        source=args.source,
    )
    if args.local:
        report = local_report(request)
    else:
        engine = build_engine(Settings())
        try:
            report = initial_observation_report(engine, request)
        finally:
            engine.dispose()
    print(
        json.dumps(report, default=str)
        if args.format == "json"
        else render_initial_observation(report)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(
            "Initial observation report unavailable; sensitive details withheld"
        ) from None
