# Security review — Phase1 foundation and initial Phase2 read-only slice

Latest bounded local verification: [11 November packet](VERIFICATION_PACKET.md). Both full
PostgreSQL suites passed 784 tests with 0 skips; 73 installed Python packages audited with 0 known
findings / 0 skips; isolated TLS/supervision and Docker auth/OAuth/bootstrap/outage checks passed.
No production approval, container-image CVE scan or new hosted CI success is implied.
The operator runtime/credentials/archives were unchanged; live trading remains disabled.
The dated 6 November source-review notes below remain historical evidence.

Reviewed 2026-11-06 UTC. Scope: foundation source, isolated tests, dependency environment,
unauthenticated browser shell and local Docker smoke checks. **Not a production approval or penetration test.**

## Executed evidence
- Latest pytest with real PostgreSQL17.11:152 passed, zero skipped; one upstream TestClient warning.
  Without PostgreSQL:142 passed, ten skipped. Native cluster used loopback, SCRAM and a
  non-superuser role; it was stopped and removed after the run.
- Ruff lint and format checks: pass. Strict mypy: pass for 16 backend source files.
- pip-audit: 63 installed packages checked; zero known vulnerability findings on this date.
  This does not include operating-system/container images or prove absence of vulnerabilities.
- Security tests: session expiry/revocation, hashed session storage, origin/CSRF rejection,
  brute-force throttle, injection input rejection, validation secrecy, trusted hosts,
  security headers, absent execution routes, database failure and schema recovery.
- Headless Chrome: 390/768/1440px layouts without horizontal overflow; theme toggles,
  unauthenticated account hiding, unavailable-service status; no captured runtime exceptions.
- Source review: restricted fixed-endpoint read-only client added; no execution code.
  Tests block real outbound HTTP and inject synthetic broker data.
- Broker tests verify credential expiry, safe error mapping, body/schema limits, redirect
  rejection, timeout behavior, serialized throttling, CSRF/private routes and secret masking.
- Local token helper tests verify atomic protected writes, preserved unrelated settings,
  rejected invalid input and rejected symlink destinations. No real credential configured.
- Chrome verified sign-in, synthetic broker success, rate-limit feedback and logout at three
  responsive widths without captured JavaScript errors. No production broker result claimed.

- Secret pattern scan: 96 source/documentation/config files checked; zero findings.
  This is a limited pattern scan, not comprehensive secret detection.

## Limitations and release blockers
- Actual PostgreSQL migrations, UTC expiry and application-recreation checks passed.
- Compose config passed with CLI5.7.0; image build and full container smoke passed with
  Docker 29.9.2/Compose 5.6.1. Auth, UID 10001, restart, DB outage/recovery, CSRF/revocation
  and absent execution routes verified; temporary containers/volume removed. CI not run.
- Fixed textual LIVE_ENABLED=false parsing; tests confirm truthy/unknown values still fail closed.
- Temporary verification environments use generated credentials and unique resources; operator
  .env and existing database schemas are not modified. See VERIFICATION.md for provenance.
- No TLS deployment, external penetration test, MFA, audit-chain integrity, backup/restore drill,
  live-execution compliance approval, quote/tick recording or trading-risk engine exists.
- Login throttling is process-local and requires a single worker and restricted admin network.
- Image tags require a future image CVE scan and digest pinning before deployment approval.
- Full keyboard/screen reader and measured WCAG contrast audit remain pending.

The default configuration is OBSERVATION with entries and live execution disabled.

The source review for read-only APIs is complete in BROKER_COMPLIANCE.md. It does not verify
real token type/entitlements or execution regulations. OAuth and durable encrypted broker-token
storage remain pending. Dependency graph versions are unchanged; HTTPX moved from dev-only
to runtime and the image rebuild must pass without relying on development packages.

Instrument iteration review: fixed public asset URL, no credentials/redirects/proxy discovery,
bounded raw gzip download/inflation/JSON records, publication/selected-schema validation,
transactional parameterized writes, deduplication and first-observed lookups. Real public-data
import was explicitly exercised outside pytest in a disposable PostgreSQL cluster. No source
bytes are executable; raw archives are deferred and excluded from APIs. Migration upgrade,
rollback, old-schema readiness, CSRF and concurrency controls tested. No new dependencies.
This review does not resolve tick units, licensing/redistribution or execution approval.

Historical slice: typed/catalog-bound requests, shared fixed-host GET transport, no credential
exposure, canonical allowlisted storage, exact bounded quantities/decimals, aware completed bars,
atomic rollback and bounded queries verified.152 PostgreSQL tests and Docker/browser checks
pass. Test network isolation remains on. No actual credential configured or real historical
broker request performed. Session/calendar completeness and historical contract validity remain
explicitly unverified; imports cannot enable signals/trades. No dependency versions changed.

## Option-chain increment — 2026-11-06T12:42:25Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:182 passed, zero skipped,
one upstream TestClient deprecation warning. Default suite:169 passed,13 PostgreSQL skipped.
Ruff lint/format PASS (51 files); strict mypy PASS (21 backend files); offline lock check PASS.
CLI help PASS. Docker build/migration/non-root/auth/chain-status/CSRF/restart/database outage
and recovery PASS; isolated containers/volume removed. Chrome synthetic expiry selection,
capture/counts/rate limit/logout plus history/catalog regression PASS at390/768/1440px with
no captured JS exceptions or overflow. Temporary browser/server/PostgreSQL stopped.
Secret-pattern scan:88 source/config/documentation files, zero findings; no operator .env.
No dependency versions changed; prior same-day dependency audit remains applicable, not rerun.
Actual authenticated broker option-chain acceptance remains unverified; all chain data synthetic.

Restricted GET transport only; server credential, admin/Origin/CSRF, strict catalog identity,
bounded parsing, safe errors and canonical field allowlist verified. Raw unknown response
fields are excluded from archive/API. No order surface or live authorization was added.
Production hardening, external penetration testing and full accessibility audit remain pending.

## P2-003D — 2026-11-06T12:52:13Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:235 passed, zero skipped.
Default pytest:222 passed,13 PostgreSQL skipped. One upstream TestClient deprecation warning.
53 new synthetic feed cases pass. Ruff lint/format PASS (55 files); strict mypy PASS (23
backend files); offline lock freshness PASS; CLI help PASS. Updated dependency audit:zero
known vulnerabilities. Runtime protobuf6.33.6; development types-protobuf6.32.1.20260221.
Docker build/locked runtime/generated decoder, migrations/non-root/auth/restart/DB outage and
recovery PASS. Added in-container synthetic market-info decoding assertion passed. Isolated
containers/volume removed; temporary PostgreSQL stopped. No frontend changes/browser rerun.
Secret-pattern scan:99 source/config/docs/vendor-schema files, zero findings; no operator .env.
No real authorization, WebSocket or broker account request; no actual feed acceptance claim.

Restricted GET, redacted server-only one-use grant and bounded allowlisted decoder output.
No public grant endpoint/socket/job or migration introduced. Decoder state never enables
trading. Source schema hash and official SDK declaration comparison recorded in vendor README.
Production security/accessibility/backup/live gates remain incomplete.

## P2-003E — 2026-11-06T13:05:26Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:260 passed, zero skipped.
Default pytest:247 passed,13 PostgreSQL skipped;25 new lifecycle cases pass. One upstream
TestClient deprecation warning. Ruff lint/format PASS (60 files); strict mypy PASS (25 backend
files); lock freshness PASS; streaming CLI help PASS. Dependency audit:zero known findings.
Added runtime websockets16.1.1. Real loopback TLS verification PASS:binary subscription,
Protobuf order, server ping/client pong, bounded close and real302 redirect rejection.
Ephemeral certificates/servers removed; no Upstox/account connection. Docker build/runtime
transport-lifecycle imports, existing decoder/migrations/non-root/auth/restart/DB outage/recovery
PASS; isolated containers/volume removed. Native PostgreSQL stopped. No frontend/browser change.
Secret-pattern scan105 files:zero findings; no operator .env. CI step added, not remotely run.

Transport uses normal TLS verification, validated one-use URI, no bearer forwarding or
redirects/proxy/compression, private disabled logger and safe fixed errors. Reconnect counts,
bytes/queues/timeouts/sink delivery/run duration bounded. No durable observations, real broker
acceptance, strategy, order permission or seven-day evidence claimed. No migration added.

## P2-003F — 2026-11-06T13:21:55Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:276 passed, zero skipped.
Default pytest:260 passed,16 PostgreSQL skipped.16 new cases (13 general/3 native PG).
One upstream TestClient deprecation warning. Ruff lint/format PASS (66 files); strict mypy
PASS (29 backend files); offline lock freshness and streaming CLI help PASS. No dependency
versions changed; prior same-day audit zero known findings, not unnecessarily rerun.
Docker build/migration/private observation reads/zero-event SYNTHETIC session restart durability,
existing non-root/auth/decoder/outage/recovery PASS; isolated containers/volume removed.
Real loopback TLS lifecycle regression PASS:binary subscribe, PLAN/status/snapshot order,
server ping/client pong, cleanup and302 redirect rejection. No real broker/account connection.
Native PostgreSQL stopped and ephemeral TLS certificates/servers removed. No frontend/browser
change. Secret-pattern scan112 files:zero findings; no operator .env. CI not remotely executed.

New native tests verify row-lock receipt deduplication, original timestamp/canonical decimal
persistence across restart, rollback and0005 downgrade/upgrade preserving catalog/admin state.
Normalized events only; strict archive schema/reason whitelist, catalog/clock/byte bounds,
parameterized row-lock transactions and read-only admin routes. Cancellation waits for
in-flight commit before finalization; failed DB closure remains lease-recoverable. Source/hash
labels do not constitute signed broker attestation. No completed observation day/live gate.

## P2-003G — 2026-11-06T13:34:45Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:301 passed, zero skipped.
Default pytest:283 passed,18 PostgreSQL skipped.25 new cases (23 general/2 native PG).
One upstream TestClient deprecation warning. Ruff lint/format PASS (70 files); strict mypy
PASS (31 backend files); offline lock freshness and coverage CLI help PASS. No dependency
versions changed; prior same-day audit zero known findings, not unnecessarily rerun.
Docker build/bundled evidence hash loading/private calendar/empty coverage plus existing
migration/auth/non-root/persistence/restart/DB outage/recovery PASS; isolated containers/volume
removed. Native PostgreSQL stopped. No frontend/browser changes or real broker/account request.
Official public NSE documents/HTML actually downloaded and hashed; market observations and
coverage-window fixtures synthetic. Secret-pattern scan120 files:zero findings; no operator
.env. CI not remotely executed. No operator DB/deployment/real credential provisioned.

Tests cover known holiday amendment/special Sunday/UTC boundaries, explicit unknown years and
historical hours, request caps, synthetic separation, interval union/discontinuity/future/closed
handling, corrupt archive/resource rejection, private nonmutating reads and native repeatable
read-only snapshot/restart persistence. Calendar evidence hashes checked before use; no caller
URLs/policy/SQL or certification flags. No migration or activation permission added.

## P2-003H — 2026-11-06T13:56:30Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:319 passed, zero skipped.
Default pytest:299 passed,20 PostgreSQL skipped.18 new cases (16 general/2 native PG).
One upstream TestClient deprecation warning. Ruff lint/format PASS (77 files); strict mypy
PASS (34 backend files); offline lock freshness and supervisor CLI help PASS. No dependency
versions changed; prior same-day audit zero known findings, not unnecessarily rerun.
Real loopback TLS PASS:existing binary/schema/ping-pong/302 checks plus two durable synthetic
supervised sessions, parent event/byte/health totals and closed children. Temporary certificate,
server and SQLite DB removed. Tests alone inject no-wait rollover; production waits30seconds.
Docker build/migration/private parent reads/zero-child SYNTHETIC parent restart durability and
existing auth/non-root/metadata/coverage/recording/outage/recovery PASS; isolated resources removed.
Native PostgreSQL stopped. Secret-pattern scan128 files:zero findings; no operator .env.
CI updated to verify_supervision but not remotely run. No frontend/browser changes, actual broker
credential/account request or permanent operator DB/deployment. All capture verification synthetic.

Native tests verify parent-first row locking under concurrent charging, all-or-none parent/
child/event rollback, durable restart and downgrade grouping removal preserving child events/
admin sessions. Supervision does not reset unresolved child backoff; pre-network PLAN storage
quotas stop safely. External cancellation waits for identities/commits and finalizes children
before parent. No public mutation, raw grant/header/error storage or live permission added.

## P2-003I — 2026-11-06T14:09:13Z

Full disposable PostgreSQL17.11/SCRAM/non-superuser suite:335 passed, zero skipped.
Default pytest:313 passed,22 PostgreSQL skipped.16 new cases (14 general/2 native PG).
One upstream TestClient deprecation warning. Ruff lint/format PASS (81 files); strict mypy
PASS (36 backend files); lock freshness and preflight/supervisor CLI help PASS. No dependency
versions changed; prior same-day audit zero known findings, not unnecessarily rerun.
Native tests verify successful local-only checks without records and actual revoked INSERT
privilege detection/restoration in an isolated schema. Docker private diagnostics/schema/table
privileges/no recording creation plus existing migration/auth/persistence/outage/recovery PASS;
isolated containers/volume removed. Real localTLS supervision regression PASS after shared
catalog resolver refactor; temporary certificate/server/SQLite DB removed. PostgreSQL stopped.
Actual workspace CLI preflight14:05:41UTC returned BLOCKED:CREDENTIAL_MISSING and
DATABASE_UNAVAILABLE; admin dashboard unconfigured warning. No writes/settings changes.
Secret-pattern scan133 files:zero findings; no operator .env. No real broker/account request,
frontend/browser change or permanent application DB/deployment. CI not remotely executed.

Read-only consistent snapshot, fixed schema identifiers, individually bound table-privilege
probes, safe blocker/action codes and explicit no-write/no-broker-verification flags. No secret/
DSN/hash/raw exception output, token/URL args, migrations or capture from diagnostics. Supervisor
CLI blocks before recovery/creation; --preflight-only returns without capture. Grant checks
do not establish row-policy/constraint/disk availability or reserve broker capacity.

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
