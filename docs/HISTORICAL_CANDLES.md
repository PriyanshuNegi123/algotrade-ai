# Historical minute candle ingestion

Implemented Phase2 slice: manual, authenticated research import of prior-day1/5/15minute
bars over at most28 calendar days. No signals, simulated fills, live orders, automatic quote
capture or observation clock are enabled by an import. All eligibility flags remain false.

Official contract rechecked2026-11-06:
https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
The verified route is GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to}/{from}.
The response is status/data/candles; each documented tuple contains timestamp, OHLC, volume
and OI. The timestamp marks bar start. V3 offers more units/intervals and request windows;
this implementation intentionally supports the smaller minute subset above, requests explicit
inclusive dates and enforces the documented January2022 minute-history floor.

Expired contracts have a separate documented API family:
https://upstox.com/developer/api-documentation/expired-instruments/
That path is not implemented or silently substituted. No undocumented token refresh is used.

## Operator setup and import

Apply current migration0003_candles and configure database/admin access as in README. Configure
the optional Analytics credential only through protected server settings/local hidden-prompt
helper (UPSTOX_SETUP.md). Do not paste credentials into chat, UI inputs or shell arguments.
Import public instrument metadata first. Then sign in and use **Historical candles**:
select a catalog instrument key, interval and historical IST dates, then import explicitly.
The form defaults to a recent historical range but never submits automatically.

For host-based operation with PostgreSQL reachable through DATABASE_URL:

```sh
uv run alembic upgrade head
uv run python -m scripts.import_candles --instrument-key 'NSE_INDEX|Nifty 50' --interval 1 --from-date 2026-11-02 --to-date 2026-11-05
```

Dates and example key are illustrative; resolve a key from your imported catalog and use an
allowed date range. Docker Compose applies migrations at startup; use the dashboard because
its private DB is not host-published. Actual local operator configuration and one-day real import were subsequently verified; see the latest evidence below.

## Validation and credential boundary

- Request model forbids extra fields, unsupported intervals, URL/path characters in keys,
  reversed/oversized windows, pre-2022 history and dates including today's IST session.
- Resolve the key/type/snapshot from the latest observed catalog BEFORE contacting the broker.
  Reject missing metadata, already expired derivatives and requests beyond contract expiry.
- Build a fixed official HTTPS GET URL with an encoded key. No selectable host, method,
  redirect following, proxy discovery, automatic retry or order path is exposed.
- Missing/expired credentials produce no broker request. HTTP401/403/429/timeouts map to safe
  codes without forwarding broker bodies.30second cooldown; bounded upstream Retry-After.
- Ten-second total request deadline, five-second HTTP timeouts, identity encoding and a3MiB
  response limit. Unexpected compression is rejected before decoding. At most12,000 bars.
- Reject malformed/duplicate-field JSON, non-finite numbers and non-seven-field tuples.
- Require aware timestamps within requested IST dates, minute alignment and close<=retrieval.
  Normalize to UTC. Reject duplicate times/mixed ordering; preserve source order and normalize
  strictly ascending or descending input to ascending stored/query order.
- Validate positive exact OHLC decimals (24digits/8places), coherent high/low bounds,
  nonnegative bounded integral volume/OI. Explicit null OI remains unknown, never converted0.
- Report potential missing intraday bars between returned points. Never interpolate or invent
  flat/zero-volume bars. Overnight breaks and absent entire sessions are not counted as gaps;
  trading calendar/session completeness is NOT verified by this slice.

The reviewed response does not guarantee an instrument echo. Identity is bound to catalog
metadata and request path; conflicting optional echoed keys are rejected. API labels this
REQUEST_PATH_ONLY, not independent proof of historical instrument identity. Current metadata
cannot establish a point-in-time option universe before first capture. INDEX/CE/PE/FUT type
is preserved; underlying candles must never be treated as executable option premiums/fills.

## Immutable persistence and reading

Migration0003_candles adds candle_imports and candles. Batch metadata includes catalog FK,
key/type, interval/range, source URL, raw-response hash, canonical validated-data hash,
retrieval/import UTC instants, row/gap counts and source order. Only validated canonical fields
are archived—unknown upstream fields and credential echoes are discarded, not persisted.
Canonical payload is deferred on normal queries and never returned to the browser.

Bar rows use batch/time primary keys, exact decimals, bigint quantities and UTC open/close.
All metadata/bars commit atomically in batches500 or roll back together. Identical canonical
content/request/catalog snapshot deduplicates without changing first-known timestamps.
Revisions and overlapping imports retain independent versions rather than overwrite history.
Dedup keeps the first response hash/order; it is not a log of every repeated request.

GET /api/candles/status is local-only. GET /api/candles/batches/{id} paginates ascending UTC
bars (default200/max500) with an aware next_after cursor. No raw payload/credential exposed.
POST /api/candles/import requires administrator session, exact Origin and CSRF header.
Empty broker results are explicit EMPTY batches, never fabricated candles. Nonempty data is
NOT_SESSION_VERIFIED or GAPS_UNVERIFIED, with signal_eligible/execution_eligible false.
A research import does not certify fee/slippage assumptions, profitability or actual fills.

## Verified results and remaining gaps

2026-11-06: native PostgreSQL suite152 passed/zero skipped; default142 passed/ten PostgreSQL
checks skipped. Ruff42 files/mypy16 backend files/lock freshness pass. Docker migration,
private history status/CSRF and existing restart/outage smoke pass. Chrome synthetic history
form/import/counts/throttle/logout and390/768/1440px checks pass without overflow/JS exceptions.
All historical broker responses were synthetic; no authenticated broker candle request made.
No historical prices are claimed as genuine captured market data. Temporary resources removed.

Remaining: actual credential/entitlement acceptance, other bar units/intervals, current-session
intraday API, expired-instrument history, calendar/session completeness, option chains,
WebSocket capture and real observation reporting. Normal pytest retains actual HTTP blocking.

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
