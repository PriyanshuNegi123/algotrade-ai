# Safe operator capture preflight

P2-003I checks local prerequisites without obtaining a grant, connecting a socket, writing records,
recovering leases, changing settings or running migrations. A passing result is LOCAL_CHECKS_PASSED,
not broker acceptance, write verification, production readiness or permission to trade.

## Interfaces and behavior

```sh
uv run python -m scripts.capture_preflight --instrument-key 'NSE_INDEX|Nifty 50'
uv run python -m scripts.supervise_capture --preflight-only --instrument-key 'NSE_INDEX|Nifty 50'
```

Both accept the supervisor's bounded runtime/session/byte/event options. The standalone command
returns JSON and exit0 when local checks pass, exit2 for blocked/invalid/unavailable diagnostics.
Invalid configuration errors never forward exception text. Tokens, passwords, database URLs and
socket URLs are not arguments or report fields. Database credentials stay in protected settings.

The normal supervise_capture CLI now runs preflight before recovery or creating parent/child
records. Blockers print the safe report and exit2; passing checks continue only because the operator
explicitly invoked capture. --preflight-only always returns after diagnostics. Configuring secrets,
loading a report or starting the application never starts capture. Existing internal test runners
and single-session stream_feed retain their own runtime checks; preflight is not an authorization
capability or a universal hook that bypasses/rewrites those controls.

Administrator GET /api/observations/preflight accepts repeated instrument_key (1–100), plus optional
total_seconds, session_seconds, max_sessions, max_payload_bytes, max_events. Invalid inputs422,
unauthenticated401; valid requests200 even when diagnostics are BLOCKED. Existing DB-backed admin
authentication must work to use the HTTP route; use the host CLI when the DB itself is unavailable.
No POST/start/stop/configuration-write route exists. The API accepts no caller as-of date, secret,
calendar URL/path or certification flag. No frontend or schema change was introduced; head0006.

## Checks and limits

| Area | Behavior |
|---|---|
| Configuration | Validated Settings; OBSERVATION required and live flag false; absent admin dashboard hash is a warning for host capture |
| Credential | Configured token plus declared aware expiry; block missing/expired or remaining lifetime not exceeding total budget+60seconds |
| Database | Reachability, PostgreSQL required for operator capture; SQLite reports DATABASE_TEST_ONLY |
| Schema | Shared read-only revision/table probes also used by /health/ready; no migration or automatic table creation |
| Permissions | Required INSERT/UPDATE table grants checked individually with current_user; schema/metadata reads exercise SELECT |
| Metadata | Reuses current-catalog key/type/expiry resolver in the same read snapshot; stale/missing/unsupported/expired keys block |
| Existing local recording | Unexpired RUNNING parent or session blocks another supervised CLI launch; rows are not closed or recovered by preflight |
| Calendar | Verify bundled evidence integrity, expose review/window; unknown derivative hours/year block; out-of-session and index-reference limits warn |
| Quotas | Existing CapturePolicy bounds; at least3 initial events and canonical PLAN size+64byte reserve; short/oversubscribed windows and report-cap mismatches warn |

PostgreSQL uses a repeatable-read READ ONLY snapshot with2second statement timeout. The shared
schema probes use fixed identifiers; permission function parameters are bound constants. The
[PostgreSQL privilege inquiry contract](https://www.postgresql.org/docs/current/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE)
allows inspecting grants without attempting writes. Each required privilege is checked separately;
a comma-separated list would test whether any listed privilege is held. The preflight does not
grant permissions or inspect/expose database credentials.

TABLE_GRANTS_PRESENT is deliberately narrower than a successful write:row-level policies,
constraints, future outages, concurrent storage pressure and filesystem capacity are not tested.
The result always retains database_writes_verified=false. No write-and-rollback probe is performed.
The PLAN reserve proves only room for the initial metadata record; full snapshots/updates can be
larger and runtime quotas still apply. Preflight cannot reserve capacity or guarantee the complete
requested session count/time budget. It is a snapshot, not a lock against another process starting
immediately afterward; other broker consumers/account limits remain unverified.

Credential expiry/type are operator-declared, not cryptographically certified or tested against
Upstox. Preflight never obtains tokens, redirects, funds or market data. broker_access_verified=false
always. Current runtime checks still validate credentials/catalogs at connection time; preflight
cannot authorize a later operation after its conditions have changed.

The bundled NSE FO calendar remains a reviewed baseline with amendment completeness unverified.
Integrity failure blocks all checks; unknown FO hours/year block FO capture planning. Calendar
coverage for an index reference is not inferred from FO hours and is explicitly warned. Quiet or
closed sessions can still be researched:OUTSIDE_REVIEWED_SESSION is a warning, not a false claim
that the market is open. Health, source/tick units and complete-day evaluation remain separate gates.

## Report contract

The response includes checked_at, state, can_attempt_capture, safe per-area checks, blocker codes,
warning codes, fixed next_actions, requested keys/policy, catalog version, PLAN reserve and reviewed
calendar context. It never serializes Settings, raw exceptions, bearer values, password hashes,
DSNs or socket grants. Local pass leaves all of these unchanged:

- broker_access_verified=false and database_writes_verified=false;
- recording_started=false, observation_started_at=null and qualifying_observation_days=0;
- entries/live/signal/execution flags=false.

No preflight result automatically certifies a phase, launches a job or promotes a trading mode.
Invalid/local-error CLI diagnostics are also safe fixed JSON, not exception tracebacks.

## Actual verification and current setup

335 pass on disposable PostgreSQL17.11; default313 pass/22 PG skip.16 new cases cover missing/
expired/short-lived credentials, test/unavailable/mismatched/missing schema, stale/missing keys,
active records/no mutation, mode/PLAN budgets, calendar integrity/scope, private endpoint/input
validation, CLI redaction/gating, successful native local-only checks and revoked table privileges.
Ruff81/mypy36/lock pass; no dependencies changed. Real loopback TLS supervision regression passes.
See VERIFICATION.md for Docker checks. No frontend/browser change or real broker request.

The actual workspace preflight ran2026-11-06T14:05:41Z and returned BLOCKED:CREDENTIAL_MISSING
and DATABASE_UNAVAILABLE. Administrator dashboard configuration was also absent (warning).
This was an honest read of the current local setup, not a test failure or a request for secrets.
No .env or persistent application DB was provisioned. Temporary test databases were removed.

Next P2-003J:secure local runtime bootstrap for PostgreSQL/admin configuration, protected settings,
Docker startup and safe post-setup checks. An actual Analytics credential must be entered only
through the existing local hidden helper, never chat, browser fields or command arguments. Real
broker acceptance and genuine observation-day evidence remain unverified gates.

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
