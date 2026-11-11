import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import event, update

from backend.app.market_data.coverage import CoverageError, CoverageRequest
from backend.app.market_data.initial_report import (
    initial_observation_report,
    render_initial_observation,
)
from backend.app.market_data.observation_models import ObservationEvent
from tests.integration.test_coverage import fixture_calendar, recorded, report_request

pytestmark = pytest.mark.usefixtures("coverage_clock")


def test_empty_seven_dates_never_certifies_observation(client):
    request = report_request("UPSTOX_V3")
    request = request.model_copy(update={"from_date": request.to_date - timedelta(days=6)})
    report = initial_observation_report(client.app.state.engine, request)
    assert report["requested_calendar_dates"] == 7
    assert report["recorded_session_count"] == 0 and report["sampled_dates"] == []
    assert report["assessment"] == "NOT_CERTIFIED" and report["qualifying_observation_days"] == 0
    assert not report["signal_eligible"] and not report["execution_eligible"]
    assert not report["live_enabled"]
    assert not report["window_progress"]["review_complete"]
    assert "ACCEPTANCE_CRITERIA_REVIEW_REQUIRED" in report["window_progress"]["review_blockers"]
    markdown = render_initial_observation(report)
    assert "## Observation-window progress" in markdown
    assert "## Frame exclusion diagnostics" in markdown
    assert sum(report["unusable_frame_reasons"].values()) == report["outside_or_unusable_frames"]
    assert "not a verified observation start" in markdown
    for heading in (
        "Data availability",
        "Trading sessions observed",
        "Indicators evaluated",
        "Patterns detected",
        "Hypothetical signals",
        "Market volatility",
        "Liquidity issues",
        "Data gaps",
        "Strategy limitations",
        "Recommendation for further testing",
    ):
        assert f"## {heading}" in markdown
    assert "No signals or hypothetical P&L" in markdown


def test_synthetic_samples_remain_separate_and_report_is_read_only(client):
    engine = client.app.state.engine
    identity, _ = recorded(engine)
    statements = []

    def observed(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper())

    event.listen(engine, "before_cursor_execute", observed)
    try:
        with patch(
            "backend.app.market_data.coverage.load_calendar", return_value=fixture_calendar()
        ):
            genuine = initial_observation_report(engine, report_request("UPSTOX_V3"))
            synthetic = initial_observation_report(engine, report_request())
    finally:
        event.remove(engine, "before_cursor_execute", observed)
    assert genuine["session_ids"] == [] and genuine["counts"]["events"] == 0
    assert synthetic["session_ids"] == [identity] and synthetic["source"] == "SYNTHETIC"
    assert synthetic["days"][0]["keys"][0]["sampled_interval_ms"] == 1000
    assert synthetic["qualifying_observation_days"] == 0
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"}
    assert "**SYNTHETIC**" in render_initial_observation(synthetic)


def test_corrupt_archive_fails_before_report_is_returned(client):
    engine = client.app.state.engine
    recorded(engine)
    with engine.begin() as connection:
        connection.execute(
            update(ObservationEvent)
            .where(ObservationEvent.sequence == 1)
            .values(payload_sha256="0" * 64)
        )
    with pytest.raises(CoverageError, match="COVERAGE_ARCHIVE_INVALID"):
        initial_observation_report(engine, report_request())


def test_instrument_keys_cannot_inject_html_or_markdown(client):
    request = report_request(keys=("NSE_FO|<img onerror=alert(1)>[label]`",))
    markdown = render_initial_observation(
        initial_observation_report(client.app.state.engine, request)
    )
    assert "<img" not in markdown
    assert "&lt;img" in markdown and "\\[label\\]\\`" in markdown


@pytest.mark.parametrize("source", ["UPSTOX_V3", "SYNTHETIC"])
def test_local_forwarding_has_no_credentials_and_no_capture(tmp_path, source):
    import subprocess

    from scripts.initial_observation import local_report

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/initial_observation.py").write_text("# trusted report source")
    payload = {"report_kind": "INITIAL_OBSERVATION_EVIDENCE"}
    with (
        patch("scripts.bootstrap_local.ROOT", tmp_path),
        patch("scripts.capture_local.local_container", return_value=("docker", "app")),
        patch(
            "scripts.initial_observation.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
        ) as run,
    ):
        assert local_report(report_request(source)) == payload
    command = run.call_args.args[0]
    assert "--local" not in command and "--env" not in command
    assert command[command.index("--source") + 1] == source
    assert "--format" in command and "json" in command
    assert run.call_args.kwargs["input"] == "# trusted report source"


@pytest.mark.parametrize("body,code", [("private failure", 1), ("[]", 0), ("{}", 0)])
def test_invalid_local_report_fails_closed(tmp_path, body, code):
    import subprocess

    from scripts.initial_observation import local_report

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/initial_observation.py").write_text("# trusted report source")
    with (
        patch("scripts.bootstrap_local.ROOT", tmp_path),
        patch("scripts.capture_local.local_container", return_value=("docker", "app")),
        patch(
            "scripts.initial_observation.subprocess.run",
            return_value=subprocess.CompletedProcess([], code, body, "private stderr"),
        ),
        pytest.raises(ValueError, match="LOCAL_REPORT_(UNAVAILABLE|INVALID)"),
    ):
        local_report(report_request())


def test_report_request_keeps_existing_range_and_segment_bounds():
    from pydantic import ValidationError

    base = report_request()
    for changes in (
        {"from_date": base.to_date - timedelta(days=7)},
        {"instrument_keys": ("NSE_INDEX|Nifty 50",)},
    ):
        with pytest.raises(ValidationError):
            CoverageRequest.model_validate({**base.model_dump(), **changes})
