"""Read-only pilot budget diagnostics; never records or calls the broker/Drive."""

import argparse
import json
import subprocess
from datetime import date

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.market_data.observation_budget import BudgetRequest, pilot_budget


def local_budget(request: BudgetRequest) -> dict:
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
    ]
    response = subprocess.run(
        command,
        input=(ROOT / "scripts/observation_budget.py").read_text(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if response.returncode not in (0, 2) or len(response.stdout) > 1024 * 1024:
        raise ValueError("LOCAL_BUDGET_UNAVAILABLE")
    result = json.loads(response.stdout)
    if not isinstance(result, dict) or result.get("report_kind") != "OBSERVATION_PILOT_BUDGET":
        raise ValueError("LOCAL_BUDGET_INVALID")
    blockers = result.get("blockers")
    if (
        not isinstance(blockers, list)
        or any(not isinstance(code, str) for code in blockers)
        or response.returncode != (2 if blockers else 0)
        or result.get("state") != ("BUDGET_BLOCKED" if blockers else "BUDGET_AVAILABLE_FOR_RECHECK")
        or any(
            result.get(flag) is not False
            for flag in (
                "authorizes_capture",
                "reservation_created",
                "recording_started",
                "phase2_complete",
                "entries_enabled",
                "live_enabled",
            )
        )
    ):
        raise ValueError("LOCAL_BUDGET_INVALID")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", required=True, type=date.fromisoformat)
    parser.add_argument("--to-date", required=True, type=date.fromisoformat)
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    request = BudgetRequest(from_date=args.from_date, to_date=args.to_date)
    if args.local:
        result = local_budget(request)
    else:
        engine = build_engine(Settings())
        try:
            result = pilot_budget(engine, request)
        finally:
            engine.dispose()
    print(json.dumps(result, default=str), flush=True)
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("OBSERVATION_BUDGET_UNAVAILABLE: sensitive details withheld") from None
