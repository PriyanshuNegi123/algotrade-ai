# Passphrase-protected Drive recovery kit

The optional recovery kit contains the existing backup encryption key and a verified
backup receipt, encrypted before upload with a separate operator-entered passphrase.
Google tokens, OAuth client secrets, broker credentials and environment files are excluded.
PostgreSQL remains the operational database. This workflow never restores into it.

## Create and verify

From the project directory, with Docker running and a verified backup already available:

```sh
uv run python -m scripts.recovery_kit create
uv run python -m scripts.recovery_kit verify-cloud
uv run python -m scripts.backup_job status
```

On this Mac, append `--dialog` for native hidden prompts. Creation asks twice; verification
asks once. Use a unique, strong passphrase (at least16characters; several unrelated words
are preferable). Never enter it in chat, command arguments, environment variables or source.
The passphrase is not saved. Preserve it independently of this Mac and Google account.
A forgotten passphrase cannot be reset to decrypt an existing kit. Do not use your Google
or trading password. A physical offline recovery copy remains optional and unconfirmed.

A fresh16-byte salt derives a256-bit wrapping key using Argon2id with64MiB memory,
3iterations and4lanes. AES-256-GCM uses a fresh12-byte nonce and authenticated version/salt.
Version1 fixes KDF resource limits; encrypted kits are bounded to64KiB. Only ciphertext
is uploaded, create-only, to the existing app-owned archive folder using `drive.file`.
No existing Drive file is overwritten, deleted or shared. No local ciphertext cache is kept.
The original data key remains unchanged and protected locally; private mode0600 receipts
record cloud identities, ciphertext SHA-256 and restore evidence, never the passphrase.

Creation downloads the uploaded kit, unwraps its key, downloads the referenced backup,
authenticates/decrypts it and restores into a fresh network-isolated disposable PostgreSQL
container. Verification uses the recovered key, not the original local key file or source DB.
The restore checks schema, stored archive/event hashes, a non-superuser role and zero login
sessions. Only after success is `.local/backups/recovery-kit.json` marked RECOVERY_VERIFIED.
An upload interrupted before verification retains a private pending receipt; retry with
`verify-pending` rather than creating another kit. Wrong passwords and tampering fail closed.

The backup health command reports a matching locally verified kit separately from an offline
copy; it does not contact Drive or guarantee present cloud access. Invalid optional kit
receipts do not interrupt the three-day backup schedule. New keys/schema changes require
fresh kit verification. No automatic key rotation or cloud retention deletion is introduced.

## Recovery without original local secrets

Keep access to the Google account, this source code and compatible PostgreSQL Docker image.
The kit embeds the immutable image ID used by the verified backup. Preserve that image or
rebuild/retrieve a separately verified compatible image before recovery; it is not uploaded
as part of the kit. The script refuses arbitrary pulls and never changes the operational DB.

If the Mac's local key/Google OAuth token files are lost, use Drive's normal browser interface
to download the app-owned `.atrecovery` file and its `.atbackup` archive. Then:

```sh
uv run python -m scripts.recovery_kit recover-local \
  --kit-file /path/to/downloaded.atrecovery \
  --archive-file /path/to/downloaded.atbackup
```

This action needs neither the original data key nor Google API credentials. It verifies the
backup using the recovered key and authenticated internal manifest, then performs only an
isolated restore drill. It also accepts newer authenticated backups encrypted with the same
key and supported schema. The kit's embedded receipt anchors its creation-time backup;
retain that backup. Recreate the kit after key rotation, schema changes or incompatible
PostgreSQL upgrades. Keep earlier kits/archives until a separate retention policy is approved.
Production recovery/cutover and importing a recovered key are separate reviewed operations.

API references: [Google Drive multipart uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
and [cryptography Argon2id](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#argon2id).
