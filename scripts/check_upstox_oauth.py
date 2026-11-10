"""Validate optional Upstox OAuth settings without showing values or making network requests."""

import json

from backend.app.brokers.oauth import configuration_status
from backend.app.config import Settings
from scripts.bootstrap_local import ROOT


def main() -> int:
    result = configuration_status(Settings(_env_file=ROOT / ".env"))
    print(json.dumps(result), flush=True)
    return 0 if result["state"] == "CONFIGURED_OPERATOR_DECLARED" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit("OAUTH_CONFIGURATION_UNAVAILABLE: sensitive details withheld") from None
