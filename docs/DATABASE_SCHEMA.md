# Database schema

Migration chain: `0001_sessions` → `0002_instruments` → `0003_candles` → `0004_option_chain` → `0005_observations` → `0006_capture_runs` (current required revision).
Back up before applying or downgrading migrations. Downgrading0002 deletes the catalog and
archives; it leaves administrator sessions intact, but updated application readiness fails
until the new schema is restored.

| Table / column | Type | Rule |
|---|---|---|
| admin_sessions.token_digest | varchar(64) | SHA-256 hex primary key; no raw session ID |
| admin_sessions.csrf_digest | varchar(64) | Required SHA-256 hex digest |
| admin_sessions.expires_at | timestamptz | Required, indexed; UTC instant |
| alembic_version.version_num | Alembic-managed varchar | Must equal current revision for readiness |

Expired sessions are deleted on successful login. Application checks expiry on every use.
No user password, broker token, orders, positions, balances or live tick tables exist.
Validated historical candle tables now exist; no actual broker history was ingested here.
Use PostgreSQL in all non-test environments. SQLite is allowed only with APP_ENV=test.
Database URLs are secret configuration and must not be logged. Migration downgrade deletes
all sessions and requires administrators to sign in again.

Verified on PostgreSQL 17.11 using SCRAM and a non-superuser database owner: migrations
up/down, aware timestamptz expiry, expired-session cleanup, revocation and session durability
across application recreation. Each integration test creates/drops only a unique schema;
existing schemas and their migration state are not reset. Docker migrations, session persistence across app restart and DB outage/recovery also passed;
no permanent application database was provisioned by the smoke run.

## Instrument catalog

| Table | Key / columns | Purpose |
|---|---|---|
| instrument_snapshots | id64 primary key; source_url; source_modified_at/retrieved_at/imported_at timestamptz; sha256; source_records/selected_records; raw_gzip bytea | Immutable source archive, first-observed provenance and idempotence |
| instruments | snapshot_id FK + instrument_key composite primary key; segment/type/symbol; underlying_key; lot/minimum_lot; tick_size_raw/strike_price numeric24,8; tick_size_unit; expiry timestamptz | Per-snapshot normalized index/derivative metadata |

Import/retrieval timestamps are indexed; snapshot/underlying/type/expiry has a contract index.
Positive lot/tick and allowed instrument-type checks supplement full application validation.
Index metadata leaves derivative-specific fields null; no default single-unit lot is invented.
Raw gzip is deferred during normal queries. Transactional bulk batches500 preserve all-or-none
visibility. No credential columns, automatic deletion or data-mutation API were added.
As-of selection uses import time and the latest applicable source universe. See
INSTRUMENT_MASTER.md for scope, units/freshness limitations and executed PostgreSQL evidence.

## Historical candle batches

| Table | Keys / data | Purpose |
|---|---|---|
| candle_imports | id64; composite catalog FK(snapshot_id,instrument_key); type/interval/dates; source URL and response/canonical hashes; UTC retrieval/import; row/gap counts, source_order; deferred canonical_payload | Immutable research-batch provenance and deduplication |
| candles | import_id FK + UTC opened_at primary key; closed_at; OHLC numeric24,8; volume/OI bigint | Ordered per-version historical bars |

Constraints enforce interval1/5/15, nonnegative counts/quantities, coherent positive OHLC and
close time after open. imported_at is indexed; per-import timestamp PK supports cursor reads.
Canonical archive includes only validated fields, never raw unknown broker/credential fields.
Atomic batches500 and catalog FKs preserve lineage. No automatic retention deletion is added.
Downgrading0003 deletes candle batches/bars and preserves catalog/admin sessions; updated
application readiness fails until schema restoration. Back up before any downgrade.

## Option-chain snapshots

| Table | Keys / data | Purpose |
|---|---|---|
| option_chain_snapshots | id64; composite catalog underlying FK; expiry date; source/hash fields; receipt/import timestamptz; strike/leg/flag counts; deferred canonical bytes | Immutable catalog-bound receipt provenance |
| option_chain_legs | snapshot/key PK; catalog option composite FK; CE/PE, strike/lot, spot/PCR, price/spread numeric, quantities bigint, Greeks/flags JSON | Sanitized per-contract observations |

Prices use numeric24,8; PCR numeric30,16; Greeks retain validated decimal strings (up to16
fractional places). Positive strike/lot, CE/PE, nonnegative quantities/quotes and positive
noncrossed bid/ask checks supplement application validation. Receipt/import times are indexed.
Atomic bulk inserts preserve all-or-none visibility. Same receipt deduplicates; later receipts
of identical prices remain separate. Revision0004 downgrade removes chain tables only;
sessions/catalog/candles survive. See OPTION_CHAIN.md. No raw broker body/token is stored.

## P2-003D — V3 feed foundation (2026-11-06)

No new tables or migration. V3 plans refer to existing current instrument snapshots; decoded
frames remain in memory/offline output only. Current revision stays0004_option_chain. Durable
feed/observation storage and lifecycle audit events remain pending.

## P2-003F — durable observation schema

observation_sessions stores source/schema/policy, aware UTC lifecycle/lease times and bounded
counters/accounting. observation_attempts uses session/number PK and catalog snapshot FK.
observation_events uses session/sequence PK, attempt composite FK, unique session/canonical
hash and deferred JSON. Creation/lease timestamps indexed. Per-event row lock/transaction
updates payload and counters atomically. No credential URL/raw frame column exists. Downgrade
0005 removes these three tables only. See OBSERVATION_STORAGE.md for bounds/recovery semantics.

## P2-003H — capture parent ledger

capture_runs stores source, requested keys/policy, indexed aware UTC creation/lease/end/recovery,
status/reason, session/event/canonical-byte counters and normalized diagnostics. Nullable indexed
observation_sessions.supervisor_id references it. Parent-before-child row locking and one append
transaction enforce aggregate budgets. Existing standalone observations remain null-linked.
Downgrade0006 removes grouping/parent counters while preserving child archives; back up first.
No secret URL/raw credential column. See CAPTURE_SUPERVISION.md.
