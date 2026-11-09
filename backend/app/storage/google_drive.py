"""Bounded Drive v3 synthetic storage test. No delete, update or arbitrary-file upload."""

import hashlib
import json
import re
from typing import Any
from uuid import uuid4

import httpx

SCOPE = "https://www.googleapis.com/auth/drive.file"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
FOLDER_NAME = "AlgoTrade-AI-Storage (app archive)"
MARKER = {"algotrade_archive": "v1"}
MAX_TEST_BYTES = 4096


class DriveError(Exception):
    """Only fixed safe reason codes, never remote bodies or credential values."""


def file_id(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value) is None:
        raise DriveError("DRIVE_INVALID_FILE_ID")
    return value


class DriveArchive:
    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None):
        if not token or any(character in token for character in "\r\n"):
            raise DriveError("DRIVE_ACCESS_TOKEN_REQUIRED")
        self._client = httpx.Client(
            headers={"Authorization": "Bearer " + token},
            transport=transport,
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, url: str, limit: int = 65_536, **kwargs: Any) -> bytes:
        try:
            with self._client.stream(method, url, **kwargs) as response:
                if response.status_code not in {200, 201}:
                    code = {
                        401: "DRIVE_AUTH_REQUIRED",
                        403: "DRIVE_ACCESS_DENIED_OR_API_DISABLED",
                        429: "DRIVE_RATE_LIMITED",
                    }.get(response.status_code, "DRIVE_REQUEST_FAILED")
                    raise DriveError(code)
                data = bytearray()
                for chunk in response.iter_bytes(chunk_size=4096):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise DriveError("DRIVE_RESPONSE_LIMIT")
                return bytes(data)
        except httpx.HTTPError:
            raise DriveError("DRIVE_NETWORK_UNAVAILABLE") from None

    def _json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            value = json.loads(self._request(method, url, **kwargs))
        except (ValueError, UnicodeError):
            raise DriveError("DRIVE_INVALID_RESPONSE") from None
        if not isinstance(value, dict):
            raise DriveError("DRIVE_INVALID_RESPONSE")
        return value

    def archive_folder(self) -> tuple[str, bool]:
        result = self._json(
            "GET",
            API + "/files",
            params={
                "q": "trashed = false and mimeType = 'application/vnd.google-apps.folder' "
                "and appProperties has { key='algotrade_archive' and value='v1' }",
                "pageSize": 2,
                "fields": "nextPageToken,files(id,mimeType,appProperties,trashed)",
            },
        )
        folders = result.get("files")
        if not isinstance(folders, list) or len(folders) > 1 or result.get("nextPageToken"):
            raise DriveError("DRIVE_ARCHIVE_FOLDER_AMBIGUOUS")
        if folders:
            folder = folders[0]
            if (
                not isinstance(folder, dict)
                or folder.get("mimeType") != FOLDER_MIME
                or folder.get("appProperties") != MARKER
                or folder.get("trashed") is not False
            ):
                raise DriveError("DRIVE_ARCHIVE_FOLDER_INVALID")
            return file_id(folder.get("id")), False
        created = self._json(
            "POST",
            API + "/files",
            params={"fields": "id"},
            json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME, "appProperties": MARKER},
        )
        return file_id(created.get("id")), True

    def synthetic_round_trip(self) -> dict[str, Any]:
        folder, created = self.archive_folder()
        nonce = uuid4().hex
        payload = json.dumps(
            {
                "kind": "SYNTHETIC_STORAGE_CHECK",
                "nonce": nonce,
                "contains_real_market_data": False,
            },
            sort_keys=True,
        ).encode()
        expected = hashlib.sha256(payload).hexdigest()
        name = f"algotrade-synthetic-storage-check-{nonce}.json"
        metadata = json.dumps(
            {
                "name": name,
                "mimeType": "application/json",
                "parents": [folder],
                "appProperties": {"algotrade_synthetic_sha256": expected},
            }
        ).encode()
        boundary = "algotrade-" + uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode()
            + payload
            + f"\r\n--{boundary}--\r\n".encode()
        )
        uploaded = self._json(
            "POST",
            UPLOAD,
            params={"uploadType": "multipart", "fields": "id"},
            content=body,
            headers={"Content-Type": "multipart/related; boundary=" + boundary},
        )
        identity = file_id(uploaded.get("id"))
        info = self._json(
            "GET",
            API + "/files/" + identity,
            params={"fields": "size,parents,mimeType,appProperties,sha256Checksum,capabilities"},
        )
        capabilities = info.get("capabilities")
        if (
            info.get("parents") != [folder]
            or info.get("mimeType") != "application/json"
            or info.get("appProperties") != {"algotrade_synthetic_sha256": expected}
            or info.get("size") != str(len(payload))
            or not isinstance(capabilities, dict)
            or capabilities.get("canDownload") is not True
            or info.get("sha256Checksum", expected) != expected
        ):
            raise DriveError("DRIVE_UPLOADED_METADATA_MISMATCH")
        downloaded = self._request(
            "GET",
            API + "/files/" + identity,
            limit=MAX_TEST_BYTES,
            params={"alt": "media"},
        )
        actual = hashlib.sha256(downloaded).hexdigest()
        if actual != expected or len(downloaded) != len(payload):
            raise DriveError("DRIVE_SHA256_MISMATCH")
        return {
            "state": "VERIFIED",
            "scope": SCOPE,
            "folder_id": folder,
            "folder_created": created,
            "file_id": identity,
            "file_name": name,
            "bytes": len(payload),
            "upload_sha256": expected,
            "download_sha256": actual,
            "synthetic_only": True,
            "file_retained": True,
            "live_enabled": False,
        }
