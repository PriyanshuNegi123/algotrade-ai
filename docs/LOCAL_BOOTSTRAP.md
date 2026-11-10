# Secure local runtime bootstrap

Keep Docker Desktop running. From the project directory:

```sh
uv sync --locked
uv run python -m scripts.bootstrap_local
```

The command creates missing local settings, builds the app, starts private PostgreSQL,
applies migrations and verifies readiness, anonymous access denial, administrator login,
OBSERVATION mode, private capture preflight and CSRF logout. It never contacts the broker,
imports metadata or starts recording. Readiness does not authorize trading.

Open http://127.0.0.1:8000. Retrieve your generated administrator password locally from
`.local/runtime/admin-password.txt`; never paste it into chat. The password and `.env` use
mode 0600; `.local/runtime` uses 0700. Both locations and temporary secret files are excluded
from Git and the Docker build context. The plaintext password file is protected local storage,
not an encrypted vault. Existing administrator hashes are preserved; without a matching local
password file, readiness is checked but the command reports `login_verified: false`.

On first setup, `--port 8001` selects another unprivileged loopback port and matching origins.
On subsequent runs the existing port and settings are preserved. Conflicting modes, external
DB configuration, credential mismatches, duplicate environment keys and unsafe secret-file
links are rejected. Missing DB credentials for an existing target volume are never regenerated.
An advisory lock prevents simultaneous bootstrap commands in this workspace. Only a local
Unix-socket Linux Docker engine is accepted. Errors use fixed codes without dumping secrets,
expanded Compose configuration or raw subprocess output. Inspect failures locally with care.

The stable Compose project is `algotrade-ai-local`, unless already configured otherwise.
The app binds to 127.0.0.1; the database has no published port. Database credentials and an
Argon2 administrator hash are generated only when missing. Re-running does not rotate them
or reset data. If startup fails, protected configuration and any persistent resources remain
for repair; the helper does not destroy volumes. Never use `docker compose down -v` against
important data. Keep Docker Desktop running while using the app.

## Optional OAuth storage lifecycle

For the first explicit opt-in to private OAuth storage:

```sh
uv run python -m scripts.configure_upstox_oauth
uv run python -m scripts.bootstrap_local --oauth-vault
```

The setup helper saves the registered app settings through a hidden local secret prompt;
see [OAuth configuration](UPSTOX_OAUTH.md). Bootstrap then adds `docker-compose.oauth.yml`
and the project's dedicated `upstox_oauth` named
volume. It does not configure the registered app or perform consent. No key is created by
bootstrap; an authenticated authorization start prepares the vault separately. The result
includes `oauth_vault_enabled`. On subsequent runs, bootstrap detects the exact
`<project>_upstox_oauth` volume and retains the overlay even without the flag. A volume for
another project or a similarly named volume does not enable it. Detection failures stop
startup rather than falling back to the base deployment. No separate mode marker is stored.

Bootstrap validates the merged storage target, local project volume, writable vault mount,
read-only root filesystem, dropped capabilities and no-new-privileges setting before `up`.
Bind mounts, external/remote volumes, subpaths, disabled volume initialization and mounting
the vault into migrations are rejected. Setting UPSTOX_OAUTH_VAULT_DIR without opting in
or an existing project volume is rejected rather than starting with unusable storage.
The overlay controls the container path; bootstrap does not rewrite this setting in `.env`.

There is no automatic opt-out or deletion. Keep the same project name and volume for future
rebuilds. Manual Compose commands must also include both files; bypassing bootstrap with a
base-only command can omit the mount. Do not remove the operational named volumes.
Registered callback settings and genuine consent remain separate gates. See
[OAuth browser setup](UPSTOX_OAUTH_BROWSER.md) for boundaries and recovery limitations.

Verify the lifecycle with disposable credentials and containers, without touching `.env`:

```sh
uv run python -m scripts.verify_compose --bootstrap --oauth-vault
uv run python -m scripts.verify_compose --bootstrap
```

The OAuth variant replaces its test application, deliberately omits the opt-in flag on the
second bootstrap and verifies that encrypted synthetic storage still decrypts. Both variants
exercise real readiness, administrator login/logout and observation preflight. Tests never
contact a broker or start market recording. Only their own containers/volumes are removed.

The generated DATABASE_URL uses the internal hostname `db`. Host-based database CLI commands
cannot resolve that private endpoint. Use authenticated dashboard controls/preflight for this
Compose deployment. The bootstrap checks readiness inside the running application through
HTTP; host CLI failure is not evidence that the private database is down.

Broker configuration remains a separate, optional local operation:

```sh
uv run python -m scripts.configure_upstox
uv run python -m scripts.bootstrap_local
```

The helper prompts without echoing the Analytics credential. Never supply credentials in
chat, command arguments or browser forms. A fresh catalog and a valid server credential are
required before any explicit bounded capture attempt. No automatic capture is configured.
Local Compose uses the PostgreSQL image's initialization user; production role separation,
TLS, encrypted storage/backups and security hardening remain pending. This is local development.

## Subsequent catalog onboarding

On2026-11-06, the running local deployment imported and verified6,504 public instruments.
The latest verified preflight now blocks only on CREDENTIAL_MISSING. Freshness can expire;
see [current setup and next steps](CONNECTION_READINESS.md) before any future attempt.

## 2026-11-06T14:52:41.408698+00:00 — P2-003N administrator rotation COMPLETE

User explicitly authorized rotation of the administrator credential exposed in chat. One-time
local maintenance completed without printing/passing secrets in argv or reports. Stopped sole
app before session deletion; transactionally revoked4sessions, confirmed0, generated random
replacement/Argon2 hash, protected per-file atomic replacement of .env and local password,
then recreated app through existing bootstrap. Candidate password file removed after success.
Actual old-password POST401, pre-rotation cookie GET401, replacement login200/private GET200
and CSRF logout204. Bootstrap readiness/login/local preflight passed; zero blockers. Final
admin_sessions0. Password at .local/runtime/admin-password.txt, mode0600; .env0600, runtime0700.
Retrieve it only locally and sign in again; never reproduce the old/new password in records.

Verified unchanged parsed configuration except ADMIN_PASSWORD_HASH, including broker token,
expiry, DB credentials and OBSERVATION settings. Read-only DB manifests (counts plus row
fingerprints compared in memory, not logged) match before/after for catalogs/history/research
and schema revision. Retained1instrument snapshot,6504instruments,1history batch,75candles,
0observation sessions/events/capture runs. DB unpublished/app127.0.0.1:8000 still running.
No real broker request, source/schema/dependency/UI change or trading/capture action. Head0006.
Mode OBSERVATION; entries/live/signal/execution false, no observation clock/certified days.
Stored history acceptance retained; streaming/option-chain acceptance remains unverified.

Checks:offline locked uv sync PASS; default326passed/22PGskipped, one upstream TestClient
warning; Ruff lint/format PASS83files; strict mypy PASS36backendfiles. Full disposable PG
result added below. Explicit rotation verification against operator runtime is distinct from
disposable regression tests; tests never contact actual broker accounts. No permanent reset
CLI/API added; temporary reviewed maintenance script contains no secrets and was removed.
Files:docs/ADMIN_CREDENTIAL_ROTATION.md, LOCAL_BOOTSTRAP.md, SECURITY.md, VERIFICATION.md,
CONNECTION_READINESS.md, README.md and all eight agent_memory records. Protected operator
.env/password changed locally and remain ignored. Aggregate ignored report:reports/admin_rotation.json.
Remaining:local plaintext password storage/MFA/backups/production hardening; no encrypted
vault claim. Per-file atomic writes are not a transaction across both credential files.
Next:P2-003O bounded real option-chain acceptance:explicit current catalog expiry, one
read-only snapshot, validation/provenance/private DB read; no orders or automated capture.
