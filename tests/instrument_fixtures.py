"""Synthetic metadata, never actual tradable contract IDs or market quotes."""

import gzip
import json
from datetime import UTC, datetime, timedelta

from backend.app.instruments.source import Download


def metadata_rows(lot_size=50, option_key="NSE_FO|synthetic-option"):
    expiry = int((datetime.now(UTC) + timedelta(days=30)).timestamp() * 1000)
    return [
        {
            "segment": "NSE_INDEX",
            "instrument_type": "INDEX",
            "instrument_key": "NSE_INDEX|Synthetic index",
            "trading_symbol": "Synthetic index",
        },
        {
            "segment": "NSE_FO",
            "instrument_type": "CE",
            "instrument_key": option_key,
            "trading_symbol": "SYNTHETIC OPTION",
            "underlying_type": "INDEX",
            "underlying_key": "NSE_INDEX|Synthetic index",
            "lot_size": lot_size,
            "minimum_lot": lot_size,
            "tick_size": 5.0,
            "strike_price": 100.0,
            "expiry": expiry,
        },
    ]


def metadata_download(rows=None, modified_at=None):
    now = datetime.now(UTC)
    return Download(
        gzip.compress(json.dumps(rows if rows is not None else metadata_rows()).encode()),
        modified_at or now - timedelta(minutes=1),
        now,
    )
