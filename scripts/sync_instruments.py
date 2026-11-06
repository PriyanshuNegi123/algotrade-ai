"""Fetch the fixed official public NSE master and archive validated index metadata."""

import json

from backend.app.config import Settings
from backend.app.database import build_engine
from backend.app.instruments.service import archive, prepare
from backend.app.instruments.source import InstrumentError, InstrumentSource


def main() -> None:
    engine = build_engine(Settings())
    try:
        result = archive(engine, prepare(InstrumentSource().download()))
        print(json.dumps(result, default=str))
    except InstrumentError as error:
        raise SystemExit(f"Instrument import rejected: {error}") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
