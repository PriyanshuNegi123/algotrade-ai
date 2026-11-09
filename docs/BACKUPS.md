# Encrypted PostgreSQL backups and isolated restore checks

PostgreSQL remains the operational database. Backups can run explicitly or through the
user-requested three-day cloud schedule; see BACKUP_SCHEDULE.md. No workflow restores over
the running database or starts trading.

## Commands

Keep the private local app/database running for creation and Google OAuth authorized:

```sh
uv run python -m scripts.backup_postgres backup
uv run python -m scripts.backup_postgres verify-latest
```

`backup` validates the local Unix Docker engine and exact Compose working directory,
serializes against local capture/bootstrap, and exports the app database with pg_dump custom
format. The consistent read-only export excludes data from public.admin_sessions and omits
owner/ACL restoration. Environment files, Google credentials/tokens and encryption keys are
not part of the database dump. Production rows/settings are not modified.

A first backup creates a random256-bit key at `.local/backups/recovery.key` (mode0600),
inside mode0700`.local/backups/`. Existing keys are never rotated/replaced silently.
If a key is missing while older backup artifacts exist, creation fails rather than starting
an unrelated key chain. `verify-latest` requires the existing key and never creates one.

**Keep a separate secure offline copy of the recovery key and verified receipt.** Neither
is uploaded by this workflow. Losing the only key makes the encrypted archives unrecoverable.
Also preserve access to the original Google OAuth project/account and its local configuration.
Do not paste keys into chat or put plaintext recovery material in Drive. File permissions
are a local boundary; encrypted key escrow/OS keychain integration is future work.

## Encryption and cloud transfer

The custom dump exists in process memory only. AES-256-GCM uses a new random96-bit nonce
per archive and authenticates a versioned format header. An encrypted internal manifest
records dump SHA256,size,schema revision and excluded-session policy. Wrong keys, modified
headers/nonces/ciphertext,tags,invalid manifests or unsupported schema revisions fail closed.
The cryptography library performs encryption;no custom cryptographic algorithm is used.

Ciphertext stays in bounded process memory; new backups do not create local `.atbackup`
files. Drive receives only the encrypted blob in the existing app-created archive folder. Resumable API creation uses a fixed Google
endpoint;the returned session URL is checked for HTTPS,exact host/path and upload ID before
any token-bearing PUT. No redirect, automatic POST retry, overwrite, delete or sharing
operation is implemented. Google OAuth remains drive.file.

The cloud copy is checked for app marker,parent,MIME,size,ciphertext SHA256 and download
capability. Downloaded bytes must match the private receipt hash before authenticated
decryption. The key and plaintext digest/manifest are not published as Drive metadata.
Only generated backup filenames are accepted;no arbitrary local-file upload path is exposed.

## Restore verification

Every backup downloads its cloud copy and restores the decrypted custom archive into a
new labelled Docker container, using the same locally installed PostgreSQL image.
The target has network=none,no host mounts/ports,a read-only root filesystem,tmpfs database
storage and explicit memory/CPU/PID limits. A temporary LOGIN role is NOSUPERUSER,
NOCREATEDB,NOCREATEROLE,NOBYPASSRLS;restore uses TCP/password authentication inside that
isolated container,exit-on-error and one transaction. Passwords go over stdin,not argv.

Verification checks schema revision,zero restored login sessions,table counts,catalog/history/
chain archive hashes and every bounded observation event's canonical SHA256. The target
container and temporary volumes are removed by its unique per-drill label,even on failure.
No live database is a permitted restore destination. A real production cutover/recovery
procedure is separate work and requires its own reviewed target and plan.

After success, private per-backup receipts and `.local/backups/latest.json` say
RESTORE_VERIFIED. A failed attempt cannot replace the last verified latest receipt;an
uploaded but unverified file is retained with its initial receipt,not deleted.
`verify-latest` needs only the local engine,matching cached PostgreSQL image,key,receipt
and authorized Google access;it does not consult the working database. A new recovery
machine must install a compatible approved image;automatic image selection/pulling is
not implemented. Keep the private receipt's image reference with recovery material.

## Bounds and limitations

Custom dump limit32MiB;ciphertext limit32MiB+4KiB. This initial workflow uses bounded
in-memory authenticated encryption and a single data PUT within a resumable session.
It fails rather than silently truncating larger data. Export/network/restore have timeouts.
Future large archives require separately reviewed streaming/chunking and resource policies.
The three-day schedule is documented separately. No cloud retention deletion,incremental
backup,key rotation,off-device key escrow or complete disaster cutover is implemented.
Existing Drive files are retained. `prune-local` removes only matching app-owned local
ciphertext after a fresh successful cloud download/decryption/hash comparison;unknown,
unverified or changed files are kept. Keys and receipts are never pruned. Scope/authentication
errors require the documented Google reauthorization flow,not broader Drive permissions.

## Actual local/cloud verification

A4,870,741-byte encrypted database backup was uploaded/downloaded and restored successfully.
The independent second check blocked source-database lookup and also passed. Recovered:
2catalogs/13,314instruments,1history batch/75candles,1chain snapshot/270legs,2captures,
2observation sessions/9events. Archive hash errors0;all9event hashes verified. Restored
role was not superuser;login-session rows0. Temporary targets removed;operational DB kept.
Private receipt contains the actual file ID/checksums and timestamps;keys/IDs are not copied
into this guide. Local secret files and receipts remain Git-ignored.

Primary references:
[pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html),
[AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/),
[Drive resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads).

Cloud-first update: new job execution and isolated restore verified without a local archive
file; one old verified cache file removed, reclaiming4,870,741bytes. No Drive file deleted.
See BACKUP_SCHEDULE.md for the installed three-day policy and local health commands.
