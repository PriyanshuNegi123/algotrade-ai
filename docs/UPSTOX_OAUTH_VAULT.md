# Local encrypted Upstox OAuth token vault

Status: opt-in storage component implemented and tested with synthetic credentials.
It is connected to the opt-in HTTP callback flow described in UPSTOX_OAUTH_BROWSER.md;
it is not an active broker credential or mounted in the current Compose deployment.
No real vault/key/token has been initialized. The saved OAuth app settings remain missing
at this iteration's local check. End-to-end OAuth and Phase2 remain incomplete.

## Storage boundary

`backend/app/brokers/oauth_store.py` exposes OAuthTokenStore.save/load/status for trusted
backend callers. A future integration must pass a fixed, canonical, server-controlled path
under ignored `.local/upstox/`, not a path taken from an HTTP request. The parent must already
exist. Creation is explicit on first save or prepare() from an authenticated,CSRF-protected OAuth
start. Preparing storage creates only its key/lock and validates existing data before broker
consent. Constructing a store or reading status never initializes missing storage.

Files are a dedicated32-byte `vault.key`, encrypted `token.enc` and `vault.lock`. The final
directory must be owned by the process user and mode0700; files must be regular, owned by
that user, mode0600 and have one hard link. Symlink paths/ancestors, hard-linked or insecure
files are refused. Operations inside the opened directory use directory-relative descriptors,
no-follow opens and a nonblocking exclusive advisory lock. Unix local filesystems are the
supported environment; this is not a distributed/cloud database or lock service.

AES-256-GCM uses fresh12-byte random nonces, a versioned format header and associated data
bound to the app configuration fingerprint. The key is separate from the PostgreSQL backup
key and Google credentials. The encrypted payload contains only access token and local
request/receipt/expiry timestamps; no profile, client secret or callback code is stored.
Ciphertext is bounded16KiB. Keys and ciphertext live under the same OS permissions boundary;
this does not protect against compromise of the owning account or full device access.

## Lifecycle and failure behavior

Save validates token syntax, aware timestamps, receipt ordering, no future receipt time and
conservative documented daily cutoff before initializing files. Load reauthenticates and
rechecks expiry/clock on every access. A newer valid token may replace an expired one for
the same app; an older token cannot replace a newer one. Expired ciphertext is retained
but never returned as usable. There is no automatic refresh, rotation, purge or deletion.

A missing/corrupt key is never silently regenerated if ciphertext or unknown artifacts
exist. Changed app ID, secret or callback fails authentication and cannot overwrite the
existing vault. Configuration changes/key recovery require a separately reviewed operator
workflow; the component does not offer an automatic reset or delete command.

Writes use a unique private ciphertext-only temporary file, file fsync, atomic same-directory
replace and directory fsync. Failure before replace preserves the prior token. A directory
sync failure after replace reports failure even though the new ciphertext may already be
published; it cannot promise rollback/durable survival. Recheck status before any retry.
Only a temporary file created by that operation is cleaned up; collisions/unknown files
and unrelated targets are preserved. Exceptions expose fixed codes, not raw paths or errors.

Status returns only a fixed state, expiry when usable and false broker/live flags. It does
not prove broker acceptance, grant trading permission or expose token/key values. The
existing `scripts.check_upstox_oauth` checks app configuration only; it does not inspect this
physical store or initialize it. SecretStr remains the in-process token representation.

## Deployment and remaining gates

The implemented backend authorizes the administrator before storage status/start/finish.
The callback finish also verifies revocation,CSRF/origin and browser binding before saving.
The loaded SecretStr is server-only;never return it or the key in HTTP responses or log dumps.
The backend must use a dedicated durable
private directory/volume writable by the backend UID. An optional Compose overlay now
provides this mount; see UPSTOX_OAUTH_BROWSER.md for lifecycle and verification. Operational
settings, existing volumes and real browser authorization remain unchanged. The HTTP/UI flow
now exists as described in UPSTOX_OAUTH_BROWSER.md. Existing Strict
administrator cookies and the Analytics-only broker adapter remain unchanged.

Vault files are not included in the PostgreSQL backup or Drive recovery kit. Nothing from
this vault is uploaded automatically. Device/key loss requires fresh OAuth authorization;
the existing backup/Drive recovery keys are not substitutes. PostgreSQL stays operational.

## Verification

33synthetic security cases cover encryption/randomization, file modes, metadata-only status,
missing-store reads, expiry/clock/cutoff bounds, app changes, tampering/size limits, missing/
corrupt keys, insecure files/directories, symlinks/hardlinks, lock contention, stale replacement,
atomic-write faults, collision preservation and post-replace durability uncertainty.
No real account/token, network request or operational database is used by these tests.

Primary API references: [AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM),
[Python flock](https://docs.python.org/3.12/library/fcntl.html#fcntl.flock) and
[Python replace](https://docs.python.org/3.12/library/os.html#os.replace).
