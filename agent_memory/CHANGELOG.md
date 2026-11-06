# Changelog

## 0.1.0 — 2026-11-06, Codex / root
Objective: Phase 1 foundation only.
Added repository structure, FastAPI/SQLAlchemy/Alembic foundation, fail-closed configuration,
Argon2 administrator sessions, CSRF/origin checks, safe logging and headers, responsive vanilla
shell, Docker/Compose definitions, tests, locked environment, CI and operational documentation.
Verification: 27 pytest passed, 1 PostgreSQL skipped; Ruff/mypy pass; 63 dependency packages
with zero audit findings; Chrome responsive/theme/private-state smoke passed.
Security: no broker credentials or execution path; no production readiness claimed.
Mode: OBSERVATION; entries false; live execution unavailable.
Remaining: PostgreSQL/Docker runtime verification; next task P1-VERIFY.

## 0.1.0 verification iteration — 2026-11-06T11:09:08Z, Codex / root
Fixed textual LIVE_ENABLED=false startup parsing with environment regression tests. Added
four unique-schema PostgreSQL integration checks, a native disposable PostgreSQL harness,
a generated-credential isolated Compose smoke command and CI wiring. Compose accepts isolated
APP_ENV_FILE/APP_BIND_PORT overrides. Updated verification/security/setup/handoff documentation.
Actual results: PostgreSQL17.11 full suite41 passed; default37 passed/4 skipped; Ruff/mypy pass;
Compose config pass. Docker engine missing: container build/runtime checks not passed.
No dependency changes, system installations, broker credentials or execution added.
Mode OBSERVATION; entries/live disabled. Next: remaining Docker runtime P1-VERIFY gate.

## Phase 1 runtime verification complete — 2026-11-06T11:19:39Z, Codex / root
Confirmed Docker client/server 29.9.2 and Compose 5.6.1 after operator installation. Actual
image build and generated-credential isolated container smoke PASSED: migrations, readiness,
authentication, non-root UID 10001, app restart, database outage/recovery, CSRF/revocation and
absent execution routes. Temporary containers/volume removed; follow-up cleanup confirmed.
Ruff lint/format and mypy rerun successfully. No application/test/dependency changes; prior
41-test PostgreSQL result retained without unnecessary rerun. Updated documentation/memory.
P1-VERIFY closed. OBSERVATION; entries/live off. Next task P2-001 read-only broker docs review.

## Phase2 first read-only slice — 2026-11-06T11:37:45Z, Codex / root
Added official API/credential review, server Analytics credential+expiry validation, fixed-GET
Upstox exchange adapter, admin/CSRF manual probe, bounded error/rate handling, dashboard states,
hidden local secret setup and network-isolated synthetic broker tests. HTTPX became runtime
without a version change. Extended Docker smoke covers the new private/unconfigured routes.
Actual checks: native PostgreSQL72 tests pass; default68 pass/4 skip; Ruff/mypy/lock pass;
Docker extended smoke pass; Chrome synthetic login/probe/throttle/logout/responsive pass.
No real broker request, token, account balance, observation record or live permission created.
Mode OBSERVATION; entries/live off. Phase2 partial. Next:P2-003A instrument-master snapshots.

## Versioned instrument master — 2026-11-06T11:58:08Z, Codex / root
Implemented bounded public NSE gzip/streaming JSON import, strict scoped metadata, immutable
raw/provenance snapshots, bulk atomic/idempotent persistence, as-of universe lookup, private
API/import controls, CLI and dashboard. Added migration0002 and readiness/table checks.
Actual checks:113 PostgreSQL tests; default106 pass/seven skip; Ruff33/mypy12/lock PASS;
real public83,940/6,504 import PASS; Docker and Chrome catalog smoke PASS. No dependency added.
No operator DB/secrets configured. OBSERVATION; entries/live false. Next:P2-003B candles.

## Historical research-minute ingestion — 2026-11-06T12:18:24Z, Codex / root
Added bounded catalog-resolved V3 minute history, exact OHLCV/aware/completed/order/gap checks,
immutable sanitized canonical batches/UTC rows, atomic dedup/rollback, private paginated APIs,
admin/CSRF cooldown import, host CLI and dashboard. Shared broker transport preserves safety.
Migration0003_candles and readiness checks added. Actual152 PostgreSQL tests, default142/ten
skip, Ruff42/mypy16/lock, Docker and Chrome synthetic checks PASS. No dependency changes.
No real historical broker data/credential/fill/return claimed. OBSERVATION; entries/live off.
Next:P2-003C option-chain snapshots/validation. Full Phase2 incomplete.

## Option-chain snapshots — 2026-11-06T12:42:25Z, Codex / root
Implemented P2-003C fixed GET/catalog expiry/CE-PE validation, exact market values and Greek
diagnostics, immutable sanitized receipt versions/legs, admin API/UI/CLI and migration0004.
182 PostgreSQL PASS, default169/13 skip, Ruff51/mypy21/lock PASS, Docker/Chrome PASS.
No dependency/secrets/deployment added. OBSERVATION; entries/live off. Next:P2-003D
WebSocket authorization/decoder foundation. Actual broker acceptance remains unverified.

## P2-003D — 2026-11-06T12:52:13Z, Codex / root
Added internal bounded V3 authorization, validated redacted one-use grants, current catalog
LTPC plans, official pinned/generated Protobuf decoding and offline CLI. Locked protobuf
runtime/types and vendor provenance/license.235 native PG PASS; default222/13skip; Ruff55/
mypy23/lock/audit/Docker PASS. Repaired a previously malformed P3 backlog row. No frontend
or schema change; no socket opened. OBSERVATION/entries-live off. Next:P2-003E lifecycle.

## P2-003E — 2026-11-06T13:05:26Z, Codex / root
Added restricted bounded WSS transport and research lifecycle/health/filtering, explicit host
streaming CLI, mock tests and real loopback TLS verification/CI step. Locked websockets16.1.1.
260 native PG PASS; default247/13skip; Ruff60/mypy25/lock/audit/Docker/TLS PASS. No frontend or
schema changes. OBSERVATION/live off; no durable recorder or actual broker acceptance.
Next:P2-003F durable research sessions/events.

## P2-003F — 2026-11-06T13:21:55Z, Codex / root
Added durable bounded sessions/catalog attempts/events, strict normalized archive/row-lock
transactions, lease recovery, cancellation-safe writer and private reads. CLI now records
before stdout; PLAN/observed UTC/monotonic stamps added. Migration0005/readiness.276 nativePG
PASS; default260/16skip; Ruff66/mypy29/lock/Docker/localTLS PASS. No dependency/frontend change.
OBSERVATION/live off; no real broker capture or certified days. Next:P2-003G calendar/coverage.

## P2-003G — 2026-11-06T13:34:45Z, Codex / root
Added reviewed official NSE FO calendar artifacts/policy/hashes and bounded read-only sampled
coverage reports/CLI/private routes. Explicit historical-hour/year unknowns, holiday amendment
and Sunday special, synthetic separation and overlap union.301 nativePG PASS; default283/
18skip; Ruff70/mypy31/lock/Docker PASS. No dependency/migration/frontend change. OBSERVATION/
live off; no real broker acceptance or certified days. Next:P2-003H capture supervision.

## P2-003H — 2026-11-06T13:56:30Z, Codex / root
Added parent quota/stats ledger, linked sessions/schema0006, bounded supervisor/new CLI,
cooperative stop/cancellation creation handling,30s rollover/pending-retry guard, recovery and
private summaries.319 nativePG PASS; default299/20skip; Ruff77/mypy34/lock/Docker/localTLS PASS.
No dependency/frontend change or real account capture. OBSERVATION/live off; certified days0.
Next:P2-003I safe operator preflight.

## P2-003I — 2026-11-06T14:09:13Z, Codex / root
Added safe preflight service/private GET/standalone CLI, shared readiness/schema and catalog
helpers, quota planning and supervisor blocked/preflight-only gating.335 nativePG PASS; default
313/22skip; Ruff81/mypy36/lock/Docker/localTLS PASS. Actual host BLOCKED missing token/DB.
No schema/dependency/frontend change or broker request. OBSERVATION/live off. Next:P2-003J
secure local runtime bootstrap, preserving secrets/settings.

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

Actual repeat bootstrap: READY_LOCAL, administrator login verified again; .env and private
administrator password bytes unchanged. Both files mode0600; runtime directory0700.
Persistent application/database retained. Secret-pattern source/document/config scan:zero
findings; protected .env/.local excluded. No real broker request or recording started.
Changed files:scripts/bootstrap_local.py, tests/security/test_runtime_bootstrap.py,
docs/LOCAL_BOOTSTRAP.md, README.md, MASTER_PLAN.md, docs/DEPLOYMENT.md and relevant
verification/security/setup/preflight docs; all eight agent_memory handoff files. Operator
.env and .local/runtime generated locally and ignored, never included in source reports.

## 2026-11-06T14:29:38.704079+00:00 — P2-003K persistent metadata onboarding

Completed authorized public-source onboarding through the running app's existing admin API.
Authenticated POST /api/instruments/sync with exact Origin/CSRF imported one immutable snapshot.
Source:https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz
Publication:2026-11-06T00:04:11Z; retrieval:2026-11-06T14:27:55.902533Z; import:2026-11-06T14:27:56.194859Z.
SHA-256:a0f03852e2b918ec41c8c538acee34c6d7a19856c4b2fff88136be0c21d72b56
Snapshot:036304c842b9b5f9014113d19c3be6546220327661bbbb83a6a64ff4ee49de6f.
Processed83,940 source records; stored6,504 selected:139INDEX,3,165CE,3,182PE,18FUT.
CURRENT_METADATA at verification14:27:56UTC; freshness is time-dependent, not permanent.
Read-only DB verification rehashed archived gzip, reparsed it through existing full validator,
matched normalized totals/type counts and confirmed exactly one snapshot. Nifty50/BankNifty
private lookups passed; anonymous access denied before login and after CSRF logout.
Observation sessions/events/capture runs remain0; global observation_started_at null.

Actual private preflight:BLOCKED only CREDENTIAL_MISSING. POSTGRESQL_REACHABLE, schema CURRENT
(head0006_capture_runs), CURRENT_KEYS_RESOLVED, TABLE_GRANTS_PRESENT. No actual Analytics
credential, authenticated broker request, grant/frame acceptance, market capture, quote/fill,
seven-day certification or trading activation. Entries/live/signals/execution remain false.
Tick units BROKER_UNVERIFIED; futures metadata conveys no trading permission. Static calendar
and broker/account access/production hardening limitations remain as previously recorded.
Public metadata download is distinct from authenticated broker-account access.

No runtime source/schema/dependency/UI change; reused existing validated import/diagnostics.
Files:docs/INSTRUMENT_MASTER.md, docs/CONNECTION_READINESS.md, docs/LOCAL_BOOTSTRAP.md,
docs/CAPTURE_PREFLIGHT.md, docs/VERIFICATION.md, README.md, MASTER_PLAN.md and all eight
agent_memory handoff files. Local ignored report:reports/local_metadata_onboarding.json.
Protected .env/admin password unchanged; no secrets printed, collected or written to report.
Persistent project algotrade-ai-local remains running at http://127.0.0.1:8000; DB unpublished.
Checks:offline uv sync --locked PASS; default pytest326passed/22PGskipped, one upstream
TestClient warning; Ruff lint/format PASS83files; strict mypy PASS36backendfiles.
A read-only verification attempt initially used an unsupported Download constructor keyword;
corrected against actual source, rerun passed, no database mutation by either verification.
Next:P2-003L operator-local Analytics setup and explicit read-only connection acceptance.
Operator must enter credential/aware actual expiry through hidden local helper, never chat.
Do not launch capture automatically or claim an unperformed acceptance check.

Final P2-003K verification:full isolated PostgreSQL17.11 suite348passed/zero skips;
cluster stopped/removed; persistent operator DB retained. One upstream TestClient warning.
Source/document/config secret-pattern scan:139files,zero findings; .env/.local excluded.
No dependency/source change requiring additional build; running app remains unchanged.
Current operator blocker is only CREDENTIAL_MISSING; see docs/CONNECTION_READINESS.md.

## 2026-11-06T14:32:03.002697+00:00 — P2-003L prerequisite check; acceptance pending

User requested next task. Inspected actual source, portable Git status and protected local
configuration without printing secret values. Analytics token and declared expiry are both
absent. Live authenticated app preflight at2026-11-06T14:31:48.392989Z:readiness200,
POSTGRESQL_REACHABLE, schema CURRENT0006_capture_runs, CURRENT_KEYS_RESOLVED and
TABLE_GRANTS_PRESENT; BLOCKED only CREDENTIAL_MISSING. Login/private diagnostic/CSRF logout
passed. No broker check requested because there is no credential. No settings/source/schema
change or capture; OBSERVATION, entries/live disabled. No actual broker acceptance claimed.
P2-003L remains pending operator-local input, not completed. Next exact action:operator runs
`uv run python -m scripts.configure_upstox` in the project directory and enters the actual
Analytics token hidden plus actual aware expiry, then runs
`uv run python -m scripts.bootstrap_local`. Never send credentials in chat. After reload,
verify explicit read-only probe and preflight; do not auto-start recording or promote phases.
Files changed:all eight agent_memory handoff records and docs/CONNECTION_READINESS.md.
Verification:this turn's live local diagnostic above; no source change, full regression suite
not rerun. Prior348PGpass evidence remains historical. Persistent deployment/data preserved.

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

Final P2-003M verification:full disposable PostgreSQL17.11 suite348passed/zero skips,
one upstream warning; temporary cluster stopped/removed, operator DB retained.
Secret-pattern scan:139source/document/config files,zero findings; protected operator
files excluded. Native tests and actual HTTP import/integrity evidence distinguish synthetic
regression coverage from real broker acceptance. No runtime source changes. Next:P2-003N.

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

Final P2-003N checks:full disposable PostgreSQL17.11 regression348passed/zero skips;
cluster stopped/removed; actual operator DB preserved. One upstream TestClient warning.
Secret-pattern scan:140files,zero findings; .env/.local excluded. Temporary rotation
script removed; candidate secret removed. No secrets in source/handoff/report. Exact next:P2-003O.

## 2026-11-06T15:05:16.615874+00:00 — P2-003O real option-chain acceptance COMPLETE

Verified one actual read-only Upstox option-chain GET via private authenticated app capture.
Nifty50, expiry2026-11-09 explicitly chosen as nearest unexpired date returned by current
local catalog, not an invented contract/rollover. Retrieved2026-11-06T15:03:40.459116Z.
Snapshot:766329217af5ea5e7c7b67df4a452fbb4349416b43cf56cd8d5a8dfaa93a9659
Catalog:036304c842b9b5f9014113d19c3be6546220327661bbbb83a6a64ff4ee49de6f
Source:https://api.upstox.com/v2/option/chain?instrument_key=NSE_INDEX%7CNifty+50&expiry_date=2026-11-09
Response SHA-256:abb38903778bef8c5b1fb7ac6e5511a3b96e442529c157361eadb5283ca9474c
Canonical SHA-256:55f639b362b144b157e4ecaf679e67ef57e7f5955063ca92fb8ce44dcfb51373
Stored135strikes/270legs(135CE,135PE),72flagged legs:56ZERO_REPORTED_VOLUME,
20WIDE_SPREAD (flags overlap). Freshness UNKNOWN; exchange_timestamp null. This verifies
one broker response/schema/credential acceptance, not current executable quotes, Greek units,
full universe coverage or trading eligibility. No validator loosened to accept real data.

Read-only DB transaction rehashed canonical payload, compared all normalized fields for all
270legs, confirmed catalog identity/strike/type/lot/underlying/expiry and complete CE/PE pairs.
Flag counts match archive metadata. Admin private pagination returned all270unique legs in
2pages, retaining freshness UNKNOWN and execution false. Anonymous status401, admin login,
capture200, private reads200 and CSRF logout204 passed. No further broker calls during
verification. Actual broker request ran outside pytest; test transports remain synthetic.

Persistent DB:1instrument snapshot/6504instruments,1history batch/75candles retained,
1chain snapshot/270legs;0observation sessions/events/capture runs. OBSERVATION; entries/live/
signals/execution false. No streaming launched, no observation clock/day certification.
Credential/password/DB configuration unchanged; rotated administrator password remains only
in protected local storage. No secret/authorization URL/raw broker body printed or archived
in reports. Safe ignored aggregate report:reports/local_option_chain_acceptance.json.
No runtime source/schema/dependency/UI changes; head0006 unchanged. Observed existing staged
repository changes; agent did not stage/commit/reset them. App/private DB remain running.

Checks:offline locked uv sync PASS; default326passed/22PGskipped; Ruff lint/format PASS83files;
strict mypy PASS36backendfiles; one upstream TestClient warning. Full disposable PG outcome
added below. Official primary option-chain API contract reviewed; explicit dates retained.
Files:README.md, MASTER_PLAN.md, docs/OPTION_CHAIN.md, CONNECTION_READINESS.md,
VERIFICATION.md, BROKER_COMPLIANCE.md and all eight agent_memory records.
Next:P2-003P bounded real streaming authorization/decoder acceptance:explicit short-lived
index-only subscription, finite runtime and safe diagnostics; no orders, automatic restart,
full-day claim or strategy phase promotion. Broker closed-market outcomes must remain honest.

Final P2-003O checks:full disposable PostgreSQL17.11 suite348passed/zero skips;
cluster stopped/removed, persistent operator DB preserved. One upstream TestClient warning.
Secret-pattern scan:140source/document/config files,zero findings; .env/.local excluded.
No runtime code changes or dependency update. Exact next:P2-003P bounded real feed acceptance.
