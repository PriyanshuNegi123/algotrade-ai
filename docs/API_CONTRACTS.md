# API contracts

Same-origin only; no CORS middleware or cross-origin authorization is enabled.

| Method / path | Access | Result |
|---|---|---|
| GET / | Public | Static shell, no account information |
| GET /assets/* | Public | Frontend files only |
| GET /health/live | Public | 200: process alive |
| GET /health/ready | Public | 200: DB revision and admin configured; otherwise 503 |
| POST /api/auth/login | Allowed Origin required | JSON password (12–256 chars); HttpOnly cookie plus JSON csrf_token |
| POST /api/auth/logout | Admin + allowed Origin + X-CSRF-Token | 204, session revoked and cookie deleted |
| GET /api/overview | Valid admin session | Mode, empty positions/decisions, null financial metrics, disabled execution |
| GET /api/broker/status | Valid admin session | Local broker state only; no upstream call or credentials returned |
| POST /api/broker/check | Admin + allowed Origin + X-CSRF-Token | Manual fixed-endpoint exchange check; no order/data recording |
| GET /api/instruments/status | Admin | Local snapshot counts/provenance/state; no source fetch or raw archive |
| POST /api/instruments/sync | Admin + Origin + CSRF | Fixed-source public metadata import; atomic normalized/archive storage |
| GET /api/instruments/lookup | Admin | instrument_key and optional timezone-aware as_of; one observed-snapshot record |
| GET /api/candles/status | Admin | Local latest immutable research-import metadata; no broker request |
| POST /api/candles/import | Admin + Origin + CSRF | Validated instrument_key/interval/from_date/to_date; fixed V3 history GET and atomic storage |
| GET /api/candles/batches/{id} | Admin | Ascending UTC bars with limit1–500 and optional aware after cursor |

Readiness always reports `entries_enabled:false`. Session TTL is 15 minutes by default,
maximum 30 minutes. Invalid credentials: 401; forbidden origin/CSRF: 403; missing/expired
session: 401; login limit (5 attempts/minute, globally): 429; missing database/schema or
unconfigured administrator: 503. Invalid JSON/schema input: 422 without echoing inputs.
Internal errors: generic 500. Request IDs are server-generated; no client-provided IDs logged.
No order, mode activation, risk mutation, broker OAuth or emergency-switch routes exist.
The emergency switch will be implemented alongside execution permissions, before any live adapter.

Broker check status states: NOT_CONFIGURED/EXPIRED return200 without network requests;
UNVERIFIED means no recent validated response; CHECKED is local connectivity evidence valid
for60seconds. Errors return503 with safe code AUTH_REQUIRED, ACCESS_DENIED, UNAVAILABLE or
INVALID_RESPONSE; local/upstream throttling returns429 with bounded Retry-After. GET status
reports the last safe error state. No raw broker payload, token or authorization header is
returned. exchange.last_updated is a broker exchange-state event timestamp, not a quote time.
The credential_type value ANALYTICS_OPERATOR_DECLARED does not certify actual broker scope.
Probe memory/cooldown resets on restart; entries/live remain false regardless of probe result.

Instrument status: NOT_IMPORTED, CURRENT_METADATA or STALE_METADATA. Sync returns200 after
successful import or deduplication,409 for concurrent import,429 with Retry-After during
five-minute cooldown,503 for safe source/validation/database errors. Lookup returns404 when
no matching key/universe was known as of the query time; naive/future times are rejected422.
All responses keep execution ineligible and orders disabled. Hash/count/date metadata may be
shown to admins; raw_gzip and tokens are never serialized. Upgrade to0006_capture_runs first;
readiness checks both catalog tables and the current revision. Empty catalog does not block
backend readiness because trading is already disabled and import is an operator action.

History import supports minute intervals1/5/15 and a28calendar-day maximum, ending before
today's IST date; no arbitrary URL, unit, token or method field accepted. Unknown/expired
catalog instruments and validation failures422; missing/expired/broker-rejected credentials503;
cooldown/upstream throttling429 with Retry-After. Missing batch404, invalid cursor/ID422.
Success200 can explicitly contain zero bars/EMPTY. Nonempty data remains NOT_SESSION_VERIFIED
or GAPS_UNVERIFIED. No bar import enables signals or execution. Response identity is bound to
request path and catalog, not a guaranteed broker key echo. Refer to HISTORICAL_CANDLES.md.
Readiness now also checks candle_imports/candles at the current migration revision.

Option-chain routes (admin required): GET /api/option-chain/status; GET
/api/option-chain/expiries with underlying_key; POST /api/option-chain/capture with
underlying_key and explicit expiry_date plus Origin/CSRF; GET /api/option-chain/snapshots/{id}
with limit1–200 and optional instrument-key after cursor. Status/expiry reads are local only.
Capture returns200 including explicit EMPTY snapshots; invalid request/catalog/response422,
missing snapshot404, credential/broker failure503, cooldown/upstream throttle429. All snapshots
report freshness UNKNOWN, null exchange_timestamp, false signal/execution eligibility.
No token or raw body is returned. Readiness checks both chain tables and revision0004.
See OPTION_CHAIN.md for exact validation, receipt-version semantics and unit limitations.

## P2-003D — V3 feed foundation (2026-11-06)

No new HTTP/WebSocket endpoint exposes the grant or decoder. The authorization method is
internal and returns a redacted, locally expiring one-use FeedGrant. Socket connection and
stream-control endpoints are not implemented. Existing application routes stay unchanged;
trading flags remain false. scripts.decode_feed operates offline using local catalog state.

## P2-003E — bounded feed lifecycle (2026-11-06)

No new HTTP/WebSocket route or dashboard stream control. Explicit scripts.stream_feed emits
normalized events and a final bounded-session summary to operator stdout. All existing admin/
Origin/CSRF boundaries remain. Observation_started_at stays null; eligibility/live flags false.
A future durable recorder must consume accepted observations and invalidate health on disconnect.

## P2-003F — private observation reads

GET /api/observations/sessions:admin-only metadata, limit1–50/default20 and optional32hex after
cursor (ID ordering). GET /api/observations/sessions/{id}:admin-only session/attempt lineage
and sequence-ordered events, limit1–50/default20 and nonnegative after. Missing404; invalid422;
unauthenticated401; DB outages fail closed. No mutation or feed-start endpoint. Calendar not
verified, qualifying days0 and eligibility false. Apply0005_observations; readiness checks all
three observation tables. See OBSERVATION_STORAGE.md.

## P2-003G — calendar/coverage reads

Admin-only GET /api/observations/calendar:inclusive from_date/to_date<=31dates. GET
/api/observations/coverage:<=7dates, repeated1–20 unique NSE_FO instrument_key values, optional
source UPSTOX_V3(default) or SYNTHETIC. Invalid input/limits422; evidence/corrupt archive/DB
failure503. No mutation/start endpoints. Reports use reviewed schedule evidence, same-source
per-key interval unions and explicit unknown windows; qualifying days0 and eligibility false.
See CALENDAR_COVERAGE.md. Schema remains0005_observations.

## P2-003H — capture summaries

Admin GET /api/observations/captures:ID-ordered metadata, limit1–50/default20, optional32hex
after cursor. GET /api/observations/captures/{id}:read-only consistent parent and<=12 linked
child summaries. Missing404; invalid422; unauthorized401. No start/stop/limit mutation route.
Last health is historical and explicitly health_current=false. All eligibility/live false,
qualifying days0. Required schema0006_capture_runs. See CAPTURE_SUPERVISION.md.

## P2-003I — capture preflight

Admin GET /api/observations/preflight accepts repeated1–100 instrument_key and optional supervisor
quota fields. Bad input422; valid diagnostic report200 with state BLOCKED/LOCAL_CHECKS_PASSED;
unauthenticated401. Existing DB-backed auth must work; standalone host CLI handles DB-unavailable
setup. No POST or settings/start route. can_attempt_capture is local-only, broker/write verification
false, recording_started false, eligibility/live false. Reports omit secrets/DSNs/raw errors.
See CAPTURE_PREFLIGHT.md. Current schema0006 unchanged.
