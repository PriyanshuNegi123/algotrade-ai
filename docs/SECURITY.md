# Initial security architecture

## Trust boundaries
Browser → same-origin API → PostgreSQL. A restricted outbound Upstox boundary now supports
read-only exchange checks and bounded historical GET imports. A separate fixed public asset
source supplies instrument metadata. No LLM or order-execution boundary exists yet.
Future internet/LLM content is untrusted research data and cannot change risk limits,
credentials, execution permissions or live order parameters.

## Implemented
- Argon2id password verification; administrator provisioned only by local environment hash.
- Random 256-bit opaque sessions, stored as digests, fixed short expiry and durable revocation.
- HttpOnly/SameSite=Strict cookies; Secure mandatory in production configuration.
- Exact Origin and CSRF header checks for cookie-authenticated mutations.
- Strict input models, secret-safe validation errors, parameterized ORM operations.
- Explicit trusted hosts; CSP without inline scripts, anti-framing, no-store and nosniff.
- Production requires HTTPS origins, secure cookies and configured hash.
- Allowlisted structured request logging excludes paths, queries, bodies, headers and exception text.
- Single-worker login throttling. Default app log access disabled in deployment commands.
- Optional broker Analytics credential stays in server secret configuration, never frontend or DB.
- Fixed-host/path GET client; TLS verification, no redirects/proxy discovery/retries, bounded
  duration/body size, allowlisted response schema and secret-free upstream error codes.
- Admin/Origin/CSRF-protected manual broker probe, serialized single-worker cooldown.
- Live/order execution remains structurally absent; configured token kind is operator-declared.
- Local credential setup uses hidden prompt, atomic mode0600 write and symlink rejection;
  temporary secret files are excluded from Git and Docker context.
- Loopback app port; private PostgreSQL; non-root app/migration containers; dropped capabilities.

## Deployment requirements / unfinished controls
TLS termination, firewall/VPN access, perimeter rate limits and TLS certificate operations are
operator requirements. Do not expose the development HTTP server publicly. Configure reverse
proxy body limits (e.g. 16 KiB), login rate limits and header timeouts. Production env validation
cannot prove the network actually uses HTTPS. Restrict access before deployment.
MFA, tamper-evident audit events, credential encryption for future broker tokens, dependency
update automation, network egress restrictions, tested encrypted backup/restore, session
concurrency limits and security incident workflows are later hardening work.

Login throttling is process-local and resets on restart. Do not run multiple workers.
An attacker can temporarily deny admin logins; use a VPN and perimeter rate limiting.
Session/CSRF tokens must never enter URLs or logs. After reload the user reauthenticates to
recover CSRF capability; prior sessions expire naturally. Password hash rotation does not
revoke existing sessions automatically: delete session rows during a credential incident.
Logs are intentionally operational, not a tamper-evident audit log.

All pytest HTTPX network transports are disabled; only explicitly injected synthetic broker
transports work. Production API acceptance, real token entitlements and token renewal have
not been verified. OAuth/token-vault persistence and tamper-evident broker audit are pending.
Environment-file storage is a development mechanism; production must use protected secret
injection. Readiness does not require an optional broker credential and cannot enable trades.

Instrument import adds a fixed public HTTPS asset boundary with no broker credential. Source
bytes are untrusted data, never instructions or code. Explicit compressed/decompressed/record
budgets, gzip/JSON validation, strict selected metadata and parameterized transactional writes
precede publication. Admin/Origin/CSRF controls protect manual synchronization; normal pytest
network isolation remains enabled. Only an explicit optional verification command fetches the
real public source outside pytest. Source archives are never included in API responses.

Historical import uses a typed bounded date/interval/key contract, catalog lookup before
network, encoded key on a fixed official GET URL, admin/Origin/CSRF gates and30second cooldown.
Credentials remain server-side. Shared bounded HTTP error handling is retained; unknown raw
response fields are dropped before canonical archive storage, preventing credential echoes
from being persisted. Pagination is bounded, decimals exact and queries parameterized.
All imported history remains non-signal/non-execution-eligible; no live order path introduced.

## P2-003C — option-chain research (2026-11-06)

Option-chain capture reuses the restricted fixed-host GET transport and server-only bearer
credential. Admin/Origin/CSRF checks, bounded payloads/counts, catalog identity, exact numeric
validation, serialized cooldown, parameterized storage and sanitized errors apply. Unknown raw
fields are excluded from archives/APIs. Normal tests block real HTTP transports. No order method
or permission is added; quote freshness and Greek units cannot be inferred from receipt time.

## P2-003D — V3 feed foundation (2026-11-06)

The internal feed-authorization GET shares existing credential-expiry/time/size/error controls.
Destination/path/query checks and a redacted one-use SecretStr grant limit URL exposure; no
public route/CLI returns grants. The decoder limits binary bytes/keys/segments and allowlists
normalized output. No socket is opened, no raw unknown fields serialized and no trading flag
changes. A future connector must separately suppress URL/header logging and disable redirects.
See WEBSOCKET_FEED.md for source provenance, local URL/TTL assumptions and remaining controls.

## P2-003E — bounded feed lifecycle (2026-11-06)

Production WSS uses validated one-use grants, normal TLS verification, no bearer forwarding,
no redirects/proxies/compression, bounded queues/frames/timeouts and a disabled private logger.
Upstream URI/header/close/error text is never emitted. Safe errors drive bounded retries; auth,
TLS and protocol failures stop. Credential state is checked before/after receives; idle expiry
detection is bounded by polling/pong. Normal pytest blocks real WebSocket handshakes too.
No socket control API, persistence or order permission added. See FEED_LIFECYCLE.md.

## P2-003F — durable research observations (2026-11-06)

Observation writes are server/host-only; new admin routes are GET-only. Strict event allowlist,
bounded sizes/rows, catalog/key checks, safe reason whitelist, parameterized transactions and
row locks prevent unsafe archive mutation. Tokens/socket URLs/raw upstream fields never enter
storage/API. Hashes establish content identity, not tamper-proof signatures. Async cancellation
waits for durable operations; failed finalization leaves a recoverable lease. No live permission.

## P2-003G — calendar/coverage baseline (2026-11-06)

Calendar/coverage are admin-only GETs; strict keys/dates/source enums and bounded DB reads.
No caller source URL/file/SQL/certification flag. Calendar bytes are hashed, never executed.
Archive digest/schema checked on report reads; corrupt evidence fails closed without partial
coverage. Raw broker/credential data never enters reports. Source labels are not cryptographic
attestation; all live/signal/execution flags remain false.

## P2-003H — bounded supervision (2026-11-06)

Supervisor quotas are server/host-only validated policy; no token/URL/method/mode args or HTTP
mutation. Parent and child locked in consistent order; event/byte/counter/stat updates atomic.
Cancellation drains writes before finalization; unknown crashes retain lease-based recovery.
Last health is explicitly historical, never trading authority. Failure/backoff cannot be reset
by immediate rollover. Existing restricted transport/credential redaction unchanged.

## P2-003I — safe capture preflight (2026-11-06)

Preflight is a secret-free local diagnostic, not a permission token. Read-only transaction,
fixed schema identifiers and individually bound privilege probes; no write-and-rollback, grants,
lease recovery or broker requests. Safe fixed errors/actions only, never Settings/DSN/token/hash
or raw error serialization. CLI gates before capture; false broker/write verification flags
make local grants/scope/time/race limitations explicit. No secret input accepted through API.

## 2026-11-06T14:26:00Z — P2-003J secure local runtime bootstrap

Implemented `scripts.bootstrap_local`: protected missing DB/admin credentials, Argon2 hash,
atomic mode0600 files, mode0700 runtime directory, local advisory lock, preservation of
existing secrets and settings, fail-closed conflict/link/existing-volume checks, Unix-socket
Docker restriction, private Compose startup and secret-free HTTP post-setup checks.
No new API, schema, dependency or frontend change. Head remains0006_capture_runs.

Actual persistent project `algotrade-ai-local` is running at http://127.0.0.1:8000.
Readiness200, anonymous overview401, administrator login/private overview/preflight and CSRF
logout passed. `.env` and `.local/runtime/admin-password.txt` hold local protected settings;
never print or paste their contents. DB is private, application loopback-only. Actual app
preflight BLOCKED:CREDENTIAL_MISSING,CURRENT_CATALOG_REQUIRED; database/schema/admin setup
now works. The earlier14:05 host report describes the pre-bootstrap state only. Generated
DATABASE_URL uses internal `db`; host CLI cannot directly reach this unpublished database.
No broker call, public metadata import, recording, strategy, order or phase promotion occurred.

Verification:348 passed against disposable PostgreSQL17.11/SCRAM/non-superuser; temporary
cluster stopped/removed. Default326 passed/22 PostgreSQL skipped. One upstream TestClient
warning.13 new bootstrap security cases. Ruff lint/format PASS83files, strict mypy PASS36
backendfiles, offline locked uv sync PASS. Persistent local deployment is distinct from the
disposable test DB. Previous same-day dependency audit retained; no dependency change.

Security:credentials never returned in safe CLI report or passed in argv; local plaintext
password file is not an encrypted vault. Existing hashes/DB passwords never reset. Existing
volume without credentials refuses generation. Private Compose initialization user has broad
DB privileges; production role separation/TLS/backup/retention/hardening remain pending.
Mode OBSERVATION; entries/live false, recording_startedfalse; genuine certified days0,
observation_started_at null. Real broker acceptance and calendar amendment proof unverified.
Next:P2-003K persistent public instrument metadata onboarding and connection-readiness guidance;
actual Analytics credential must be entered by the operator through local hidden helper only.

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
