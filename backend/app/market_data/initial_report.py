"""Evidence-only first-week report; never certifies elapsed days or authorizes trading."""

import html
import re
from typing import Any

from sqlalchemy.engine import Engine

from backend.app.market_data.coverage import CoverageRequest, coverage_report


def initial_observation_report(engine: Engine, request: CoverageRequest) -> dict[str, Any]:
    # Reuse the bounded, hash-validated, repeatable-read archive reader. No broker calls.
    coverage = coverage_report(engine, request)
    return {
        "report_kind": "INITIAL_OBSERVATION_EVIDENCE",
        "assessment": "NOT_CERTIFIED",
        "source": coverage["source"],
        "as_of": coverage["as_of"],
        "from_date": request.from_date,
        "to_date": request.to_date,
        "requested_calendar_dates": (request.to_date - request.from_date).days + 1,
        "recorded_session_count": len(coverage["session_ids"]),
        "session_ids": coverage["session_ids"],
        "counts": coverage["counts"],
        "days": coverage["days"],
        "calendar": coverage["calendar"],
        "outside_or_unusable_frames": coverage["outside_or_unusable_frames"],
        "sampled_dates": [
            day["date"]
            for day in coverage["days"]
            if any(key["sampled_interval_ms"] > 0 for key in day["keys"])
        ],
        "coverage_kind": coverage["coverage_kind"],
        "qualifying_observation_days": coverage["qualifying_observation_days"],
        "signal_eligible": False,
        "execution_eligible": False,
        "live_enabled": False,
    }


def _text(value: object) -> str:
    # Instrument keys are data, not executable HTML or Markdown instructions.
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", html.escape(str(value), quote=True))


def render_initial_observation(report: dict[str, Any]) -> str:
    lines = [
        "# Initial observation report",
        "",
        f"Source: **{_text(report['source'])}**. Assessment: **NOT CERTIFIED**.",
        f"Generated at: {_text(report['as_of'])} (UTC).",
        f"Requested dates: {_text(report['from_date'])} to {_text(report['to_date'])} (IST).",
        "",
        "## Data availability",
        "",
        f"Recorded sessions matching these keys/source: {report['recorded_session_count']}.",
        f"Validated stored events: {report['counts']['events']}.",
        "A seven-date request or elapsed calendar time does not prove seven days of observation.",
        "Synthetic archives are separate evidence and cannot satisfy genuine observation.",
        "",
        "## Trading sessions observed",
        "",
        "| IST date | Calendar state | Instrument key | Accepted samples | Sampled ms | "
        "Uncovered elapsed ms |",
        "|---|---|---|---:|---:|---:|",
    ]
    for day in report["days"]:
        for key in day["keys"]:
            uncovered = key["uncovered_elapsed_ms"]
            lines.append(
                f"| {_text(day['date'])} | {_text(day['state'])} | "
                f"{_text(key['instrument_key'])} | {key['accepted_samples']} | "
                f"{key['sampled_interval_ms']} | "
                f"{uncovered if uncovered is not None else 'Unknown'} |"
            )
    lines += [
        "",
        "Sampled spans are conservative evidence, not complete exchange tick coverage.",
        "Calendar amendment completeness is unverified; unknown windows remain unknown.",
        "Qualifying observation days: 0. No completed-day certification is implemented.",
        "",
        "## Indicators evaluated",
        "",
        "Not implemented: Phase 3 research. No indicator results are invented.",
        "",
        "## Patterns detected",
        "",
        "Not evaluated: pattern detection belongs to Phase 3.",
        "",
        "## Hypothetical signals",
        "",
        "Not implemented: Phase 4 strategy engine. No signals or hypothetical P&L are recorded.",
        "",
        "## Market volatility",
        "",
        "Not evaluated by this archive-coverage report; no volatility estimate is inferred.",
        "",
        "## Liquidity issues",
        "",
        "Not evaluated: LTPC coverage alone does not establish bid/ask depth or spread quality.",
        "Option-chain research is separate and its receipt time does not verify quote freshness.",
        "",
        "## Data gaps",
        "",
        f"Stored duplicate observations: {report['counts']['duplicates']}; "
        f"out-of-order observations: {report['counts']['out_of_order']}; "
        f"disconnect events: {report['counts']['disconnects']}.",
        f"Outside-window or unusable data frames: {report['outside_or_unusable_frames']}.",
        "Uncovered elapsed time is not an exact missing-tick count.",
        "Exchange sequence loss is unknown.",
        "",
        "## Strategy limitations",
        "",
        "This report evaluates stored data availability only. It does not backtest a strategy,",
        "simulate fills, claim profitability, approve Phase 2 completion or authorize trading.",
        "",
        "## Recommendation for further testing",
        "",
        "Verify current metadata and reviewed session/calendar evidence before each capture.",
        "Collect genuine market-hours updates and inspect freshness, reconnects and sampled gaps.",
        "Review the full seven-calendar-day observation window using actual available sessions.",
        "Keep research, strategies and paper execution in their required later phases.",
        "OBSERVATION mode remains required; live trading and execution remain disabled.",
        "",
    ]
    return "\n".join(lines)
