"""Explicit desktop OAuth and synthetic Drive test; never uploads project files."""

import argparse
import fcntl
import json
import logging
import os
import stat
from contextlib import contextmanager
from pathlib import Path

import requests
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, WSGITimeoutError
from oauthlib.oauth2 import MismatchingStateError, OAuth2Error

from backend.app.storage.google_drive import SCOPE, DriveArchive, DriveError
from scripts.bootstrap_local import ROOT, private_read, private_write

TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URIS = {
    "https://accounts.google.com/o/oauth2/auth",
    "https://accounts.google.com/o/oauth2/v2/auth",
}


def directory(root: Path) -> Path:
    path = root
    for part in (".local", "google"):
        path = path / part
        if path.is_symlink():
            raise DriveError("GOOGLE_SYMLINKED_DIRECTORY")
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.stat()
        if not path.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise DriveError("GOOGLE_UNSAFE_DIRECTORY")
    os.chmod(path, 0o700)
    return path


def secure_json(path: Path) -> dict | None:
    contents = private_read(path)
    if contents is None:
        return None
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise DriveError("GOOGLE_PRIVATE_FILE_PERMISSIONS_REQUIRED")
    value = json.loads(contents)
    if not isinstance(value, dict):
        raise DriveError("GOOGLE_INVALID_PRIVATE_CONFIGURATION")
    return value


def client_config(path: Path) -> dict:
    config = secure_json(path)
    installed = config.get("installed") if config else None
    if (
        not isinstance(installed, dict)
        or not isinstance(installed.get("client_id"), str)
        or not installed["client_id"].endswith(".apps.googleusercontent.com")
        or not isinstance(installed.get("client_secret"), str)
        or not installed["client_secret"]
        or installed.get("token_uri") != TOKEN_URI
        or installed.get("auth_uri") not in AUTH_URIS
    ):
        raise DriveError("GOOGLE_DESKTOP_CONFIGURATION_REQUIRED")
    # Only fields used by Google's OAuth flow; do not honor other remote endpoint fields.
    return {
        "installed": {
            key: installed[key]
            for key in (
                "client_id",
                "client_secret",
                "auth_uri",
                "token_uri",
            )
        }
    }


@contextmanager
def storage_lock(path: Path):
    descriptor = os.open(path / "oauth.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise DriveError("GOOGLE_UNSAFE_LOCK")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DriveError("GOOGLE_OPERATION_ALREADY_RUNNING") from None
        yield
    finally:
        os.close(descriptor)


def verify_scopes(credentials: Credentials) -> None:
    requested = set(credentials.scopes or ())
    granted = credentials.granted_scopes
    if requested != {SCOPE} or (granted is not None and set(granted) != {SCOPE}):
        raise DriveError("GOOGLE_DRIVE_FILE_SCOPE_REQUIRED")
    if not credentials.token or not credentials.refresh_token:
        raise DriveError("GOOGLE_OFFLINE_CREDENTIAL_REQUIRED")


def authorize(path: Path, config: dict, *, interactive: bool, force: bool = False) -> Credentials:
    if force and not interactive:
        raise DriveError("GOOGLE_EXPLICIT_AUTHORIZATION_REQUIRED")
    if os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") or os.environ.get(
        "OAUTHLIB_RELAX_TOKEN_SCOPE"
    ):
        raise DriveError("GOOGLE_UNSAFE_OAUTH_ENVIRONMENT")
    saved = secure_json(path / "token.json")
    credentials = None
    installed = config["installed"]
    if saved is not None and not force:
        if (
            saved.get("token_uri") != TOKEN_URI
            or saved.get("client_id") != installed["client_id"]
            or saved.get("client_secret") != installed["client_secret"]
            or set(saved.get("scopes", ())) != {SCOPE}
        ):
            raise DriveError("GOOGLE_TOKEN_CONFIGURATION_MISMATCH")
        credentials = Credentials.from_authorized_user_info(saved, scopes=[SCOPE])
        verify_scopes(credentials)
        if not credentials.valid:
            with requests.Session() as session:
                session.trust_env = False
                request = Request(session=session)

                def refresh_request(**kwargs):
                    kwargs["timeout"] = 20
                    kwargs["allow_redirects"] = False
                    return request(**kwargs)

                credentials.refresh(refresh_request)
    elif interactive:
        # Library verifies random state and exchanges the code with a generated PKCE verifier.
        flow = InstalledAppFlow.from_client_config(
            config,
            scopes=[SCOPE],
            autogenerate_code_verifier=True,
        )
        flow.oauth2session.trust_env = False
        original = flow.oauth2session.request

        def bounded_request(method, url, **kwargs):
            if url != TOKEN_URI:
                raise DriveError("GOOGLE_TOKEN_ENDPOINT_REJECTED")
            kwargs["timeout"] = 20
            kwargs["allow_redirects"] = False
            return original(method, url, **kwargs)

        flow.oauth2session.request = bounded_request
        try:
            print("GOOGLE_AUTHORIZATION_WAITING: complete consent in your browser.", flush=True)
            credentials = flow.run_local_server(
                host="127.0.0.1",
                bind_addr="127.0.0.1",
                port=0,
                open_browser=True,
                authorization_prompt_message=None,
                success_message="Response received. Return to AlgoTrade to confirm authorization.",
                timeout_seconds=300,
                access_type="offline",
                prompt="consent",
                include_granted_scopes="false",
            )
        finally:
            flow.oauth2session.close()
    else:
        raise DriveError("GOOGLE_AUTHORIZATION_REQUIRED")
    verify_scopes(credentials)
    if not credentials.valid:
        raise DriveError("GOOGLE_VALID_ACCESS_TOKEN_REQUIRED")
    private_write(path / "token.json", credentials.to_json())
    return credentials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify-config", "authorize", "test"))
    parser.add_argument("--reauthorize", action="store_true")
    args = parser.parse_args()
    if args.reauthorize and args.action != "authorize":
        raise DriveError("GOOGLE_EXPLICIT_AUTHORIZATION_REQUIRED")
    # Third-party DEBUG traces can contain OAuth codes/tokens and callback query strings.
    for name in ("google_auth_oauthlib", "requests_oauthlib", "oauthlib", "urllib3", "httpx"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    path = directory(ROOT)
    config = client_config(path / "credentials.json")
    if args.action == "verify-config":
        print(json.dumps({"state": "DESKTOP_CONFIGURATION_VALID", "scope": SCOPE}))
        return 0
    with storage_lock(path):
        credentials = authorize(
            path, config, interactive=args.action == "authorize", force=args.reauthorize
        )
        if args.action == "authorize":
            print(json.dumps({"state": "AUTHORIZED", "scope": SCOPE, "tokens_saved": True}))
        else:
            drive = DriveArchive(credentials.token)
            try:
                receipt = drive.synthetic_round_trip()
            finally:
                drive.close()
            private_write(path / "storage-test.json", json.dumps(receipt, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        key: receipt[key]
                        for key in (
                            "state",
                            "bytes",
                            "upload_sha256",
                            "download_sha256",
                            "folder_created",
                            "synthetic_only",
                            "file_retained",
                            "live_enabled",
                        )
                    }
                )
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DriveError as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        raise SystemExit("GOOGLE_AUTHORIZATION_CANCELLED") from None
    except WSGITimeoutError:
        raise SystemExit(
            "GOOGLE_AUTHORIZATION_TIMED_OUT: complete browser consent and retry"
        ) from None
    except MismatchingStateError:
        raise SystemExit("GOOGLE_STATE_VALIDATION_FAILED") from None
    except RefreshError:
        raise SystemExit("GOOGLE_REFRESH_REAUTHORIZATION_REQUIRED") from None
    except OAuth2Error:
        raise SystemExit("GOOGLE_AUTHORIZATION_REJECTED: check consent and app settings") from None
    except Exception:
        raise SystemExit("GOOGLE_DRIVE_OPERATION_FAILED: sensitive details withheld") from None
