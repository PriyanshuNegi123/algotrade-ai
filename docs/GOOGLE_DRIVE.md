# Google Drive desktop OAuth and synthetic storage check

Google Drive is an archive/backup destination. PostgreSQL remains the operational database.
OAuth/synthetic checks and manual encrypted PostgreSQL cloud backups with isolated restore
verification are implemented; see [BACKUPS.md](BACKUPS.md). The three-day schedule is documented in BACKUP_SCHEDULE.md; separately authorized passphrase-encrypted recovery material is
documented in [RECOVERY_KIT.md](RECOVERY_KIT.md). Live trading remains off.

## Configuration and commands

Save your own Google OAuth Desktop JSON as `.local/google/credentials.json`. Enable the
Google Drive API for that Google Cloud project and configure its OAuth consent audience.
For an app in testing, authorize using an account allowed as a test user.
Never paste the JSON, callback URL, authorization code or token values into chat or logs.

```sh
uv sync --locked
uv run python -m scripts.google_drive verify-config
uv run python -m scripts.google_drive authorize
uv run python -m scripts.google_drive test
```

Authorization opens the default browser and listens on an ephemeral127.0.0.1 port for
up to300seconds. Google's maintained OAuth library generates state and S256 PKCE; it
validates the callback state and exchanges the code through the fixed Google token endpoint.
Consent requests offline access and exactly `https://www.googleapis.com/auth/drive.file`.
Broader requested/granted scopes are rejected. The auth URL and callback query are not
printed; credential-bearing third-party debug logging is suppressed for this CLI.
The browser's acknowledgement only confirms receipt of the callback; terminal AUTHORIZED
confirms the token exchange, scope checks and secure local save succeeded.

Tokens live in `.local/google/token.json` with mode0600 inside mode0700`.local/google/`.
Refresh reuses Google's library with bounded requests; updates are atomic. The process
refuses unsafe/symlinked files/directories, substituted credential endpoints/client identity,
broader token-file scopes and concurrent operations. OAuth/Drive requests disable environment
proxies and redirects; failures are safe reason codes with no remote body or token values.
The existing `.local/` Git exclusion covers credentials,tokens,lock and private receipt.
Revoked/expired refresh access may require `authorize --reauthorize`. This explicit option
opens new consent and preserves the old token file unless new authorization succeeds. The test command
does not open a browser automatically or silently replace a saved credential.

## Folder choice and test behavior

Under drive.file, the app does not get general visibility into existing Drive folders.
We deliberately create **AlgoTrade-AI-Storage (app archive)** with the app-private property
`algotrade_archive=v1`. Existing `AlgoTrade-AI-Storage` and other user files are untouched.
Later use of an existing folder requires explicit file-picker authorization; typing its name
is not authorization. The CLI reuses only a single visible folder with the exact app marker;
ambiguous or invalid matches fail closed rather than choosing an arbitrary folder.

The test uploads only internally generated JSON named
`algotrade-synthetic-storage-check-<random>.json`. There is no local-file argument or database
export path. Drive v3 multipart creation writes a new file; metadata/parent/download capability
checks precede a bounded media download. SHA-256 and byte length must match the generated
content; a reported server checksum, if present, must match too. The small test file is
**retained**. The integration implements no delete, update, overwrite or permission-sharing
operation. Failed network POSTs are not automatically retried because completion may be
uncertain. Do not infer an encrypted backup/restore capability from this test.

Successful real verification writes `.local/google/storage-test.json` (mode0600), containing
file/folder IDs, filename, byte count and checksums, but no credentials. Summary output omits
IDs and user identity. Actual acceptance status is recorded in agent_memory/HANDOFF.md.
If authorization or API access fails, no cloud-test success is claimed.

## Official references

- [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Folder creation](https://developers.google.com/workspace/drive/api/guides/folder)
- [Multipart uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
- [Blob downloads](https://developers.google.com/workspace/drive/api/guides/manage-downloads)

Google calls drive.file a non-sensitive per-file scope; it is narrower than the restricted
full-Drive scope. The integration uses this narrower scope despite the colloquial use of
"restricted" to mean limited access.

## Actual acceptance — 2026-11-09T14:48:12.940990+00:00 UTC

Browser authorization succeeded with exactly drive.file. The app archive folder was created
and one116-byte synthetic file was uploaded/downloaded and retained. SHA256:
`c49d466f6d206233385ae269167bb218b3b980238a3900f51337e8041ca17a26`.
Both computed digests match;no existing user file changed. Credentials/token/receipt file
permissions are0600 and the Google directory0700. Real identifiers remain in the ignored
local receipt. OAuth/state/PKCE/refresh/folder/integrity/bounds tests pass(23cases);exact
staged full PostgreSQL suite397passed,zero skips. Actual refresh-token issuance verified;
expiry-refresh behavior tested synthetically rather than forcing unnecessary account refresh.
