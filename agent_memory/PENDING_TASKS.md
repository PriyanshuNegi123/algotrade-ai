# Prioritized backlog

Immediate status:the two Gitleaks false positives are resolved by exact fingerprints;
HEAD92a941b has2reachable commits and the latest full-history scan passed. Public push is
still not authorized. See [project progress and next actions](../docs/PROJECT_STATUS.md).
Functional next remainsP2-003P; publishing checks must be repeated after the final commit.

| ID | Priority | Dependencies | Scope | Acceptance criteria | Complexity | Status |
|---|---|---|---|---|---|---|
| P1-VERIFY | P0 | Docker/PostgreSQL | Verify image build, migrations, auth, non-root UID, app restart and database outage/recovery | Full isolated smoke succeeds and cleanup confirmed | Medium | COMPLETE 2026-11-06: native PostgreSQL 41 tests and actual container smoke passed; CI execution tracked separately |
| P1-UI-AUDIT | P1 | P1-004 | Keyboard, screen reader and measured contrast audit | Accessible focus/order/errors and AA contrast measured; resolve defects | Small | Pending |
| P2-001 | P1 | P1-VERIFY | Official read-only Upstox API review | Sources/date/versions/credential limits and unknowns recorded | Medium | COMPLETE 2026-11-06; see BROKER_COMPLIANCE.md |
| P2-002A | P1 | P2-001 | Server Analytics credential, restricted probe and secure local setup | Expiry/CSRF/errors/throttling/secret tests and container/browser checks pass | Medium | COMPLETE implementation; actual broker acceptance not tested without operator credential |
| P2-002 | P1 | P2-001; appropriate operator app configuration | OAuth and protected persistent broker credentials | Exact registered callback; mandatory one-use session-bound state; no invented scope/refresh endpoint; no token exposure | High | Pending; market-data path currently uses server Analytics credential instead |
| P2-003A | P1 | P2-001 | Bounded official NSE index instrument import/versioned snapshots | Atomic archive, provenance, exact raw units, stale/invalid/duplicate/as-of tests and real public-data verification | Medium | COMPLETE 2026-11-06:113 PostgreSQL tests and real83,940/6,504 import verified |
| P2-003B | P1 | P2-003A; P2-002A | Prior-day1/5/15minute history, immutable batches and private APIs/UI | Bounded/catalog-bound/UTC/OHLCV/order/completion/provenance/rollback tests | High | COMPLETE scoped implementation2026-11-06;152 PostgreSQL tests; actual broker acceptance unverified |
| P2-003C | P1 | P2-003A; P2-002A | Bounded option-chain snapshots and data validation | Explicit expiry/catalog CE-PE identity; price/spread/quantity/OI/Greeks checks; freshness unknown absent source timestamp | High | COMPLETE scoped implementation2026-11-06;182 PostgreSQL tests; actual broker acceptance unverified |
| P2-003D | P1 | P2-003C; P2-002A | V3 WebSocket authorization/Protobuf decoder foundation | Official contract; restricted URL/credential handling; bounded decoded identities/timestamps; synthetic tests; no orders | High | COMPLETE scoped foundation2026-11-06;235 PostgreSQL tests; actual broker acceptance unverified |
| P2-003E | P1 | P2-003D | Bounded server WebSocket lifecycle | Mocked grant consumption/binary subscription/ordering/heartbeat/timeouts/cancellation/reconnect/backoff/duplicates/freshness; no orders or URL logs | High | COMPLETE scoped implementation2026-11-06;260 PostgreSQL tests and loopback TLS PASS; real broker acceptance unverified |
| P2-003F | P1 | P2-003E | Durable bounded research observation sessions/events | Catalog/time lineage, accepted observations/health/discontinuities, atomic rollback/restart, private bounded reads, genuine captured-duration accounting; no invented days | High | COMPLETE scoped implementation2026-11-06;276 PG tests; calendar and genuine completed-day verification pending |
| P2-003G | P1 | P2-003F | NSE session/calendar policy and bounded coverage reporting | Explicit holiday/session source provenance, unknown missing coverage, fixture-labeled tests and no invented completed days; live remains off | High | COMPLETE scoped baseline2026-11-06;301 PG tests; static amendment completeness and actual broker capture remain unverified |
| P2-003H | P1 | P2-003G | Bounded multi-session capture supervision | Explicit total runtime/session/byte quotas, cooperative stop, fresh auth/catalog and health summaries; no auto-start/unknown interval bridging/certified days invented | High | COMPLETE scoped implementation2026-11-06;319 nativePG/TLS/Docker PASS; real account acceptance unverified |
| P2-003I | P1 | P2-003H | Safe operator capture preflight | Local config/schema/metadata/token-expiry/calendar/quota checks, private readiness and CLI guidance; no secrets/automatic capture/account-certification claim | Medium | COMPLETE scoped implementation2026-11-06;335 PG tests; actual host blocked missing credential/unavailable DB |
| P2-003J | P1 | P2-003I | Secure local runtime bootstrap | Protected/preserved DB and admin settings, Docker startup and safe post-setup checks; actual Analytics token via local hidden helper only; no blind overwrite/live promotion | Medium | COMPLETE scoped implementation and actual persistent local startup2026-11-06;348 PG tests |
| P2-003K | P1 | P2-003J | Persistent public instrument metadata onboarding and safe connection-readiness guidance | Current catalog in local DB, provenance/currentness checked; no broker credential in chat and no automatic capture | Medium | COMPLETE2026-11-06:actual persistent6,504 instruments; checksum/counts/lookup/preflight verified |
| P2-003L | P1 | P2-003K; operator-local Analytics credential | Operator credential onboarding and explicit read-only connection acceptance | Hidden local credential/aware expiry; app reload; safe private probe; no automatic capture or secret in chat | Medium | COMPLETE scoped local configuration and real history credential acceptance; exchange-status success operator-reported |
| P2-003M | P1 | P2-003L | Small real historical candle import acceptance | One prior day/catalog-bound index; archive integrity and private reads verified; no observation clock | Medium | COMPLETE2026-11-06:75 Nifty50 five-minute candles for November5 |
| P2-003N | P1 | P2-003M | Rotate exposed local administrator credential and revoke old sessions | Protected replacement, old credential/session rejection, new login, broker/catalog/history preserved | Medium | COMPLETE2026-11-06:old password/session rejected;4sessions revoked;new login/data preservation verified |
| P2-003O | P1 | P2-003N; valid Analytics token/current catalog | Bounded real option-chain acceptance | One explicit catalog expiry; validate source/legs/archive/private read; no freshness guarantees/orders/stream capture | Medium | COMPLETE2026-11-06:135strikes/270legs;72flagged;canonical/catalog/pagination verified |
| P2-003P | P1 NEXT | P2-003O; valid Analytics/current catalog | Bounded actual streaming authorization and decoder acceptance | Finite index-only subscription, safe outcome/diagnostics, no invented tick/day or trading permission | Medium | Pending |
| P2-003 | P1 | P2-003A; P2-002A; optional operator credential for actual data | Candles, chain, approved feed and observation | Real UTC data; freshness/duplicates/gaps/reconnect/session checks; reports only from captured sessions | High | Partial: metadata/history/chain/auth-decoder implemented; bounded socket lifecycle implemented; durable research archive implemented; reviewed calendar/sampled coverage implemented; bounded multi-session supervisor implemented; safe preflight implemented; persistent local bootstrap verified; real acceptance/completed-day certification pending |
| P3-001 | P2 | P2-003 | Knowledge provenance, indicators, controlled research | Licensed sources, completed candles, research cannot alter permissions | High | Not started |
| P4-001 | P2 | P3-001 | Deterministic strategy and affordability interfaces | Whole-lot, spread, stale-data and insufficient-budget tests | High | Not started |
| P5-001 | P2 | P4-001 | Historical option backtester | Point-in-time data, costs, slippage, out-of-sample and no-look-ahead validation | High | Not started |
| P6-001 | P2 | P5-001 | Paper execution/ledger, stop and circuit breaker | Genuine data; partial fills; net costs; independent risk controls tested | High | Not started |
| P7-001 | P2 | P6-001 | Broker compliance, order intents/state/reconciliation | Current official approvals/limits documented; outage/idempotency tests; LIVE remains off | High | Not started |
| P8-001 | P2 | P6-001 | Full dashboard and reporting | All required sections use verified backend state with correct access controls | High | Not started |
| P9-001 | P1 before production | P7-001 | MFA, audit integrity, scanning, backups, network hardening | Security evidence and successful encrypted restore drill | High | Not started |
| P10-001 | P1 before live | All prior gates | Extended paper evaluation and operator approvals | Failure simulations, monitoring and approvals verified; explicit independent authorization | High | Not started |

Never advance a phase based solely on generated source or a dashboard screenshot.

Actual repeat bootstrap: READY_LOCAL, administrator login verified again; .env and private
administrator password bytes unchanged. Both files mode0600; runtime directory0700.
Persistent application/database retained. Secret-pattern source/document/config scan:zero
findings; protected .env/.local excluded. No real broker request or recording started.
Changed files:scripts/bootstrap_local.py, tests/security/test_runtime_bootstrap.py,
docs/LOCAL_BOOTSTRAP.md, README.md, MASTER_PLAN.md, docs/DEPLOYMENT.md and relevant
verification/security/setup/preflight docs; all eight agent_memory handoff files. Operator
.env and .local/runtime generated locally and ignored, never included in source reports.

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
