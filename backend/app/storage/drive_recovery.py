"""Create-only encrypted recovery kits using the existing drive.file archive folder."""

import hashlib
import json
import re
from typing import Any
from uuid import uuid4

from backend.app.storage.backup_crypto import BackupError
from backend.app.storage.google_drive import API, UPLOAD, DriveArchive, file_id
from backend.app.storage.recovery_kit import MAX_KIT, envelope


class DriveRecovery(DriveArchive):
    def upload(self, value: bytes) -> dict[str, Any]:
        envelope(value)
        folder, _ = self.archive_folder()
        digest = hashlib.sha256(value).hexdigest()
        name = "algotrade-recovery-kit-" + uuid4().hex + ".atrecovery"
        metadata = json.dumps(
            {
                "name": name,
                "mimeType": "application/octet-stream",
                "parents": [folder],
                "appProperties": {"algotrade_recovery_kit": "v1", "cipher_sha256": digest},
            }
        ).encode()
        boundary = "algotrade-" + uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + value
            + f"\r\n--{boundary}--\r\n".encode()
        )
        uploaded = self._json(
            "POST",
            UPLOAD,
            params={"uploadType": "multipart", "fields": "id"},
            content=body,
            headers={"Content-Type": "multipart/related; boundary=" + boundary},
        )
        return {
            "file_id": file_id(uploaded.get("id")),
            "folder_id": folder,
            "file_name": name,
            "cipher_sha256": digest,
            "encrypted_bytes": len(value),
            "state": "UPLOADED_NOT_VERIFIED",
        }

    def download(self, receipt: dict[str, Any]) -> bytes:
        identity, folder = file_id(receipt.get("file_id")), file_id(receipt.get("folder_id"))
        size, digest = receipt.get("encrypted_bytes"), receipt.get("cipher_sha256")
        if (
            not isinstance(size, int)
            or not 0 < size <= MAX_KIT
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise BackupError("RECOVERY_KIT_RECEIPT_INVALID")
        info = self._json(
            "GET",
            API + "/files/" + identity,
            params={
                "fields": "parents,mimeType,size,appProperties,sha256Checksum,capabilities",
            },
        )
        capabilities = info.get("capabilities")
        if (
            info.get("parents") != [folder]
            or info.get("size") != str(size)
            or info.get("mimeType") != "application/octet-stream"
            or info.get("appProperties")
            != {"algotrade_recovery_kit": "v1", "cipher_sha256": digest}
            or info.get("sha256Checksum", digest) != digest
            or not isinstance(capabilities, dict)
            or capabilities.get("canDownload") is not True
        ):
            raise BackupError("RECOVERY_KIT_CLOUD_METADATA_MISMATCH")
        value = self._request(
            "GET", API + "/files/" + identity, limit=size, params={"alt": "media"}
        )
        if len(value) != size or hashlib.sha256(value).hexdigest() != digest:
            raise BackupError("RECOVERY_KIT_CLOUD_SHA256_MISMATCH")
        envelope(value)
        return value
