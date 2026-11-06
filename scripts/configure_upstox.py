"""Configure a read-only Analytics credential locally; never receive it through chat/argv."""

import os
import re
import tempfile
from getpass import getpass
from pathlib import Path

from backend.app.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def save_analytics_credential(destination: Path, token: str, expiry: str) -> None:
    if destination.is_symlink():
        raise ValueError("Refusing to replace a symlinked environment file")
    settings = Settings(
        _env_file=None, upstox_analytics_token=token, upstox_analytics_expires_at=expiry
    )
    if not settings.upstox_analytics_token.get_secret_value():
        raise ValueError("A nonempty Analytics credential is required")
    expires = settings.upstox_analytics_expires_at
    if expires is None:
        raise ValueError("A timezone-aware expiry is required")
    original = (
        destination.read_text() if destination.exists() else (ROOT / ".env.example").read_text()
    )
    lines = [
        line
        for line in original.splitlines()
        if not re.match(r"^\s*(?:export\s+)?UPSTOX_ANALYTICS_(?:TOKEN|EXPIRES_AT)\s*=", line)
    ]
    lines.extend(
        [
            f"UPSTOX_ANALYTICS_TOKEN='{token}'",
            f"UPSTOX_ANALYTICS_EXPIRES_AT='{expires.isoformat()}'",
        ]
    )
    descriptor, temporary = tempfile.mkstemp(prefix=".algotrade-secret-", dir=destination.parent)
    try:
        # mkstemp creates mode0600; replace atomically without following a destination symlink.
        with os.fdopen(descriptor, "w") as output:
            output.write("\n".join(lines) + "\n")
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    credential = getpass("Upstox Analytics Token (hidden; never paste into chat): ")
    expires_at = input("Actual expiry from broker console (ISO8601 with timezone): ").strip()
    try:
        save_analytics_credential(ROOT / ".env", credential, expires_at)
    except ValueError:
        raise SystemExit(
            "Configuration rejected. Check token format, timezone-aware expiry and file type."
        ) from None
    print("Analytics credential saved locally with mode0600. Configure DB/admin access separately.")
