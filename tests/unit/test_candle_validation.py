from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.market_data.contracts import IST, CandleRequest
from backend.app.market_data.history import CandleError, validate_history
from tests.candle_fixtures import TOKEN, candle_payload, candle_rows, history_request


@pytest.mark.parametrize(
    "changes",
    [
        {"interval": True},
        {"interval": "1"},
        {"interval": 2},
        {"from_date": date(2021, 1, 1)},
        {"from_date": datetime.now(UTC).astimezone(IST).date()},
        {"to_date": datetime.now(UTC).astimezone(IST).date()},
        {"from_date": date(2022, 1, 1), "to_date": date(2022, 2, 1)},
        {"instrument_key": "https://evil.example"},
        {"instrument_key": "NSE_INDEX|../private"},
    ],
)
def test_bad_history_request_rejected(changes):
    values = history_request().model_dump()
    with pytest.raises(ValidationError):
        CandleRequest(**{**values, **changes})


def test_descending_bars_normalized_without_preserving_untrusted_fields():
    request = history_request()
    payload = candle_payload(request, list(reversed(candle_rows(request))), ignored_secret=TOKEN)
    prepared = validate_history(request, payload)
    assert prepared.source_order == "DESCENDING" and prepared.gap_count == 0
    assert list(prepared.bars) == sorted(prepared.bars, key=lambda bar: bar.opened_at)
    assert prepared.bars[0].opened_at.utcoffset() == timedelta(0)
    assert str(prepared.bars[0].close) == "101.25"
    assert TOKEN.encode() not in prepared.canonical
    assert TOKEN not in repr(payload)


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda rows: rows + [rows[0]], "DUPLICATE_CANDLE_TIME"),
        (lambda rows: [rows[0], rows[2], rows[1]], "UNORDERED_CANDLES"),
        (lambda rows: [[rows[0][0], 100, 98, 99, 101, 10, 0]], "INCONSISTENT_OHLC"),
        (lambda rows: [[rows[0][0], 0, 102, 99, 101, 10, 0]], "INVALID_OHLC"),
        (lambda rows: [[rows[0][0], 100, 102, 99, 101, -1, 0]], "INVALID_QUANTITY"),
        (lambda rows: [[rows[0][0], 100, 102, 99, 101, True, 0]], "INVALID_QUANTITY"),
        (lambda rows: [[rows[0][0], 100, 102, 99, 101, 1.5, 0]], "INVALID_QUANTITY"),
        (lambda rows: [[rows[0][0], 100, 102, 99, 101, 10]], "INVALID_CANDLE_ROW"),
        (lambda rows: [[rows[0][0][:-6], *rows[0][1:]]], "NAIVE_CANDLE_TIME"),
    ],
)
def test_invalid_candles_rejected(mutation, code):
    request = history_request()
    with pytest.raises(CandleError, match=code):
        validate_history(request, candle_payload(request, mutation(candle_rows(request))))


def test_gap_detection_never_fills_missing_bars():
    request = history_request()
    rows = candle_rows(request)
    result = validate_history(request, candle_payload(request, [rows[0], rows[2]]))
    assert result.gap_count == 1 and len(result.bars) == 2


def test_misaligned_interval_is_rejected():
    rows = candle_rows()
    request = history_request(interval=5)
    with pytest.raises(CandleError, match="MISALIGNED_CANDLE_SEQUENCE"):
        validate_history(request, candle_payload(request, rows))


def test_source_echo_range_and_completion_checks():
    request = history_request()
    payload = candle_payload(request)
    with pytest.raises(CandleError, match="SOURCE_IDENTITY_MISMATCH"):
        validate_history(request, replace(payload, source_url="https://untrusted.example"))
    with pytest.raises(CandleError, match="INSTRUMENT_IDENTITY_MISMATCH"):
        validate_history(request, candle_payload(request, instrument_key="NSE_INDEX|Other"))
    first = datetime.fromisoformat(candle_rows(request)[0][0])
    with pytest.raises(CandleError, match="INCOMPLETE_CANDLE"):
        validate_history(request, replace(payload, retrieved_at=first))
    wrong_day = candle_rows(request)
    wrong_day[0][0] = (first - timedelta(days=1)).isoformat()
    with pytest.raises(CandleError, match="CANDLE_OUTSIDE_REQUEST"):
        validate_history(request, candle_payload(request, wrong_day))


def test_empty_result_is_explicit_not_a_fabricated_flat_candle():
    result = validate_history(history_request(), candle_payload(rows=[]))
    assert result.bars == () and result.source_order == "EMPTY"


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"status":"success","data":{"candles":[]},"status":"success"}',
        b'{"status":"error"}',
        b'{"status":"success","data":{"candles":NaN}}',
    ],
)
def test_bad_envelopes_rejected(body):
    payload = replace(candle_payload(), body=body)
    with pytest.raises(CandleError):
        validate_history(history_request(), payload)


def test_extreme_quantity_and_nonfinite_prices_rejected():
    request = history_request()
    body = candle_payload(request).body.replace(b"1000", b"1e9999999", 1)
    with pytest.raises(CandleError, match="INVALID_QUANTITY"):
        validate_history(request, replace(candle_payload(request), body=body))
    rows = candle_rows(request)
    rows[0][1] = float("inf")
    with pytest.raises(CandleError, match="INVALID_JSON_NUMBER"):
        validate_history(request, candle_payload(request, rows))


def test_candle_count_limit(monkeypatch):
    from backend.app.market_data import history

    monkeypatch.setattr(history, "MAX_CANDLES", 2)
    with pytest.raises(CandleError, match="CANDLE_COUNT_LIMIT"):
        validate_history(history_request(), candle_payload())
