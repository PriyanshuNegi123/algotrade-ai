"""Synthetic historical bars only; never broker recordings or execution results."""

import json
from datetime import UTC, datetime, time, timedelta

from backend.app.brokers.upstox import BrokerPayload, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.market_data.contracts import IST, CandleRequest, history_url

TOKEN = "synthetic-history-credential"


def history_request(**changes):
    day = datetime.now(UTC).astimezone(IST).date() - timedelta(days=1)
    return CandleRequest(
        **{
            "instrument_key": "NSE_INDEX|Synthetic index",
            "from_date": day,
            "to_date": day,
            **changes,
        }
    )


def candle_rows(request=None, count=3):
    request = request or history_request()
    start = datetime.combine(request.from_date, time(9, 15), tzinfo=IST)
    return [
        [
            (start + timedelta(minutes=index * request.interval)).isoformat(),
            100,
            102,
            99,
            101.25,
            1000,
            0,
        ]
        for index in range(count)
    ]


def candle_payload(request=None, rows=None, **extra):
    request = request or history_request()
    body = {
        "status": "success",
        "data": {"candles": rows if rows is not None else candle_rows(request), **extra},
    }
    return BrokerPayload(history_url(request), json.dumps(body).encode(), datetime.now(UTC))


def history_adapter(transport):
    settings = Settings(
        _env_file=None,
        upstox_analytics_token=TOKEN,
        upstox_analytics_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return ReadOnlyUpstox(settings, transport)
