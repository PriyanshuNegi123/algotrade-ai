# Architecture decisions

## D001 — Single application and worker (2026-11-06)
Context: foundation and constrained resources. Alternatives: distributed services/shared cache.
Selected: modular monolith, one FastAPI worker, PostgreSQL durable sessions.
Reason: low operational overhead and clear module boundaries. Trade-off: process-local throttle;
no multi-worker deployment until a shared limiter exists. Execution single-writer is future work.

## D002 — Execution structurally absent
Context: Phase 1 is non-trading. Alternatives: stub broker calls behind an environment switch.
Selected: no broker adapter or activation/order routes; LIVE rejected in configuration.
Reason: a normal command/test cannot submit an order. Trade-off: no claimed simulator or risk engine.

## D003 — Opaque server-validated sessions
Context: a single environment-provisioned administrator. Alternatives: JWT or external IdP.
Selected: Argon2id verification, random tokens stored only as digests, fixed expiry, origin/CSRF
checks and durable logout. Trade-offs: DB required for every private request; CSRF stays in
page memory so reauthentication is needed after reload for state-changing actions.

## D004 — Explicit database migrations
Context: PostgreSQL is required; host has no server. Alternatives: production SQLite or
silent schema creation on startup. Selected: PostgreSQL runtime, test-only SQLite for isolated
checks, opt-in real PostgreSQL test and CI service. Trade-off: local test pass cannot certify
PostgreSQL compatibility; Phase 1 verification remains open until actual service checks run.

## D005 — Honest frontend shell
Context: no authorized market or account source. Alternatives: fabricated demonstration values.
Selected: null balances/P&L, no chart series, explicit unavailable data and planned modules.
Reason: prevents simulated values appearing as trading evidence. Trade-off: live chart/module
views will be built only when their backend contracts are implemented.

## D006 — Portable tooling for constrained host
System Python/Git require absent developer tools. A workspace-local uv Python and temporary
Dulwich initialized the repository without installing system tooling or adding runtime dependencies.
Trade-off: default shell git remains unavailable; use documented portable status or install Git.

## D007 — Disposable native/database and container verification (2026-11-06)
Context: no installed PostgreSQL or Docker engine. Alternatives: assume SQLite parity, install
system apps, or defer all checks. Selected: checksum-verified official workspace-local native
binaries, SCRAM loopback cluster and non-superuser application role; schema-per-test isolation.
Compose CLI validates configuration without an engine; a separate unique-project smoke command
covers actual container behavior when an engine exists. Reason: real PostgreSQL evidence without
altering operator credentials, existing databases or system applications. Trade-off: native
results cannot certify Docker/VPS operation; the remaining runtime gate stays open.

## D008 — Normalize false without permitting live activation (2026-11-06)
Context: Literal[False] rejected environment string "false", breaking shipped setup.
Selected: a before-validator recognizes only normalized textual false; literal-false validation
still rejects true/unknown values. Alternatives: unrestricted bool or removing the flag.
Reason: retain the absolute execution boundary while supporting actual environment configuration.
Trade-off: alternate textual false forms like "off" remain unsupported and fail closed.

## D009 — Use Desktop's current context and isolate runtime verification (2026-11-06)
Context: operator installed Docker Desktop, whose engine uses the per-user socket; the
existing agent shell had a stale PATH. Selected: process-local PATH prefix and existing Docker
context; no global shell edits, root socket symlink or daemon reconfiguration needed.
The isolated smoke command passed actual image/auth/non-root/restart/outage/recovery checks
and deleted only its own containers/volume. Reason: verify the declared foundation without
provisioning operator credentials or leaving a development deployment running. Trade-off:
operator setup remains a separate documented action; no production deployment implied.

## D010 — Read-only data credential before OAuth (2026-11-06)
Context: official review supports a separate data credential path. Alternatives: immediately
implement a general order-capable OAuth token path or block all data work on account access.
Selected: explicit server Analytics credential, one fixed GET method and no user-controlled URL.
Reason: start data integration without adding execution capabilities or an OAuth/token-vault
migration. Trade-off: manual local credential/expiry provisioning and actual acceptance test
remain operator steps; OAuth/account access are still unfinished. See BROKER_COMPLIANCE.md.

## D011 — Bounded manual probe, not an observation feed (2026-11-06)
Selected: serialized30second cooldown, no auto retries, fixed host, no redirects/proxy discovery,
10second total deadline,64KiB decoded body limit and strict allowlisted exchange response.
A successful result expires as current connectivity after60seconds; missing/stale/invalid
states never imply market data freshness, usable funds, a started observation period or trading
permission. Trade-off: ephemeral status/limiting and no unattended data capture yet.

## D012 — Development secret helper and network-isolated broker tests (2026-11-06)
Selected: hidden prompt, atomic mode0600 .env update preserving unrelated settings, symlink
rejection and ignored temporary files; no browser credential input or token database columns.
Mock transports provide synthetic protocol fixtures; default HTTPX transports are prohibited
in pytest. Reason: reproducible safety tests without real accounts. Trade-off: managed secret
injection and durable encrypted broker token storage remain production/OAuth requirements.

## D013 — Immutable raw archive with scoped normalized catalog (2026-11-06)
Context: official NSE master contains multiple schemas and tens of thousands of records.
Selected: retain exact compressed source/provenance and normalize only indices/index CE/PE/FUT
for current scope. Stream decoded JSON rather than loading the entire array. Do not fabricate
index lots or tick conversion. Trade-off: raw archive storage grows; stock/other-exchange
normalization and unit verification remain explicit future work.

## D014 — Conservative freshness and first-observed lookup (2026-11-06)
Selected: require a verified publication header within36hours, store publication/retrieval/import
UTC instants independently, mark current only for same-IST-date publication/recent retrieval.
Lookup chooses a universe known by import cutoff before checking a key, preventing removed
contracts from reappearing via fallback and source publication from backdating app knowledge.
Trade-off: holidays/weekends conservatively stale; no historical universe before capture.

## D015 — Atomic snapshot import and idempotence (2026-11-06)
Selected: deterministic URL/publication/content identity, raw archive+bulk rows in one DB
transaction, unique snapshot/key constraints and indexed queries. Repeated content preserves
first timestamps; integrity races resolve only if an identical snapshot committed. API uses
one-worker nonblocking lock/five-minute cooldown and admin/Origin/CSRF. No edit/delete routes.
Trade-off: application-level limiter resets on restart; CLI is an explicit operator action.

## D016 — Conservative prior-day minute history scope (2026-11-06)
Context: V3 supports more units/windows, but session/calendar validation is unfinished.
Selected:1/5/15minute intervals, at most28calendar days, January2022 floor and end before
today's IST session; explicit completed-bar checks remain. Reject expired regular contracts.
Trade-off: current/broader/expired history separate future increments; no calendar completeness
or signal permission implied. Catalog snapshot/type resolution precedes network requests.

## D017 — Canonical immutable candle batches with explicit limits (2026-11-06)
Selected: versioned catalog-bound imports, exact decimals/UTC, source/canonical hashes and only
validated canonical fields. Unknown raw broker fields/credential echoes not persisted.
Ascending/descending accepted; mixed/duplicate bars rejected; intraday gaps reported without
filling. Atomic batches and bounded cursor reads. Trade-off: duplicate requests retain first
provenance only; repeated/overlapping revisions store separate versions. No full-session or
point-in-time historical instrument truth is asserted; all eligibility flags remain false.

## D018 — Reuse restricted bounded broker transport (2026-11-06)
Selected: shared private GET downloader for status/history public methods, preserving expiry,
fixed constructed host/path, identity encoding/body/time budgets, safe failures and no retries.
History API has admin/Origin/CSRF and serialized30second cooldown; DB/validation work is offloaded
from the async event loop. Trade-off: credential type/expiry remain operator-declared; actual
broker acceptance unverified until local secure setup and manual read. No order method exists.

## D019 — Catalog-bound chain receipts and unknown freshness (2026-11-06)
Selected:explicit catalog expiry and paired CE/PE identity before GET; immutable canonical
receipts including receipt time in identity. Same receipt idempotent; later identical prices
retain separate provenance. Missing optional data remains null/zero with diagnostics; invalid
identity/numerics/positive crossed quotes reject whole snapshot. No full-chain completeness.
Trade-off:current metadata can conservatively reject weekend/holiday sources; units stay raw.
No documented exchange quote timestamp means UNKNOWN freshness, regardless of receipt time.
The20% spread/ask diagnostic is not a trading threshold. No eligibility granted.

## D020 — V3 foundation before transport/recording (2026-11-06)
Selected:published schema and generated classes with pinned hash/SDK attribution; protobuf
runtime locked. First supported mode LTPC, max100 catalog-bound index/CE/PE keys. Restricted
authorization GET and server-only locally expiring single-use grant; no browser/CLI grant
endpoint. Conservative single-label Upstox host/path/query policy fails unexpected formats.
Trade-off:actual URL/entitlement/frame acceptance unverified; local60second TTL not broker expiry.

## D021 — Explicit Protobuf precision/presence/time limits (2026-11-06)
Selected:wire-double values converted by shortest decimal representation with explicit flags;
proto3 scalar defaults never certified as present. CurrentTs, receipt and last-trade time remain
separate;5second future tolerance, old frames retained as research. Freshness NOT_EVALUATED
and false eligibility. Only known LTPC/status output; unknown/CAS/preopen detail excluded.
Trade-off:stateless foundation cannot guarantee ordering/duplicates/gaps/session/freshness.
Transport/lifecycle and durable observation must establish those before later research gates.

## D022 — Explicit bounded connector before durable observation (2026-11-06)
Selected:websockets16.1.1 with standard TLS, no redirects/proxies/compression/bearer forwarding,
private disabled logger and safe error codes. Max300s/3attempts/10000frames; each retry resolves
current catalog and obtains fresh one-use grant,30/60s spacing+jitter/Retry-After. Host CLI only,
no app job/control route/migration. Trade-off:no cross-process/account scheduling; actual broker
acceptance remains unverified. Local TLS test uses isolated ephemeral trust only.

## D023 — Aged research health and accepted-only events (2026-11-06)
Selected:status before data, per-connection watermarks, duplicate last-value suppression and
trade-time regression rejection. Filtered frame ticks match accepted observations. Per-key
health ages on data/idle; missing keys and times explicit; pongs cannot refresh prices.
Trade-off:no sequence-loss proof, durable archive or calendar completeness. RECENT_TRADE is
a local diagnostic, all eligibility false; consumers invalidate on disconnect. Missing trade
time never resets prior high watermark. Reconnect starts new provenance/state.

## D024 — Canonical bounded observation archive (2026-11-06)
Selected:separate sessions/catalog attempts/sequential events, strict allowlisted normalized
JSON and hashes; no raw frames or secret socket URI. Per-event row-lock transaction includes
counters/accounting; same receipt idempotent. Async writer waits on in-flight DB work before
propagating cancellation/finalization. Trade-off:DB I/O can extend nominal sink deadline;
no forced thread kill. Read-only admin routes; CLI records before stdout. No mutation API.

## D025 — Conservative intervals and honest crash recovery (2026-11-06)
Selected:sampled interval metric from adjacent accepted same-attempt samples, <=10s receipt/
monotonic deltas, broken by non-data/idle/disconnect. Run duration separate; no calendar day
certification. Lease duration+60s; recover expired sessions as INTERRUPTED with recovery time,
unknown crash end/duration left null. New runs use new IDs; no auto-resume. Trade-off:bounded
recovery pass is not a daemon; metrics do not imply complete coverage. Synthetic provenance
explicit and qualifying days always0 pending calendar/reporting gates.

## D026 — Reviewed NSE FO baseline with explicit temporal limits (2026-11-06)
Selected:pin original annual/amendment/special circulars and current timing page with hashes
and manifest. Current FO09:15–15:40 starts local review validity2026-11-06; earlier ordinary
hours unknown because historical effective date not established. Special Sunday overrides
weekend/holiday; unsupported years unknown. Trade-off:review snapshot not proof of all notices
or realtime amendments. No caller policy/URL. Index/cash coverage is a separate future scope.

## D027 — Consistent sampled evidence, no completed-day inference (2026-11-06)
Selected:repeatable-read READ ONLY PG snapshot, bounded candidates/events/canonical bytes,
payload hash/schema validation. Same-source/key/session/attempt adjacent samples with known
window/ages and<=10s receipt/monotonic deltas; break discontinuities and union overlaps.
Trade-off:incremental quiet feeds undercount; no exact sequence/full-session guarantee.
Future duration not missing; unknown hours/calendar null. Synthetic records separate, qualifying
days0/eligibility false regardless of ratios. Existing archive counters are not rewritten.

## D028 — Durable per-run quota ledger with consistent locks (2026-11-06)
Selected:parent capture_runs table, optional session FK, atomic parent-first/session-second
locking for create/append. Quotas and stats charged only with committed events; identical
receipt idempotent. Source/key/policy binding validated; no quota mutation API. Trade-off:only
linked sessions counted, not filesystem/account/global quotas; downgrade loses grouping but
preserves child archives. Last recorded health never represented as current tradable state.

## D029 — Explicit bounded supervision without failure reset (2026-11-06)
Selected:up to1hour/12children/64MiB/100k events, fresh auth+catalog,30s rollover, only healthy
normal child completion with snapshot/no pending retry rolls over. Transport retry flag survives
child duration/backoff to prevent bypass. Cooperative stop drains/finalizes children; DB creation
cancellation waits for identity. Trade-off:cleanup I/O can exceed nominal duration; forced kill
needs lease recovery. No automatic resume/service/phase/day/live promotion.

## D030 — Local preflight without broker or write probes (2026-11-06)
Selected:consistent read-only schema/grant/catalog/active-record snapshot, individual PostgreSQL
privilege inquiries, calendar integrity/scope and declared credential budget+60s expiry. PLAN
reserve and>=3events, bounded inputs, fixed safe report/errors/actions. No Settings/secret/DSN
serialization, broker call, write-and-rollback, grant or migration. Trade-off:local pass not
RLS/constraint/disk/broker acceptance proof or lock; verification flags remain false.

## D031 — Explicit supervisor gating with honest setup blockers (2026-11-06)
Selected:standalone JSON preflight and private GET; normal supervisor CLI checks before record
creation/recovery and exits2 on blockers. --preflight-only returns without launching. Admin
absence warns for host use, SQLite blocks operator capture, FO unknown calendar blocks while
closed hours warn. Trade-off:existing library fixtures/single-session controls independent;
no global authorization token. Actual workspace missing token/DB must be reported as blocked,
not concealed by successful disposable verification. Secure bootstrap is the next task.

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

## 2026-11-06T15:45:59.740534+00:00 — Consolidated status and next steps

User requested Markdown progress/next-action update. Added docs/PROJECT_STATUS.md and
refreshed CURRENT_STATE.md to remove stale one-commit/unavailable-Git statements while
preserving verified data lineage, safety limits and reproduction steps. Current HEAD92a941b,
2reachable commits;tracked exact Gitleaks allowances. Rescanned actual full history this
turn:Gitleaks8.30.1 exit0/zero unallowed findings. Prior2false-positive exceptions retained;
no new ignore scope or detection-rule changes. Runtime verification was not rerun; prior
348PGpass/default326pass22skip results labeled historical. Runtime health/data counts also
not rechecked. No credentials/values copied to documentation.

Functional next:P2-003P finite index-only real streaming grant/subscription/decoder verification;
first recheck current catalog/credential/preflight,then bounded operation/safe cleanup only
when resumed. No fake ticks/day certification or automatic recording. Publishing next:
review and normally commit these documentation changes when authorized,check staged whitespace,
rerun full-history Gitleaks on final refs,then push only on explicit instruction. No history
rewrite/force-push required or authorized. OBSERVATION/live off unchanged; no source/env/
security/broker changes or requests, staging, commit, runtime restart or push this turn.
Files:docs/PROJECT_STATUS.md and all8agent_memory Markdown records. Existing prior review
notes retained in HANDOFF/SESSION_LOG; source requirement phase order retained. Next pending
functional task unchanged; strategy/backtest/paper/execution and production gates remain later.
