"""Synthetic paired contracts and quotes, never real broker market observations."""

import json
from datetime import UTC, datetime, timedelta

from backend.app.brokers.upstox import BrokerPayload, ReadOnlyUpstox
from backend.app.config import Settings
from backend.app.market_data.contracts import IST
from backend.app.market_data.option_contracts import ChainRequest, chain_url
from tests.instrument_fixtures import metadata_download, metadata_rows

TOKEN = "synthetic-chain-credential"


def chain_metadata():
    rows = metadata_rows()
    rows.append({**rows[1], "instrument_type": "PE", "instrument_key": "NSE_FO|synthetic-put"})
    return metadata_download(rows, modified_at=datetime.now(UTC))


def chain_request(**changes):
    expiry = (datetime.now(UTC) + timedelta(days=30)).astimezone(IST).date()
    return ChainRequest(
        **{"underlying_key": "NSE_INDEX|Synthetic index", "expiry_date": expiry, **changes}
    )


def chain_rows(request=None):
    request = request or chain_request()

    def leg(key, delta):
        return {
            "instrument_key": key,
            "market_data": {
                "ltp": 10.5,
                "close_price": 10,
                "bid_price": 10,
                "ask_price": 11,
                "bid_qty": 100,
                "ask_qty": 100,
                "volume": 500,
                "oi": 1000,
                "prev_oi": 900,
            },
            "option_greeks": {
                "delta": delta,
                "gamma": 0.0000000001,
                "theta": -2.5,
                "vega": 1.5,
                "iv": 20,
                "pop": 45,
            },
        }

    return [
        {
            "underlying_key": request.underlying_key,
            "expiry": request.expiry_date.isoformat(),
            "strike_price": 100,
            "underlying_spot_price": 100,
            "pcr": 1.2,
            "call_options": leg("NSE_FO|synthetic-option", 0.6),
            "put_options": leg("NSE_FO|synthetic-put", -0.4),
        }
    ]


def chain_payload(request=None, rows=None):
    request = request or chain_request()
    return BrokerPayload(
        chain_url(request),
        json.dumps(
            {"status": "success", "data": chain_rows(request) if rows is None else rows}
        ).encode(),
        datetime.now(UTC),
    )


def chain_adapter(transport):
    settings = Settings(
        _env_file=None,
        upstox_analytics_token=TOKEN,
        upstox_analytics_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return ReadOnlyUpstox(settings, transport)
