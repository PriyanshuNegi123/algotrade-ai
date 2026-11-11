"""Evidence-only first-week report; never certifies elapsed days or authorizes trading."""

import html
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.engine import Engine

from backend.app.market_data.contracts import IST
from backend.app.market_data.coverage import CoverageRequest, coverage_report


def _window_progress(
    coverage: dict[str, Any], request: CoverageRequest, sampled_dates: list[date]
) -> dict[str, Any]:
    """Describe the requested filter and evidence; never certify an observation clock."""
    as_of: datetime = coverage["as_of"]
    start = datetime.combine(request.from_date, time.min, IST)
    end = datetime.combine(request.to_date + timedelta(days=1), time.min, IST)
    requested = (request.to_date - request.from_date).days + 1
    elapsed = max(0, min(requested, (as_of.astimezone(IST).date() - request.from_date).days))
    sessions = [day for day in coverage["days"] if day["opens_at"] and day["closes_at"]]
    closed = [day["date"] for day in sessions if day["closes_at"] <= as_of]
    missing = [day for day in closed if day not in sampled_dates]
    unknown = [
        day["date"]
        for day in coverage["days"]
        if day["state"] in {"UNKNOWN_CALENDAR", "UNKNOWN_HOURS"}
    ]
    blockers = []
    if requested != 7:
        blockers.append("SEVEN_CALENDAR_DATES_REQUIRED")
    if as_of < end:
        blockers.append("REQUESTED_RANGE_NOT_ELAPSED")
    if request.source != "UPSTOX_V3":
        blockers.append("SYNTHETIC_SOURCE")
    if coverage["calendar"]["kind"] != "OFFICIAL_BASELINE":
        blockers.append("SYNTHETIC_CALENDAR")
    if unknown:
        blockers.append("UNKNOWN_CALENDAR_WINDOWS")
    if not coverage["calendar"]["amendment_completeness_verified"]:
        blockers.append("CALENDAR_AMENDMENTS_UNVERIFIED")
    if missing:
        blockers.append("ELAPSED_SESSION_DATES_WITHOUT_SAMPLED_INTERVALS")
    # No numerical coverage threshold or completed-day policy is invented here.
    blockers.append("ACCEPTANCE_CRITERIA_REVIEW_REQUIRED")
    return {
        "range_state": "FUTURE" if as_of < start else "ELAPSED" if as_of >= end else "IN_PROGRESS",
        "starts_at_ist": start,
        "ends_at_exclusive_ist": end,
        "elapsed_calendar_dates": elapsed,
        "remaining_calendar_dates": requested - elapsed,
        "seven_date_range_elapsed": requested == 7 and as_of >= end,
        "calendar_session_dates": [day["date"] for day in sessions],
        "elapsed_calendar_session_dates": closed,
        "elapsed_session_dates_without_sampled_intervals": missing,
        "unknown_calendar_dates": unknown,
        "review_blockers": blockers,
        "requested_range_is_verified_observation_start": False,
        "minimum_coverage_threshold_defined": False,
        "review_complete": False,
        "phase2_complete": False,
    }


def initial_observation_report(engine: Engine, request: CoverageRequest) -> dict[str, Any]:
    # Reuse the bounded, hash-validated, repeatable-read archive reader. No broker calls.
    coverage = coverage_report(engine, request)
    sampled_dates = [
        day["date"]
        for day in coverage["days"]
        if any(key["sampled_interval_ms"] > 0 for key in day["keys"])
    ]
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
        "unusable_frame_reasons": dict(coverage["unusable_frame_reasons"]),
        "sampled_dates": sampled_dates,
        "window_progress": _window_progress(coverage, request, sampled_dates),
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
    progress = report["window_progress"]
    lines = [
        "# Initial observation report",
        "",
        f"Source: **{_text(report['source'])}**. Assessment: **NOT CERTIFIED**.",
        f"Generated at: {_text(report['as_of'])} (UTC).",
        f"Requested dates: {_text(report['from_date'])} to {_text(report['to_date'])} (IST).",
        "",
        "## Observation-window progress",
        "",
        f"Requested-range state: **{_text(progress['range_state'])}**. "
        f"Fully elapsed calendar dates: {progress['elapsed_calendar_dates']} "
        f"of {report['requested_calendar_dates']}.",
        f"Review blockers: {_text(', '.join(progress['review_blockers']))}.",
        "The requested date filter is not a verified observation start. Elapsed dates and",
        "sampled dates do not certify completed days. Minimum coverage criteria need review.",
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
        "## Frame exclusion diagnostics",
        "",
        "| Primary reason | Frames |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {_text(reason)} | {count} |"
        for reason, count in report["unusable_frame_reasons"].items()
    )
    lines += [
        "",
        "One primary reason is counted per frame in the outside/unusable aggregate.",
        "These counts do not enumerate all per-key trade exclusions, missing ticks or root causes.",
        "Generation after receipt does not identify which clock or timestamp source is incorrect.",
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
