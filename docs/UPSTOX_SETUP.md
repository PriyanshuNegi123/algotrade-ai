# Local read-only Upstox setup

The credentialed integration currently provides a manual NSE exchange-status probe.
Public instrument metadata import is also implemented and needs no token; see
INSTRUMENT_MASTER.md. Historical-minute ingestion is implemented separately and needs a configured credential;
its actual broker acceptance has not been tested. Balances, live quotes and option chains are
not fetched, and observations are not recorded. See HISTORICAL_CANDLES.md.
No credential is needed to run automated tests. All broker responses in tests are synthetic.

## Optional operator configuration

1. Use [Upstox Developer Apps](https://account.upstox.com/developer/apps) and its Analytics tab
   to generate the Analytics Token described in the [official instructions](https://upstox.com/developer/api-documentation/analytics-token/).
2. Never paste the token into chat, screenshots, a browser dashboard field, shell arguments,
   Git or logs. From the repository root run:

   ```sh
   uv run python -m scripts.configure_upstox
   ```

   The hidden prompt accepts the token; a separate prompt accepts its actual broker-console
   expiry in ISO8601 with a timezone (for example a date/time ending in+05:30 orZ). Do not
   infer expiry from when you copied it or reuse the commented example as the actual value.
3. The helper atomically writes the pair into local .env with mode0600, preserves other
   configuration and rejects symlinked destination files. Temporary secret files are ignored
   by Git and Docker. It creates .env from the template only if none exists.
4. Configure PostgreSQL and an administrator password hash as described in README. The
   token helper does not provision database/admin credentials or validate those fields.
5. Restart the application/container after secret changes; authenticate to the dashboard and
   use **Check read-only connection**. A configured credential is initially UNVERIFIED.

Alternatively provision these two server-side environment values through your secret manager:
UPSTOX_ANALYTICS_TOKEN and UPSTOX_ANALYTICS_EXPIRES_AT. They must be set together; expiry
must carry a timezone. In non-development hosting, prefer a managed secret mechanism.
The credential is never persisted in PostgreSQL or returned through the API.

## Status interpretation

- NOT_CONFIGURED: no credential; no network call.
- EXPIRED: local expiry reached; no network call; replace it locally.
- UNVERIFIED: no recent successful check; click the manual control after signing in.
- CHECKED: a validated read-only exchange response was received within60seconds. This is
  connectivity evidence only, not quote freshness, account reconciliation or a recording feed.
- AUTH_REQUIRED/ACCESS_DENIED: broker authentication/permissions rejection; no automatic renewal.
- RATE_LIMITED: wait for Retry-After/cooldown. No automatic retries are performed.
- UNAVAILABLE/INVALID_RESPONSE: failed connection or response validation; no market state assumed.

GET /api/broker/status reads only local state. POST /api/broker/check requires administrator
session, exact allowed Origin and CSRF header. Only the server contacts the fixed official
GET endpoint. The adapter accepts no user-selected URL or HTTP method. Historical paths are constructed
from bounded requests and catalog-resolved encoded instrument keys. Redirects and proxy
environment discovery are disabled. Compressed responses are rejected before decoding; requests have bounded duration and size;
responses are parsed into an allowlisted schema and errors never forward broker bodies.
Token kind is operator-declared, not locally cryptographically certified. Even if the wrong
credential is configured, this adapter contains no order method. No credential grants a
trading permission inside the application.

## Unfinished secure integration

OAuth redirects/state/replay handling and encrypted broker-token storage are separate future
work. Account/funds access needs additional broker/IP setup. No LLM, browser or research
component may replace credentials or select live parameters. The complete remaining Phase2
backlog covers broader/current-session candle support, WebSocket capture and observation reports. Instrument
metadata is implemented separately; its raw tick units remain unverified.
No authenticated production Upstox request has been run in this iteration.

Option-chain research capture is implemented through the same protected server credential.
Import current metadata, load an explicit expiry in the dashboard and capture manually.
See OPTION_CHAIN.md; no authenticated chain acceptance has been verified in development.

## P2-003D — V3 feed foundation (2026-11-06)

The V3 authorization/Protobuf decoder foundation is implemented server-side. No operator
setup auto-starts a WebSocket; the bounded host CLI is an explicit operator action. Never paste or log an authorized redirect URI:its query contains
a one-use connection credential. Actual Analytics acceptance and feed entitlements remain
unverified. See WEBSOCKET_FEED.md; the offline decoder needs no broker credential.

## P2-003E — bounded feed lifecycle (2026-11-06)

V3 bounded connector is now available through explicit host scripts.stream_feed. Import current
metadata and configure protected Analytics credentials locally before an operator-run session.
Nothing auto-starts on application boot. Actual broker acceptance remains unverified. Never
log/paste an authorized URL; CLI output contains normalized research events only. No durable
recording or observation-day certification is implemented. See FEED_LIFECYCLE.md.

## P2-003F — durable research observations (2026-11-06)

The explicit bounded streaming CLI now persists research sessions/events before stdout.
Upgrade0005_observations first. Local credential requirements unchanged; no token/authorized
URL accepted through HTTP or args. Actual broker acceptance unverified. Admin read-only archive
routes do not start recording. Zero certified observation days until calendar/coverage gates.
See OBSERVATION_STORAGE.md for crash recovery and host/private-Docker DB constraints.

## P2-003H — bounded supervision (2026-11-06)

supervise_capture offers an explicit bounded multi-session host command with fresh catalog/
authorization, total quotas and cooperative stop. Apply0006_capture_runs; no automatic feed
starts when credentials are configured. No real broker acceptance was exercised. Use protected
local setup only; no token or grant URI in args/chat/browser. See CAPTURE_SUPERVISION.md.

## P2-003I — safe capture preflight (2026-11-06)

Run scripts.capture_preflight for safe local readiness diagnostics; no broker request or
secret output. CREDENTIAL_MISSING/EXPIRED/short lifetime have fixed guidance to the local
hidden configure_upstox helper. Never paste a credential into chat/HTTP/argv. Local pass is
not broker scope/acceptance verification. The supervisor CLI now checks before starting.
Actual workspace still lacks an operator credential and reachable configured DB.

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

## 2026-11-06T14:49:54.812528+00:00 — P2-003M actual historical-candle acceptance

Operator configured Analytics token locally and reported exchange-status check passed.
Agent independently verified authenticated historical GET acceptance through the existing
private app import endpoint at2026-11-06T14:48:33.888270+00:00. One explicit broker request, not a pytest
fixture or order: Nifty50 (NSE_INDEX|Nifty 50),5minutes,2026-11-05 only.75 validated candles
stored, source DESCENDING normalized ascending, gap_count0, NOT_SESSION_VERIFIED.
First open03:45UTC(09:15IST), last open09:55UTC(15:25IST), last close10:00UTC(15:30IST).
Batch:cdaca7b0383b2cb2f61fc7623842271b623b26aca69bc3d526995c4b359212aa
Catalog snapshot:036304c842b9b5f9014113d19c3be6546220327661bbbb83a6a64ff4ee49de6f
Response SHA-256:4529cb0398c56fa670ba07d69d469e6dcc1bb4db13ed0491f76f759ac0500676
Canonical SHA-256:4d58c9cdbd614fec87b97e2a72e655afe54ff6c2ae133f0e26df806cd55dd3e6
Source:https://api.upstox.com/v3/historical-candle/NSE_INDEX%7CNifty%2050/minutes/5/2026-11-05/2026-11-05

Read-only private DB transaction rehashed canonical archive, matched every normalized bar,
verified OHLC bounds,5minute stride/duration and requested IST date. Anonymous status401,
admin login/import/stored batch read200 and CSRF logout204 passed. Local preflight passed
with zero blockers at import time. Operator expiry is a deliberately conservative local
cutoff2027-11-05T00:00:00+05:30 based on console date2027-11-06, not verified exact broker
expiry; previous missing-credential reports are historical. Never print token or expiry claims
as broker cryptographic validation. No token in report/argv/log output. Credentials unchanged.

No source/dependency/schema/UI change. Actual history saved in persistent local private DB;
ignored aggregate report:reports/local_history_acceptance.json. No repeat broker request.
Observation sessions/events/capture runs remain0. OBSERVATION; entries/live/signal/execution
false, observation_started_at null, qualifying days0. Historical import does not certify a
session, options-price dataset or completed day. Request-path identity only, historical
metadata unverifiable; calendar regular hours before review boundary unknown. No fabrication.
Real option-chain acceptance and streaming grant/frame acceptance remain unverified. Exchange
status success is operator-reported; agent's independent broker evidence is the history call.
An administrator password was exposed in chat earlier; do not reproduce it in records.
Rotation and old-session revocation remain a concrete security follow-up, not completed.

Checks this iteration:offline locked uv sync PASS; default pytest326passed/22PGskipped;
Ruff lint/format PASS83files; strict mypy PASS36backendfiles. One upstream TestClient warning.
Full disposable PG verification result recorded below after completion. Tests use synthetic
broker transports and disposable DB only; explicit real-data acceptance ran outside pytest.
Files:README.md, MASTER_PLAN.md, docs/HISTORICAL_CANDLES.md, CONNECTION_READINESS.md,
UPSTOX_SETUP.md, VERIFICATION.md and all eight agent_memory records. Head0006 unchanged.
Next:P2-003N rotate exposed local administrator credential, revoke prior sessions, preserve
broker credential/catalog/history and verify old-password rejection/new-login success.
