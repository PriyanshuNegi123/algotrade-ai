"""Log only allowlisted operational metadata; never HTTP bodies, headers or queries."""

import json
import logging
from datetime import UTC, datetime


class SafeJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "event": record.msg if record.msg in {"request_complete"} else "application_event",
                "request_id": getattr(record, "request_id", None),
                "status": getattr(record, "status", None),
            }
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJSONFormatter())
    logger = logging.getLogger("algotrade")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
