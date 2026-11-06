# Versioned instrument master

Implemented scope: official NSE indices plus index CE/PE/FUT metadata. Equity, currency,
stock-option and other exchange records are counted in the source but not normalized in this
slice. Futures metadata does not enable futures trading. No metadata record enables execution.

Official source verified 2026-11-06:
https://upstox.com/developer/api-documentation/instruments/
https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz

The real reviewed file has distinct index/derivative schemas. Index lot/tick/expiry fields
remain null; derivatives require valid lot, raw tick, expiry, underlying and option strike.
No hardcoded current lot size or tick-to-rupee conversion is used. The source tick value is
stored exactly as decimal with BROKER_UNVERIFIED unit. Downstream execution must resolve it.

## Import and operator controls

For host-based operation, first apply migrations to a PostgreSQL database reachable from
the host via DATABASE_URL. For Docker deployment, Compose migrates automatically; sign in
and use the dashboard control, since its private DB is not host-published. Host commands:

```sh
uv run alembic upgrade head
uv run python -m scripts.sync_instruments
```

No broker token is needed. The CLI uses only the fixed official public source, validates the
entire catalog before any write, then commits the archive and selected records atomically.
Do not point development commands at an unrelated database. The optional secure local bootstrap creates protected missing database/admin settings;
see LOCAL_BOOTSTRAP.md.

Alternatively sign into the dashboard and choose **Import official NSE metadata**. The API
requires administrator session, exact allowed Origin and CSRF header. An in-process lock
rejects simultaneous imports409; attempts have a five-minute cooldown429. Download or
validation failures503 preserve the prior successful snapshot. Exactly one API worker is
supported. CLI imports are explicit operator actions, not scheduled retry loops.

GET status and lookup never fetch the source. The dashboard displays local counts/publication
and import times in IST. No import starts quote capture or the seven-day observation clock.

## Bounded untrusted-data handling

- Fixed HTTPS host/path; no token, redirect following, proxy discovery or automatic retries.
- Ten-second HTTP operation timeouts; a45second streaming budget checked between reads.
  A blocked network read may consume its operation timeout before the budget is rechecked.
- At most16MiB compressed and128MiB decompressed data; at most300,000 total/50,000 selected rows.
- Incremental gzip inflation in64KiB chunks and UTF-8/JSON array parsing, with a64KiB per-record
  byte limit; the entire decoded master is not materialized in memory.
- Reject corrupt/truncated/concatenated gzip, trailing JSON, duplicate fields/selected keys,
  malformed rows, missing underlying indices, invalid numbers and incompatible schemas.
- Require a timezone-aware CDN Last-Modified; reject publication over36hours old or more than
  five minutes in the future. This is a conservative application policy, not an exchange
  trading-calendar guarantee. Holidays/weekends may reject an otherwise latest available file.
- CURRENT_METADATA additionally requires the source publication date to match today's IST
  date and retrieval within24hours. Otherwise the preserved snapshot is STALE_METADATA.
  Neither state grants execution eligibility or certifies lot sizes against exchange notices.

## Persistence and historical correctness

Migration0002_instruments creates instrument_snapshots and instruments. The source archive
contains exact gzip bytes, SHA-256, official URL, publication, first retrieval and import UTC
instants, plus total/selected counts. Raw bytes are deferred on normal reads and never returned
by API. Snapshot identity hashes URL/publication/content; repeat imports do not overwrite the
original retrieval/import times. Changed content creates a new immutable snapshot.

Normalized instrument rows use a composite snapshot/key primary key and an indexed contract
lookup. Inserts use batches of500 in one transaction; an interruption rolls everything back.
A concurrent identical transaction resolves through the snapshot primary key. No edit/delete
API exists. Database administration still requires protected access and backups.

As-of lookup filters snapshots by import time first, then chooses the latest source universe
and looks up the key inside it. Source publication alone never backdates what the application
knew. A removed contract does not reappear from an older snapshot. Query timestamps must have
a timezone and are normalized to UTC. Retrieval starts no pre-existing historical universe:
the catalog only preserves snapshots actually captured from now onward.

The expiry timestamp/date is broker metadata, not a verified intraday exchange cutoff. A
future execution gate still needs calendar/session/settlement and expiry-trading-window rules.
No automatic retention deletion exists; estimate source-archive growth and plan backups before
long-running deployments. This snapshot is not a historical option-premium dataset.

## Executed evidence

2026-11-06: full native PostgreSQL suite **113 passed, zero skipped**; default106 passed/seven
PostgreSQL checks skipped. Real public import into a disposable SCRAM/non-superuser PostgreSQL
database successfully processed83,940 source rows and stored6,504 selected records.
Source Last-Modified:2026-11-06T00:04:11Z; retrieved2026-11-06T11:56:48Z.
SHA-256:a0f03852e2b918ec41c8c538acee34c6d7a19856c4b2fff88136be0c21d72b56.
That temporary database was stopped/removed. No permanent operator database was provisioned.

Reproduce explicit real public-data verification alongside isolated tests:

```sh
uv run python -m scripts.verify_postgres --bin-dir /path/to/postgresql/bin --check-public-instruments
```

Normal pytest blocks actual HTTPX transports and uses synthetic fixtures. Real-source fetching
occurs only through the explicit optional verification flag outside pytest. Docker checks
passed new schema/startup/private catalog/CSRF controls and existing restart/outage recovery.
Chrome synthetic import/cooldown/logout checks passed at390/768/1440px without overflow or
captured JS exceptions. No broker-account, prices, paper fills, observations or returns claimed.

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
