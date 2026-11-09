"""Create-only encrypted Drive archives; session URLs and plaintext never logged."""

import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from backend.app.storage.backup_crypto import MAX_ENCRYPTED, BackupError, encrypted_envelope
from backend.app.storage.google_drive import API, UPLOAD, DriveArchive, DriveError, file_id


def upload_session(value: str) -> str:
    parsed = urlsplit(value)
    if (
        len(value) > 8192
        or parsed.scheme != "https"
        or parsed.netloc != "www.googleapis.com"
        or parsed.path != "/upload/drive/v3/files"
        or parsed.fragment
        or parse_qs(parsed.query).get("uploadType") != ["resumable"]
        or not parse_qs(parsed.query).get("upload_id")
    ):
        raise BackupError("BACKUP_UPLOAD_SESSION_REJECTED")
    return value


class DriveBackup(DriveArchive):
    def upload(self, ciphertext: bytes, name: str) -> dict[str, Any]:
        encrypted_envelope(ciphertext)  # Plaintext/key/env file uploads are not accepted.
        if re.fullmatch(r"algotrade-pg-backup-[0-9a-f]{32}\.atbackup", name) is None:
            raise BackupError("BACKUP_INVALID_ARCHIVE_NAME")
        folder, _ = self.archive_folder()
        digest = hashlib.sha256(ciphertext).hexdigest()
        properties = {"algotrade_encrypted_backup": "v1", "cipher_sha256": digest}
        try:
            with self._client.stream(
                "POST",
                UPLOAD,
                params={"uploadType": "resumable", "fields": "id"},
                json={
                    "name": name,
                    "mimeType": "application/octet-stream",
                    "parents": [folder],
                    "appProperties": properties,
                },
                headers={
                    "X-Upload-Content-Type": "application/octet-stream",
                    "X-Upload-Content-Length": str(len(ciphertext)),
                },
            ) as response:
                if response.status_code != 200:
                    raise DriveError("BACKUP_UPLOAD_INITIATION_FAILED")
                session = upload_session(response.headers.get("Location", ""))
        except httpx.HTTPError:
            raise DriveError("BACKUP_UPLOAD_NETWORK_FAILED") from None
        uploaded = self._json(
            "PUT",
            session,
            content=ciphertext,
            headers={"Content-Type": "application/octet-stream"},
        )
        return {
            "state": "UPLOADED_NOT_VERIFIED",
            "file_id": file_id(uploaded.get("id")),
            "folder_id": folder,
            "cipher_sha256": digest,
            "encrypted_bytes": len(ciphertext),
            "file_name": name,
        }

    def download(self, receipt: dict[str, Any]) -> bytes:
        identity, folder = file_id(receipt.get("file_id")), file_id(receipt.get("folder_id"))
        size = receipt.get("encrypted_bytes")
        digest = receipt.get("cipher_sha256")
        if (
            not isinstance(size, int)
            or not 0 < size <= MAX_ENCRYPTED
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise BackupError("BACKUP_INVALID_RECEIPT")
        info = self._json(
            "GET",
            API + "/files/" + identity,
            params={"fields": "parents,mimeType,appProperties,size,sha256Checksum,capabilities"},
        )
        capabilities = info.get("capabilities")
        if (
            info.get("parents") != [folder]
            or info.get("mimeType") != "application/octet-stream"
            or info.get("appProperties")
            != {
                "algotrade_encrypted_backup": "v1",
                "cipher_sha256": digest,
            }
            or info.get("size") != str(size)
            or not isinstance(capabilities, dict)
            or capabilities.get("canDownload") is not True
            or info.get("sha256Checksum", digest) != digest
        ):
            raise BackupError("BACKUP_CLOUD_METADATA_MISMATCH")
        value = self._request(
            "GET", API + "/files/" + identity, limit=size, params={"alt": "media"}
        )
        if len(value) != size or hashlib.sha256(value).hexdigest() != digest:
            raise BackupError("BACKUP_CLOUD_SHA256_MISMATCH")
        encrypted_envelope(value)
        return value
