# Architecture

A single deployable FastAPI application serves a same-origin vanilla frontend.
PostgreSQL stores administrator sessions through SQLAlchemy; Alembic owns schema changes.
There is no task scheduler, market feed, risk engine or order executor yet.
Empty module directories reserve boundaries and are not implementation claims.

`Settings → app factory → engine → schema readiness → authenticated read-only API`

Authentication uses Argon2id and random opaque session identifiers. Only SHA-256
digests of session and CSRF tokens are persisted. Session validity is checked for every
private request; expiry never slides. Logout deletes the durable session.

Public shell contains no financial data. Private overview returns null for unavailable
financial metrics; no broker account state is inferred from an empty result.
Readiness checks the session table, expected migration revision and configured admin.
Readiness does not enable trading. Liveness deliberately survives database failures.

Use one application worker. Login throttling is bounded in-memory and resets on restart;
shared throttling and perimeter restrictions are required before scale-out.
Future order execution requires a separate deterministic risk gate and durable single-writer
intent/reconciliation workflow. Research cannot reach that execution boundary directly.

Primary references checked 2026-11-06:
- https://fastapi.tiangolo.com/advanced/events/
- https://fastapi.tiangolo.com/tutorial/security/first-steps/
- https://docs.sqlalchemy.org/en/20/core/engines.html
- https://alembic.sqlalchemy.org/en/latest/tutorial.html
- https://docs.astral.sh/uv/concepts/projects/sync/

Phase 1 verification now includes actual PostgreSQL 17.11 using a temporary native cluster.
Dedicated scripts isolate native clusters and Compose projects with generated credentials.
Compose configuration and actual Docker image/build/auth/non-root/restart/database-outage
checks pass locally. Production and trading behavior remain outside this foundation scope.
Textual LIVE_ENABLED=false is normalized before literal-false validation so environment-based
startup works without broadening permission to enable live execution.

Phase2 first slice: a dedicated ReadOnlyUpstox adapter supports only the fixed official NSE
exchange-status GET operation. BrokerMonitor serializes manual checks with a30second cooldown
and discards success as current connectivity after60seconds. No state is trading authorization.
Administrator-only routes expose an allowlisted snapshot and require existing Origin/CSRF
controls for the manual check. Broker tokens use server secret configuration, not session
storage or PostgreSQL. OAuth and recording services remain separate pending work.
HTTPX is now a locked runtime dependency; no new package version was introduced. Outbound
HTTP is blocked in pytest except injected mock transports. Source review is recorded in
BROKER_COMPLIANCE.md; setup and failure semantics are in UPSTOX_SETUP.md.

HTTPX references verified for the adapter implementation on2026-11-06:
- https://www.python-httpx.org/async/
- https://www.python-httpx.org/advanced/transports/
- https://www.python-httpx.org/environment_variables/

Instrument service: fixed public source → bounded gzip/streaming JSON → scoped strict
metadata validation → one transactional snapshot+normalized-row archive → authenticated local
status/as-of lookup. The current migration is0002_instruments. Archived source bytes are
stored in PostgreSQL but deferred from normal reads; the dashboard never receives the blob.
Metadata publication, retrieval and import are separate UTC facts. Conservative freshness
rules and BROKER_UNVERIFIED tick units cannot authorize orders. See INSTRUMENT_MASTER.md.

Historical-minute path: typed bounded request → observed catalog key/type/snapshot lookup →
restricted V3 GET → exact OHLCV/aware timestamp/order/completion validation → immutable batch
plus UTC rows in one transaction. Known metadata and historical prices remain separate facts;
all data stays research-only and cannot serve as option fills or authorize signals/orders.
The broker adapter shares one bounded private HTTP transport for status/history public methods.
No raw unknown response fields are persisted. Migration0003 adds catalog-bound candle tables;
local status and bounded cursor queries never issue broker requests. See HISTORICAL_CANDLES.md.

## P2-003C — option-chain research (2026-11-06)

Option-chain request/context/validation/storage live in market_data/option_*.py, separated
from broker transport and private API routes. Exact shared JSON/quantity primitives also serve
history imports. Catalog resolution precedes network; async capture offloads database work.
Immutable sanitized receipts keep UNKNOWN quote freshness and false eligibility. No strategy,
execution or observation recorder is introduced. See OPTION_CHAIN.md.

## P2-003D — V3 feed foundation (2026-11-06)

V3 feed foundation separates brokers/feed_authorization.py (server-only grants), restricted
broker GET, market_data/feed.py (catalog plans/pure LTPC decoding), and pinned generated vendor
classes. Offline scripts.decode_feed normalizes supplied frames without network or persistence.
No connector/background task/API route/state table is added. Frame/trade/receipt times remain
distinct, freshness NOT_EVALUATED and all eligibility false. See WEBSOCKET_FEED.md.

## P2-003E — bounded feed lifecycle (2026-11-06)

brokers/feed_transport.py owns restricted WSS and safe transport errors. market_data/
feed_lifecycle.py owns bounded sessions, per-attempt catalog resolution, ordering, tick filtering
and aged diagnostics. scripts.stream_feed is explicit host-only entry; no app startup job or API
route added. Async sink is bounded; observations stay ephemeral. See FEED_LIFECYCLE.md.

## P2-003F — durable research observations (2026-11-06)

Observation storage separates strict canonical archive schemas, SQLAlchemy session/attempt/event
models, transactional service and read-only admin routes. The runner stamps original observed
UTC/monotonic times and emits PLAN lineage. CLI commits before output; serialized async writer
waits for in-flight threads on cancellation. Lease recovery preserves unknown crash endpoints.
No strategy, automatic startup or calendar certification. See OBSERVATION_STORAGE.md.

## P2-003G — calendar/coverage baseline (2026-11-06)

calendar.py validates/version-hashes bundled NSE evidence and resolves reviewed session windows;
coverage.py aggregates immutable observation payloads inside a bounded consistent read snapshot.
Same-source, per-key sampled intervals union across sessions without bridging discontinuities.
Private GET endpoints and a host read-only CLI add no capture, strategy or execution behavior.
No schema/dependency change. See CALENDAR_COVERAGE.md.

## P2-003H — bounded supervision (2026-11-06)

supervision_models/store provide the durable parent quota ledger. supervisor.py orchestrates
sequential child FeedRunner/ObservationWriter sessions with explicit total budget, rollover
spacing and cooperative stop. Parent-before-child locks make event/byte/stat charging atomic.
Child retry_pending prevents rollover from bypassing unresolved backoff. Host CLI only; private
read APIs expose normalized historical summaries. No auto-start or interval bridging.

## P2-003I — safe capture preflight (2026-11-06)

schema.py shares fixed read-only runtime probes with readiness/preflight. feed.py exposes
resolve_feed_catalog for reuse within one DB snapshot. preflight.py aggregates safe local
checks without transport or storage mutation. Supervisor host CLI checks before recovery/
creation; private GET/standalone CLI return diagnostics. Runtime controls remain independent.
No database/dependency/frontend change. See CAPTURE_PREFLIGHT.md.
