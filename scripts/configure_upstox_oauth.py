"""Save registered OAuth app settings through a local terminal, never chat or argv."""

import argparse
import io
import json
import os
import stat
import sys
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path

from dotenv.parser import parse_stream
from pydantic import SecretStr, ValidationError

from backend.app.brokers.oauth import OAuthApp, OAuthError
from backend.app.brokers.oauth_browser import callback_configuration
from scripts.bootstrap_local import ROOT, BootstrapError, assignments, bootstrap_lock, private_write

FIELDS = ("UPSTOX_CLIENT_ID", "UPSTOX_CLIENT_SECRET", "UPSTOX_REDIRECT_URI")


class OAuthSetupError(Exception):
    """Only fixed local reason codes; no input values in errors."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unknown arguments, which might be misplaced secrets.
        raise OAuthSetupError("OAUTH_ARGUMENTS_INVALID")


def read_environment(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, encoding="utf-8", newline="") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1
                or info.st_size > 1024 * 1024
            ):
                raise OAuthSetupError("OAUTH_ENV_UNSAFE")
            contents = stream.read(1024 * 1024 + 1)
            if len(contents) > 1024 * 1024:
                raise OAuthSetupError("OAUTH_ENV_UNSAFE")
            return contents
    except FileNotFoundError:
        raise OAuthSetupError("OAUTH_BOOTSTRAP_REQUIRED") from None
    except (OSError, UnicodeError):
        raise OAuthSetupError("OAUTH_ENV_UNAVAILABLE") from None


def literal(value: str) -> str:
    # Single quotes preserve dollars in Compose. Reject ambiguous cross-parser literals.
    # python-dotenv expands ${...} even in single quotes; backslash decoding also differs.
    if "\\" in value or "${" in value:
        raise OAuthSetupError("OAUTH_ENV_LITERAL_UNSUPPORTED")
    return "'" + value.replace("'", "\\'") + "'"


def save_oauth_settings(
    root: Path,
    client_id: str,
    client_secret: SecretStr,
    redirect_uri: str,
    *,
    replace: bool = False,
) -> dict[str, object]:
    try:
        app = OAuthApp(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)
    except ValidationError:
        raise OAuthSetupError("OAUTH_APP_CONFIGURATION_INVALID") from None
    updates = {
        "UPSTOX_CLIENT_ID": app.client_id,
        "UPSTOX_CLIENT_SECRET": app.client_secret.get_secret_value(),
        "UPSTOX_REDIRECT_URI": app.redirect_uri,
    }
    encoded = {key: literal(value) for key, value in updates.items()}
    destination = root / ".env"
    # Reject missing/unsafe files before even creating the shared bootstrap lock directory.
    read_environment(destination)
    with bootstrap_lock(root):
        original = read_environment(destination)
        values = assignments(original)
        aliases = [key.upper() for key in values if key.upper() in FIELDS]
        if len(aliases) != len(set(aliases)):
            raise OAuthSetupError("OAUTH_ENV_DUPLICATE_FIELDS")
        if values.get("TRADING_MODE") != "OBSERVATION" or values.get(
            "LIVE_ENABLED", ""
        ).lower() != ("false"):
            raise OAuthSetupError("OAUTH_OBSERVATION_REQUIRED")
        try:
            origins = json.loads(values.get("ALLOWED_ORIGINS", "[]"))
            if not isinstance(origins, list) or not all(isinstance(item, str) for item in origins):
                raise ValueError
            callback_configuration(app, origins)
        except (ValueError, OAuthError):
            raise OAuthSetupError("OAUTH_CALLBACK_LOCAL_CONFIGURATION_INVALID") from None
        existing = {key.upper(): value for key, value in values.items() if key.upper() in FIELDS}
        changed = existing != updates
        if changed and any(existing.values()) and not replace:
            raise OAuthSetupError("OAUTH_REPLACEMENT_REQUIRES_FLAG")
        if changed:
            # Preserve original text of every unrelated binding, including multiline values.
            contents = "".join(
                binding.original.string
                for binding in parse_stream(io.StringIO(original))
                if binding.key is None or binding.key.upper() not in FIELDS
            )
            newline = "\r\n" if "\r\n" in original else "\n"
            if contents and not contents.endswith(("\r", "\n")):
                contents += newline
            contents += "".join(f"{key}={encoded[key]}{newline}" for key in FIELDS)
            if any(assignments(contents).get(key) != value for key, value in updates.items()):
                raise OAuthSetupError("OAUTH_ENV_LITERAL_UNSUPPORTED")
            if read_environment(destination) != original:
                raise OAuthSetupError("OAUTH_ENV_CHANGED_DURING_SETUP")
            private_write(destination, contents)
            # Publication already occurred if the following durability check fails.
            try:
                descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                raise OAuthSetupError("OAUTH_SETTINGS_SAVE_UNCERTAIN") from None
        return {
            "state": "CONFIGURED_OPERATOR_DECLARED",
            "saved": changed,
            "registration_verified": False,
            "browser_authorization_started": False,
            "live_enabled": False,
        }


def main() -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="Replace previously configured app")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise OAuthSetupError("OAUTH_INTERACTIVE_TERMINAL_REQUIRED")
    read_environment(ROOT / ".env")
    client_id = input("Registered Upstox API key (public client ID): ")
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        secret = SecretStr(getpass("Upstox API secret (hidden; never paste into chat): "))
    redirect = input("Exact registered redirect URL: ")
    result = save_oauth_settings(ROOT, client_id, secret, redirect, replace=args.replace)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        raise SystemExit(
            "OAUTH_SETUP_CANCELLED: inspect local configuration before retrying"
        ) from None
    except Exception as error:
        code = str(error) if isinstance(error, OAuthSetupError) else "OAUTH_SETUP_UNAVAILABLE"
        if isinstance(error, BootstrapError):
            code = "OAUTH_LOCAL_CONFIGURATION_UNAVAILABLE"
        raise SystemExit(code + ": sensitive details withheld") from None
