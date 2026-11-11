# Test plan

Default pytest suite uses isolated migrated SQLite databases. Tests cover defaults and
unsafe configuration, authentication, hashed session storage, expiry, CSRF, origin checks,
revocation, rate limiting, input secrecy, security headers, host checks, absent live routes,
readiness and schema failure/recovery. Tests never load a real broker credential or live adapter; synthetic credentials remain
local to explicit protocol fixtures. HTTPX real network transports are blocked by an autouse fixture.

Ten opt-in PostgreSQL checks use unique disposable schemas to verify actual migrations,
readiness, UTC expiry/cleanup, CSRF logout/revocation and session persistence across application
recreation. They skip without TEST_POSTGRES_URL. The native verification harness starts a
loopback-only, SCRAM-authenticated temporary cluster and runs the full suite as a non-superuser.
Latest Phase2 result on2026-11-06:152 passed, zero skipped with PostgreSQL. Without PostgreSQL:
142 passed, ten skipped. One upstream TestClient deprecation warning remains.
SQLite tests alone are not PostgreSQL verification.

Run Ruff lint/format and strict mypy. Run pip-audit against installed locked dependencies.
CI additionally starts PostgreSQL 17, runs all tests, scans dependencies and invokes the
isolated Compose build/start/restart/outage smoke command. Compose configuration parsing
has passed locally using the official standalone CLI. Actual image build and container
auth/non-root/app-restart/database-outage/recovery/logout smoke checks also passed on
Docker 29.9.2/Compose 5.6.1. CI itself must execute before its success can be claimed.
Dependency scanning is not a penetration test.

Browser smoke checks executed at true 390/768/1440px viewports: no horizontal overflow,
theme toggle works, unauthenticated account state stays hidden and missing-database readiness
is displayed accurately; no captured JavaScript runtime exceptions. Temporary screenshots
were visually inspected at desktop and mobile sizes.

Keyboard focus/control contrast and320px reflow now verified in an isolated Chrome audit;
see ACCESSIBILITY_AUDIT.md. Pending: CI execution, complete keyboard/screen reader checks,
authenticated dynamic states and broader measured contrast audit,
production hardening and later-phase trading tests. The Phase 1 container runtime gate passed.
See VERIFICATION.md for evidence and exact reproduction commands.
Implemented Phase2 broker mocks cover fixed GET routing, no redirects/retries, expiry,
HTTP401/403/429/timeouts, malformed/oversized bodies, schema/timestamp checks, serialized
throttling, CSRF, private routes, secret masking and protected local credential-file writes.
Headless Chrome verified authenticated broker state, synthetic success, rate limiting, logout
and no horizontal overflow at390/768/1440px with no captured runtime exceptions.

Later: broader broker/data pipeline mocks, strategy/look-ahead tests, fills/idempotency,
reconciliation, circuit breakers, holiday/calendar handling, restart and outage simulations.

Instrument checks cover chunked UTF-8/JSON parsing, corrupt/truncated/concatenated gzip,
expansion/record bounds, publication freshness, invalid contracts, duplicate keys, missing
underlying, immutable deduplication, historical universe selection/removals, offset timestamps,
stale status, import locking/cooldown/CSRF, rollback and missing/old schema. PostgreSQL adds
actual numeric/UTC/archive durability, rollback and session-preserving migration upgrade.
Explicit --check-public-instruments verification imported the real public file to a temporary
PostgreSQL DB (83,940 source/6,504 selected records); it is not a live trading test.
Chrome synthetic catalog import/counts/cooldown/logout passed three viewport sizes. Docker
passed migration/readiness and catalog privacy/CSRF checks. No automatic public fetch in pytest.

History tests: bounded date/interval/path requests, fixed encoded broker GET, duplicate/naive/
partial/out-of-range/unordered bars, exact OHLC/quantity checks, extreme numbers, malformed JSON,
identity mismatch, gaps without interpolation, explicit empty batches, option-vs-index identity,
expired-contract rejection, canonical sanitization, deduplication/rollback, cursor pagination,
CSRF/private routes/cooldown and missing credentials without network. PostgreSQL adds actual
history durability/decimals/UTC/rollback and session+catalog-preserving migration roundtrip.
Chrome uses synthetic bars to check form/import/count/throttle/logout and three widths.
No real authenticated historical broker request or genuine recorded prices claimed.

## P2-003C — option-chain research (2026-11-06)

P2-003C verification:182 full PostgreSQL tests pass, zero skipped; default169 pass/13 PG
skipped. Tests cover fixed GET construction, catalog/expiry/CE-PE identity, exact prices/Greeks,
missing/zero data, malformed payload rejection, receipt versions, rollback, sanitized storage,
private paginated APIs, CSRF/cooldown, native numeric/timestamp durability and migration recovery.
Synthetic browser flow passes at390/768/1440px. Actual broker acceptance remains unverified.

## P2-003D — V3 feed foundation (2026-11-06)

53 new synthetic feed cases; full native PostgreSQL suite235 passed/zero skipped; default
222 passed/13 PG skipped. Tests cover schema hash, independently encoded binary scalar vector,
unsafe grants, redaction/expiry/reuse, missing/expired credentials, safe HTTP failures, catalog
resolution, subscription bytes, malformed/mismatched/mode/numeric/timestamp frames and known
market statuses. Strict mypy23 files and Ruff55 files pass. Lock check and dependency audit pass.
Container smoke also exercises decoding. No frontend changes; no new browser check needed.

## P2-003E — bounded feed lifecycle (2026-11-06)

P2-003E adds25 mocked lifecycle cases. Full disposable PostgreSQL suite260 passed/zero skipped;
default247 passed/13 PG skipped. Ruff60/mypy25/lock and dependency audit pass. Separate real
loopback TLS verifies binary subscribe, schema ordering, server ping/client pong, cleanup and
302 redirect rejection. CI step added but not run remotely. No real broker or browser test.

## P2-003F — durable research observations (2026-11-06)

P2-003F adds16 cases (13 general plus3 native PostgreSQL):full suite276 pass/zero skipped;
default260 pass/16 PG skip. Covers canonical/idempotent receipts, pagination, sampled intervals
and continuity breaks, unsafe/schema mismatch, transaction rollback/byte caps, lease recovery,
private API, runner integration, cancellation/in-flight commit, concurrent row locks, restart
and migration retention. Ruff66/mypy29/lock PASS. Docker migration/private reads/persistence
and real loopback TLS regression PASS. No real broker data or new browser check.

## P2-003G — calendar/coverage baseline (2026-11-06)

P2-003G adds25 cases (23 general/2 PG):full301 pass/zero skip; default283 pass/18 PG skip.
Coverage includes verified hashes/holiday/special priority, reviewed-hour/year unknowns, bounds,
source separation/overlap union/discontinuities, future/closed/empty windows, archive/resource
failures, private read-only endpoints, consistent native PG snapshot and restart. Ruff70/mypy31/
lock PASS. No dependency/frontend change; genuine NSE source artifacts, synthetic market data.

## P2-003H — bounded supervision (2026-11-06)

P2-003H adds18 cases (16 general/2 PG).319 nativePG pass/zero skip; default299 pass/20 PG skip.
Tests cover rollover/grants/distinct IDs/quota statistics, early byte/event rejection, child
access failure/pending retry, cooperative stop/external cancellation/creation race, lease
recovery, hard policy limits, runtime exhaustion, concurrent quota enforcement/rollback and
restart/downgrade child preservation. Ruff77/mypy34/lock PASS. New standalone verify_supervision
checks real local TLS and two durable synthetic sessions; CI step updated, not remotely run.

## P2-003I — safe capture preflight (2026-11-06)

P2-003I adds16 cases (14 general/2 PG):full335 pass/zero skip; default313 pass/22 PG skip.
Credential/schema/catalog/calendar/quota/active-record diagnostics, no mutations/network, API
auth/validation, CLI safe errors/no-start, native local-pass and revoked INSERT detection pass.
Ruff81/mypy36/lock and real localTLS supervision regression PASS. No dependency/frontend change.
Actual workspace diagnostic correctly BLOCKED for missing credential/unavailable DB.

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

## 2026-11-06T17:53:39.936212+00:00 — CI-PG-PERM PostgreSQL permission regression fixed

Permission-denial tests need a disposable PostgreSQL setup login with CREATEROLE (or a
bootstrap superuser),not production. Migrations retain setup ownership. The restricted
execution role is separately created NOLOGIN/NOSUPERUSER/NOCREATEROLE/NOBYPASSRLS/non-owner.
Fixture grants isolated-schema reads/required writes and SET ROLE per connection;teardown
revokes grants and drops role/memberships. No ordinary default test role becomes superuser.
Test positive baseline,then revoke capture_runs INSERT,query effective privileges and prove
actual INSERT fails42501 before asserting preflight's DATABASE_PRIVILEGES_MISSING blocker.
CI17.6superuser setup and native17.11non-superuser setup both pass348tests;target1pass after
reproduced failure. uv Ruff/format/mypy pass. One upstream warning. Fixture cleanup verified
zero roles/schemas remain. See VERIFICATION.md for exact root cause/security boundaries.

## 2026-11-06T18:00:37.861532+00:00 — Running the PostgreSQL tests instead of skipping them

Default pytest without TEST_POSTGRES_URL:326passed/22skipped;the privilege test is not run.
Use the supported disposable harness when native binaries are available:
`uv run python -m scripts.verify_postgres --bin-dir .local/verification/postgres/17/bin`.
Fresh Compose PostgreSQL17.6 verification:fixed target1pass,PGintegration22pass,full348pass,
all0skips;old-code archive reproduces1expected failure. Runtime fix is in e108f1e. Ruff/mypy
pass. Fixture roles/grants/schemas and disposable project cleanup verified. Operator DB must
never be supplied as TEST_POSTGRES_URL. Full evidence:VERIFICATION.md latest entry.

## 2026-11-06T18:44:21.685960+00:00 — P2-003S deterministic synthetic coverage fixtures COMPLETE

Root cause reproduced at fixed2026-11-06T18:29:58Z(23:59:58IST):old helper used wall-clock
recent observations but its synthetic session closed23:59;sampled union became0instead1000ms.
At ISTmidnight,independent date reads could also select a different date than recorded samples.
A temporary test-only clock harness first hit a module-alias mismatch;corrected it and verified
the exact original coverage assertion fails before changes and passes after at the same time.
No runtime guard,window or assertion was relaxed to obtain passing results.

Added opt-in coverage_clock fixture in tests/conftest.py with synthetic fixed instant
2026-11-06T06:30:00Z(noonIST). Only requesting tests' catalog/recording/coverage modules and
synthetic metadata builders receive restored-after-test datetime references. Authentication,
OS/system clock,production configuration and unrelated tests are not frozen. Coverage helpers
use the same explicit instant for calendar/request/base;two PostgreSQL coverage consumers now
request this fixture.4regression cases poison helper wall-clock at23:59:58,23:59:59.999999,
00:00:00IST and a year rollover;coverage/source separation and zero-day assertions preserved.

Verification:original deterministic reproducer now1pass;coverage module27pass;full disposable
PostgreSQL17.11 suite371passed/0failed/0skipped,cluster removed. Default348passed/23PGskipped.
Ruff86files/mypy36backendfiles/locked uv sync PASS;1Starlette TestClient warning remains.
No operator DB,Upstox token,env,calendar manifest,broker call,live flag or runtime implementation
changed by this task. No source-type claims made for genuine data;fixtures remainSYNTHETIC.
PriorQ/R uncommitted changes preserved. Temporary reproducer removed. CI hosted resolution
remains unconfirmed. This task only changes3test files plus relevant docs/handoff records.
No staging/commit/push/history rewrite. OBSERVATION/live disabled retained.
Next:P2-003R-A recheck official catalog freshness then genuine active-broker stop acceptance
only if preflight passes;last operator report blocked CURRENT_CATALOG_REQUIRED. Do not bypass
freshness/closed-market gates or certify a day from snapshots. Longer observation still pending.

## Initial report and Phase2 closure verification

10new report/security tests plus1PostgreSQL test cover source separation, empty seven-date
windows, corruption, Markdown/HTML escaping, input bounds, read-only access and container
forwarding. Latest full disposablePG suite385passed/0skips;default361passed/24PGskips.
Ruff89files,mypy37files,TLS/supervision,pip-audit and isolated Docker smoke pass. One upstream
warning remains. Hosted foundation run42630898094 passes on0f2df43; these new tests are local
until a new approved commit/push. See PHASE2_ACCEPTANCE.md; overall Phase2 remains partial.

## Evidence-only window progress — 11 November 2026

Fourteen new synthetic cases verify exact IST midnight/UTC boundaries, clamped elapsed date
counts, short/future/elapsed filters, open and special/holiday windows, missing and partial
samples, source/calendar separation and state isolation. Even fully elapsed dates with
samples on all baseline sessions do not certify observation or imply a threshold. Existing
read-only SQL, escaping and native PostgreSQL report assertions remain and were strengthened.
Targeted24passed; fresh full disposable PostgreSQL17.11:758passed,0failed,0skipped, one existing
Starlette warning. Ruff123files/format, mypy50files and locked sync passed. Actual deployed
stored-data report remains IN_PROGRESS/NOT_CERTIFIED; archive hashes unchanged. Operational
acceptance was separate from tests and made no real broker/Drive call or new recording.
