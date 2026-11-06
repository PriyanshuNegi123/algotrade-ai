# Option-chain research snapshots

P2-003C implements bounded, administrator-triggered snapshots. It does not start continuous
observation, produce signals, select contracts or place orders. All eligibility flags are false.
Actual one-snapshot authenticated acceptance verified2026-11-06:135strikes/270legs, expiry2026-11-09.
Freshness remains UNKNOWN; see the latest evidence below. Automated regression tests use synthetic data.

## Source and identity

Official contract reviewed 2026-11-06:
[Put/call option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/)
and [option-chain overview](https://upstox.com/developer/api-documentation/option-chain/).
The adapter constructs a fixed GET to `https://api.upstox.com/v2/option/chain` with encoded
`instrument_key` and `expiry_date` query parameters and server-side bearer authentication.
The documented response includes expiry, underlying identity/spot, strike, PCR, call/put keys,
market data and Greeks. No documented per-field exchange timestamp proves quote freshness.

Only NSE index keys and explicit ISO expiry dates from the current local catalog are accepted.
Past dates and rolling expiry names are rejected. Before network access, resolve the underlying,
expiry and complete, unambiguous CE/PE pairs in one catalog snapshot, including matching pair lots.
Each returned strike, contract key, type, underlying and expiry must match that catalog.
Current metadata is conservative by IST date; weekends/holidays may require a fresh import.
A returned subset of catalog strikes is allowed; no completeness of the full chain is asserted.

## Validation and provenance

- Maximum 3 MiB decoded response and 2,000 strikes; bounded duration, no redirects, proxies or retries.
- Duplicate JSON fields/strikes/legs, malformed objects, nonfinite/negative prices or quantities,
  fractional/out-of-bigint quantities and positive crossed bid/ask are rejected atomically.
- Exact decimal prices, positive catalog strikes/lots and signed Greeks are retained. Delta is
  constrained to CE [0,1] or PE [-1,0]; gamma/vega/IV/POP are nonnegative. Theta may be signed.
  IV/POP/Greek units are preserved as supplied; no unverified percent conversion is performed.
- Missing optional fields remain null; zero quotes and quantities remain zero. Diagnostic flags
  identify missing/zero quotes, liquidity, volume, OI, Greeks and underlying price. Positive
  spread/ask above 20% is a research diagnostic, not a trading risk threshold or permission.
- Missing market data is retained as a flagged research observation; missing contract legs fail.
  An empty upstream list creates an explicit EMPTY snapshot, never synthetic legs.
- UTC receipt/import times, source URL, response/canonical hashes and catalog lineage are stored.
  `freshness=UNKNOWN` and `exchange_timestamp=null` always apply; receipt time proves only receipt.
- Only allowlisted validated data is archived. Unknown fields and credential echoes are omitted;
  the original body is hashed but not stored. Canonical bytes are deferred and never returned.

## Storage and interfaces

Apply `alembic upgrade head` (revision `0004_option_chain`) before starting the updated app.
`option_chain_snapshots` and `option_chain_legs` use catalog foreign keys, exact numeric columns,
UTC timestamps, indexed retrieval and all-or-none bulk inserts of 500 legs. A repeated identical
receipt is idempotent; identical data received later creates a separate observation. No edit,
delete or automatic retention endpoint exists. Backups/retention automation remain future work.
Downgrading 0004 deletes only chain data and preserves sessions/catalog/candles; readiness fails
until current schema restoration. Back up before migration or downgrade.

All routes require an administrator session:

| Route | Behavior |
|---|---|
| GET /api/option-chain/status | Latest local receipt metadata; never fetches upstream |
| GET /api/option-chain/expiries?underlying_key=… | Sorted unexpired local catalog dates |
| POST /api/option-chain/capture | Origin/CSRF-protected explicit underlying_key + expiry_date |
| GET /api/option-chain/snapshots/{id} | Validated legs, limit 1–200 (default 100), instrument-key after cursor |

Invalid schema/catalog/response is 422; missing snapshot 404; absent/expired/rejected credential
503; local/upstream throttle 429 with Retry-After. Capture serializes requests with a 30-second
cooldown; the one-worker in-memory limiter resets on restart. The CLI is an explicit operator
action rather than a persistent shared-rate scheduler. Safe errors never forward broker bodies.

The dashboard loads expiries locally, then captures only on explicit submission. For a host
with its configured PostgreSQL reachable:

```sh
uv run python -m scripts.capture_option_chain --help
uv run python -m scripts.capture_option_chain --underlying-key 'NSE_INDEX|Nifty 50' --expiry-date YYYY-MM-DD
```

Replace YYYY-MM-DD with a date actually present in the current catalog. Supply credentials only
through protected server configuration. Docker's private database is accessed through the
application dashboard; it is not published on the host. No secret argument or dashboard field exists.

## Executed verification

Full disposable PostgreSQL 17.11 suite: 182 passed, zero skipped. Default suite: 169 passed,
13 PostgreSQL skipped. Includes identity, missing/zero values, exact precision, rejected payloads,
receipt versioning, sanitized archives, pagination, auth/CSRF/cooldown, rollback, migration and
restart durability. Ruff lint/format and strict mypy pass. Chrome synthetic expiry/capture/counts,
rate limiting, historical regression and logout pass at 390/768/1440 px with no captured JS errors
or horizontal overflow. See VERIFICATION.md for container evidence.

No genuine chain prices, broker entitlements, freshness, fills, balances or observation days
were verified. WebSocket ingestion, session/calendar rules and seven-day observation remain pending.

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
