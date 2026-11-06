# Durable bounded research observations

P2-003F adds durable research sessions, catalog-bound attempts and canonical events to the
bounded LTPC CLI. It does not certify market-session completeness, seven observation days,
signals or trading. Actual authenticated broker capture remains unverified; all recorded
verification data is explicitly SYNTHETIC. No genuine observation days are claimed.

## Schema and lifecycle

Apply `alembic upgrade head` to revision `0005_observations`. Readiness checks all three new
tables and the current revision. The migration preserves administrator sessions, catalog,
history and option-chain data. Downgrading0005 deletes observation data only; back up first.
The updated app remains unready until its required schema is restored.

| Table | Durable facts |
|---|---|
| observation_sessions | Random32hex ID, source, pinned schema hash, requested keys/policy, status/reason, UTC creation/lease/end/recovery, counters/bytes, monotonic duration and conservative sampled intervals |
| observation_attempts | Session/attempt1–3 PK, catalog snapshot FK, exact subscribed keys |
| observation_events | Session/sequence PK, attempt composite FK, kind, original observed UTC/elapsed time, canonical SHA-256 and allowlisted JSON |

Session IDs are generated before network access. Source is UPSTOX_V3 for the operator-run CLI,
SYNTHETIC for fixtures; this is provenance labeling, not cryptographic broker attestation.
The schema hash identifies the pinned published V3 contract. Attempt metadata binds normalized
instrument identities to the catalog selected before authorization. Credential-bearing socket
URLs, tokens, headers, unknown broker fields and raw binary frames are never stored.
Generation, original receipt, last-trade and recorder-observed timestamps remain separate.
Canonical validated decimal strings preserve the decoder's wire-double limitations.

The runner now emits a PLAN event before obtaining each grant. Events include original UTC
observed_at and monotonic elapsed_ms. Accepted observations, health diagnostics, duplicate/
out-of-order counters, IDLE, DISCONNECTED and BACKOFF events are recorded. Reconnect creates
new attempt lineage and resets sample continuity. No loss count or filled data is invented.
Only allowlisted safe reasons and normalized schemas enter archives; unknown stop text becomes
UNCLASSIFIED_STOP. No secret or upstream error body is echoed through reads or CLI errors.

## Atomicity, bounds and cancellation

Each event transaction locks its session row, checks state/catalog/keys/time/size, assigns the
next sequence, stores event JSON/hash and updates counters/accounting together. PostgreSQL
row locks serialize concurrent writers. Repeating an identical canonical receipt is idempotent,
including after closure; it does not alter counters or timestamps. There are no edit/delete APIs.
SHA-256 detects content identity; it is not tamper-proof auditing or a signed broker receipt.

Limits:100 keys,3 attempts,11,000 events,256KiB canonical bytes/event and32MiB canonical payload
bytes/session. Database/index overhead is additional. Existing run bounds remain1–300seconds
and10,000 decoded frames. JSON payloads are deferred for metadata reads and loaded in one
bounded event-page query. PostgreSQL statement/lock timeouts are1second for writer transactions;
SQLite is test-only. No retention, quota scheduler or backup automation is introduced.

The asynchronous writer serializes operations and waits for an in-flight database thread to
finish before propagating cancellation or closing the session. A sink timeout therefore cannot
silently race a late event commit with finalization. Individual transactions remain atomic on
failure. Cancellation may exceed the nominal2second sink deadline while waiting for database
checkout/connection/I/O to settle; it does not forcibly terminate a database thread. If the DB
is unavailable and finalization fails, the CLI exits with a safe error and leaves recovery to
the lease mechanism. No false CLOSED result is printed. Normal cancellation records its actual
monotonic elapsed duration; a process kill cannot supply a reliable final duration.

## Crash and restart semantics

A session lease expires at creation + configured duration +60seconds grace. No automatic
resume exists. Reads show a still-RUNNING expired lease as ABANDONED without mutating data.
Before a new CLI session starts, a bounded recovery pass marks up to100 expired sessions
INTERRUPTED/LEASE_EXPIRED, clears interval continuity and records recovered_at. It leaves
ended_at and unknown run duration null; recovery time is never presented as the actual stop.
Unexpired sessions are untouched. Old sessions and events remain readable across app restart.
Expired/interrupted/closed sessions reject new receipts. A new run always has a new identity.
This recovery pass is not a continuous daemon or a cross-process broker connection scheduler.

## Capture accounting

`run_elapsed_ms` describes the monotonic bounded runner duration when known. It includes
connection attempts, idle/backoff and processing; it is not captured market coverage.
`observed_interval_ms` is a conservative sampled span only:sum the smaller positive receipt
and monotonic deltas between adjacent persisted nonempty accepted source samples of the same
attempt, when both deltas are <=10seconds and the new source frame is not delayed >10seconds.
PLAN/status/idle/disconnect/backoff/empty/duplicate-only/out-of-order events break continuity.
No time before the first sample, after the last sample or across reconnect is credited.

This span does not prove all-key coverage, every exchange tick, market-open status, executable
freshness or a completed trading day. Synthetic spans are explicitly labeled as such. Every
session reports calendar_verified=false, qualifying_observation_days=0, and false signal/
execution eligibility. Global observation_started_at remains null. Wire precision, absent
sequence numbers, market calendars and actual broker acceptance remain unresolved gates.

## Interfaces

The explicit host CLI now records by default to its configured PostgreSQL before printing
normalized events; no separate token or URL parameter is accepted:

```sh
uv run alembic upgrade head
uv run python -m scripts.stream_feed --instrument-key 'NSE_INDEX|Nifty 50' --duration 60
```

Use protected local server credentials and a current catalog. Host commands require a DB
reachable from the host; Docker's private DB remains unpublished. The application does not
start a feed job automatically. No HTTP start/stop/mutation or dashboard controls were added.

Administrator-only reads:

| Route | Bounds |
|---|---|
| GET /api/observations/sessions | Default20/max50 session metadata; optional32hex after cursor; sorted by ID |
| GET /api/observations/sessions/{id} | Default20/max50 ordered events; optional nonnegative sequence after cursor; attempt lineage included |

Invalid IDs/cursors/limits422, missing session404, unauthenticated401; database/schema outages
fail closed. Private responses never return the internal interval checkpoint. Cursor ordering
is explicit; session IDs are random rather than chronological. Existing session/CSRF rules are
unchanged. No write permission can be obtained from these routes.

## Verification and next task

Full native PostgreSQL suite276 pass/zero skipped; default260 pass/16 PostgreSQL skipped.
New coverage includes canonical receipts/pagination, interval breaks, malformed/unsafe events,
atomic rollback/storage cap, catalog/tick mismatch, crash recovery, private routes, integrated
runner recording, cancellation during commit, concurrent row locking, restart and downgrade/
upgrade retention. Ruff66/mypy29/lock pass; no dependencies changed. Docker verifies new tables,
private reads and a closed zero-event SYNTHETIC session surviving restart with zero sampled
span/days. Real loopback TLS/redirect regression passes; no real broker call or frontend change.

Next P2-003G:explicit NSE session/calendar and coverage policy, holiday/source provenance and
bounded observation coverage reporting from stored genuine events. Missing data must remain
unknown; tests may use synthetic calendars labeled as fixtures. No fabricated seven-day result,
strategy permission or automatic promotion of phase/live mode.

## P2-003G — calendar/coverage baseline (2026-11-06)

P2-003G adds versioned NSE derivatives calendar evidence and bounded read-only per-key sampled
coverage; see CALENDAR_COVERAGE.md. It recomputes conservative unions without altering original
archive counters or leases. Calendar completion and certified days remain false/zero. Current
schema0005 unchanged; no report starts capture or enables a strategy.

## P2-003H — bounded supervision (2026-11-06)

0006_capture_runs adds optional parent grouping and transactional aggregate quotas; see
CAPTURE_SUPERVISION.md. Standalone records remain supported; current schema0006 required.
Parent quota accounting is in the same event transaction. Child sampled intervals retain
continuity breaks; no cross-child span or completed-day inference is introduced.
