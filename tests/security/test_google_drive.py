import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from email.parser import BytesParser
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google.oauth2.credentials import Credentials

from backend.app.storage.google_drive import (
    FOLDER_MIME,
    MARKER,
    SCOPE,
    DriveArchive,
    DriveError,
)
from scripts import google_drive as cli
from scripts.bootstrap_local import private_write


@pytest.fixture
def google_home(tmp_path):
    path = cli.directory(tmp_path)
    config = {
        "installed": {
            "client_id": "synthetic.apps.googleusercontent.com",
            "client_secret": "synthetic-desktop-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": cli.TOKEN_URI,
        }
    }
    private_write(path / "credentials.json", json.dumps(config))
    return path, config


def credentials(*, expired=False, scopes=None):
    return Credentials(
        "synthetic-access",
        refresh_token="synthetic-refresh",
        token_uri=cli.TOKEN_URI,
        client_id="synthetic.apps.googleusercontent.com",
        client_secret="synthetic-desktop-secret",
        scopes=scopes or [SCOPE],
        expiry=(datetime.now(UTC) + timedelta(hours=-1 if expired else 1)).replace(tzinfo=None),
    )


@pytest.mark.parametrize("existing", [False, True])
def test_synthetic_roundtrip_only_creates_owned_files_and_checks_hash(existing):
    calls = []
    uploaded = {}

    def handler(request):
        calls.append(request.method)
        assert request.url.host == "www.googleapis.com"
        assert request.headers["authorization"] == "Bearer synthetic-access"
        assert "access_token" not in request.url.params
        if request.method == "GET" and request.url.path == "/drive/v3/files":
            assert "appProperties" in request.url.params["q"]
            files = (
                [
                    {
                        "id": "folder1",
                        "mimeType": FOLDER_MIME,
                        "appProperties": MARKER,
                        "trashed": False,
                    }
                ]
                if existing
                else []
            )
            return httpx.Response(200, json={"files": files})
        if request.method == "POST" and request.url.path == "/drive/v3/files":
            body = json.loads(request.content)
            assert body["mimeType"] == FOLDER_MIME and body["appProperties"] == MARKER
            return httpx.Response(200, json={"id": "folder1"})
        if request.method == "POST":
            assert request.url.path == "/upload/drive/v3/files"
            assert request.url.params["uploadType"] == "multipart"
            message = BytesParser().parsebytes(
                ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
                + request.content
            )
            parts = message.get_payload()
            metadata = json.loads(parts[0].get_payload(decode=True))
            payload = parts[1].get_payload(decode=True)
            assert json.loads(payload)["kind"] == "SYNTHETIC_STORAGE_CHECK"
            assert metadata["parents"] == ["folder1"]
            assert (
                metadata["appProperties"]["algotrade_synthetic_sha256"]
                == hashlib.sha256(payload).hexdigest()
            )
            uploaded.update(metadata=metadata, payload=payload)
            return httpx.Response(200, json={"id": "file1"})
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=uploaded["payload"])
        return httpx.Response(
            200,
            json={
                "size": str(len(uploaded["payload"])),
                "parents": ["folder1"],
                "mimeType": "application/json",
                "appProperties": uploaded["metadata"]["appProperties"],
                "capabilities": {"canDownload": True},
                "sha256Checksum": hashlib.sha256(uploaded["payload"]).hexdigest(),
            },
        )

    drive = DriveArchive("synthetic-access", transport=httpx.MockTransport(handler))
    try:
        report = drive.synthetic_round_trip()
    finally:
        drive.close()
    assert report["state"] == "VERIFIED" and report["synthetic_only"]
    assert report["folder_created"] is not existing and report["file_retained"]
    assert report["upload_sha256"] == report["download_sha256"]
    assert not set(calls) & {"DELETE", "PATCH", "PUT"}


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_drive_errors_never_redirect_retry_or_expose_remote_body(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="synthetic-private-response",
            headers={"Location": "https://untrusted.invalid/"},
        )

    drive = DriveArchive("synthetic-access", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DriveError) as error:
            drive.archive_folder()
    finally:
        drive.close()
    assert "synthetic-private-response" not in str(error.value) and len(requests) == 1


@pytest.mark.parametrize(
    "data",
    [
        {"files": [{"id": "a"}, {"id": "b"}]},
        {"files": [], "nextPageToken": "another-page"},
        {"files": [{"id": "a", "mimeType": FOLDER_MIME, "trashed": False}]},
    ],
)
def test_folder_adoption_requires_unambiguous_application_marker(data):
    drive = DriveArchive(
        "synthetic-access",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)),
    )
    try:
        with pytest.raises(DriveError):
            drive.archive_folder()
    finally:
        drive.close()


def test_download_sha256_mismatch_fails_without_delete(monkeypatch):
    drive = DriveArchive(
        "synthetic-access",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"tampered")),
    )
    monkeypatch.setattr(drive, "archive_folder", lambda: ("folder1", False))
    metadata = {}

    def fake_json(method, url, **kwargs):
        if method == "POST":
            message = BytesParser().parsebytes(
                ("Content-Type: " + kwargs["headers"]["Content-Type"] + "\r\n\r\n").encode()
                + kwargs["content"]
            )
            parts = message.get_payload()
            metadata.update(json.loads(parts[0].get_payload(decode=True)))
            metadata["size"] = str(len(parts[1].get_payload(decode=True)))
            return {"id": "file1"}
        return {**metadata, "capabilities": {"canDownload": True}}

    monkeypatch.setattr(drive, "_json", fake_json)
    try:
        with pytest.raises(DriveError, match="DRIVE_SHA256_MISMATCH"):
            drive.synthetic_round_trip()
    finally:
        drive.close()


def test_response_size_limit():
    drive = DriveArchive(
        "synthetic-access",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 65_537)),
    )
    try:
        with pytest.raises(DriveError, match="DRIVE_RESPONSE_LIMIT"):
            drive.archive_folder()
    finally:
        drive.close()


def test_secret_modes_scope_and_configuration(google_home):
    path, config = google_home
    assert cli.client_config(path / "credentials.json") == config
    assert path.stat().st_mode & 0o777 == 0o700
    os.chmod(path / "credentials.json", 0o644)
    with pytest.raises(DriveError, match="PERMISSIONS"):
        cli.client_config(path / "credentials.json")
    with pytest.raises(DriveError, match="SCOPE"):
        cli.verify_scopes(credentials(scopes=["https://www.googleapis.com/auth/drive"]))


def test_rejects_untrusted_oauth_endpoint(google_home):
    path, config = google_home
    config["installed"]["token_uri"] = "https://untrusted.invalid/token"
    private_write(path / "credentials.json", json.dumps(config))
    with pytest.raises(DriveError, match="DESKTOP_CONFIGURATION"):
        cli.client_config(path / "credentials.json")


def test_symlink_and_concurrent_authorization_rejected(google_home, tmp_path):
    path, _ = google_home
    link = tmp_path / "linked"
    link.mkdir()
    (link / ".local").symlink_to(path.parent, target_is_directory=True)
    with pytest.raises(DriveError, match="SYMLINKED"):
        cli.directory(link)
    with cli.storage_lock(path), pytest.raises(DriveError, match="ALREADY_RUNNING"):
        with cli.storage_lock(path):
            pass


def test_oauth_loopback_pkce_private_tokens_and_no_url_logging(google_home, monkeypatch, capsys):
    path, config = google_home
    session = SimpleNamespace(trust_env=True, request=Mock(), close=Mock())
    flow = SimpleNamespace(oauth2session=session, run_local_server=Mock(return_value=credentials()))
    build = Mock(return_value=flow)
    monkeypatch.setattr(cli.InstalledAppFlow, "from_client_config", build)
    result = cli.authorize(path, config, interactive=True)
    assert result.token == "synthetic-access"
    assert build.call_args.kwargs["autogenerate_code_verifier"] is True
    options = flow.run_local_server.call_args.kwargs
    assert options["host"] == options["bind_addr"] == "127.0.0.1" and options["port"] == 0
    assert options["authorization_prompt_message"] is None
    assert options["access_type"] == "offline" and options["include_granted_scopes"] == "false"
    assert session.trust_env is False and session.close.called
    assert (path / "token.json").stat().st_mode & 0o777 == 0o600
    output = capsys.readouterr().out
    assert "synthetic-access" not in output and "synthetic-refresh" not in output


def test_expired_token_refresh_is_saved_atomically(google_home, monkeypatch):
    path, config = google_home
    private_write(path / "token.json", credentials(expired=True).to_json())

    def refresh(self, request):
        self.token = "synthetic-refreshed"
        self.expiry = (datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    value = cli.authorize(path, config, interactive=False)
    assert value.token == "synthetic-refreshed"
    assert cli.secure_json(path / "token.json")["token"] == "synthetic-refreshed"


def test_missing_token_does_not_open_browser_during_test(google_home):
    path, config = google_home
    with pytest.raises(DriveError, match="AUTHORIZATION_REQUIRED"):
        cli.authorize(path, config, interactive=False)


def test_token_endpoint_or_identity_cannot_be_substituted(google_home):
    path, config = google_home
    saved = json.loads(credentials().to_json())
    saved["token_uri"] = "https://untrusted.invalid/token"
    private_write(path / "token.json", json.dumps(saved))
    with pytest.raises(DriveError, match="CONFIGURATION_MISMATCH"):
        cli.authorize(path, config, interactive=False)


def test_real_oauth_library_rejects_state_mismatch_and_uses_s256(google_home):
    from urllib.parse import parse_qs, urlsplit

    from google_auth_oauthlib.flow import InstalledAppFlow
    from oauthlib.oauth2 import MismatchingStateError

    _, config = google_home
    flow = InstalledAppFlow.from_client_config(
        config,
        scopes=[SCOPE],
        autogenerate_code_verifier=True,
    )
    flow.redirect_uri = "http://127.0.0.1:12345/"
    url, state = flow.authorization_url(access_type="offline")
    parameters = parse_qs(urlsplit(url).query)
    assert parameters["code_challenge_method"] == ["S256"]
    assert parameters["state"] == [state] and len(state) >= 20
    assert parameters["scope"] == [SCOPE]
    try:
        with pytest.raises(MismatchingStateError):
            flow.fetch_token(
                authorization_response="https://127.0.0.1:12345/?code=synthetic&state=incorrect"
            )
    finally:
        flow.oauth2session.close()


def test_broader_granted_scope_is_not_accepted():
    value = credentials()
    value._granted_scopes = [SCOPE, "https://www.googleapis.com/auth/drive"]
    with pytest.raises(DriveError, match="SCOPE"):
        cli.verify_scopes(value)


def test_explicit_reauthorization_failure_preserves_existing_tokens(google_home, monkeypatch):
    path, config = google_home
    original = credentials().to_json()
    private_write(path / "token.json", original)
    session = SimpleNamespace(trust_env=True, request=Mock(), close=Mock())
    flow = SimpleNamespace(oauth2session=session, run_local_server=Mock(side_effect=ValueError))
    monkeypatch.setattr(cli.InstalledAppFlow, "from_client_config", Mock(return_value=flow))
    with pytest.raises(ValueError):
        cli.authorize(path, config, interactive=True, force=True)
    assert (path / "token.json").read_text() == original
    assert session.close.called


def test_no_forced_browser_authorization_from_test_command(google_home):
    path, config = google_home
    with pytest.raises(DriveError, match="EXPLICIT_AUTHORIZATION"):
        cli.authorize(path, config, interactive=False, force=True)
