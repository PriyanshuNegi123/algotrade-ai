"""Exact, bounded primitives shared by read-only market-data importers."""

import json
from decimal import Decimal
from typing import Any


class MarketDataError(Exception):
    pass


def quantity(value: object) -> int:
    if type(value) is int:
        result = value
    elif isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        if value < 0 or value > 9_223_372_036_854_775_807:
            raise MarketDataError("INVALID_QUANTITY")
        result = int(value)
    else:
        raise MarketDataError("INVALID_QUANTITY")
    if result < 0 or result > 9_223_372_036_854_775_807:
        raise MarketDataError("INVALID_QUANTITY")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MarketDataError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _bad_number(value: str) -> None:
    raise MarketDataError("INVALID_JSON_NUMBER")


def strict_json(body: bytes) -> Any:
    try:
        return json.loads(
            body, parse_float=Decimal, object_pairs_hook=_unique_object, parse_constant=_bad_number
        )
    except (ValueError, TypeError, RecursionError):
        raise MarketDataError("INVALID_JSON") from None
