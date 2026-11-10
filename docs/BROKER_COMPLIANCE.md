# Broker integration evidence — Phase 2 read-only scope

Reviewed: 2026-11-06 UTC. Source: official Upstox documentation linked below.
This is an API integration review, not SEBI/NSE/broker approval for live trading.
No order module, live authorization or broker account verification is implemented.

## Credentials and account access

[Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/):
read-only, generated in Developer Apps, one-year validity, one per account. Market-data
categories work without a static IP; User/Portfolio/account categories require a whitelisted
static IP. Only GET operations are permitted. Our first adapter uses this credential category
and exposes fixed status/history/chain/feed-authorization GET methods. The operator must supply the correct token;
its type is not independently proven by inspecting local text.

[OAuth](https://upstox.com/developer/api-documentation/authentication/) uses authorization code
redirects through Upstox, exact registered redirect URI, optional echoed state, and a backend
form-encoded token exchange. The protocol foundation now makes state mandatory,short-lived
and single-use,bound to a caller-supplied validated administrator session digest. Optional
local configuration,token exchange,browser-bound HTTP callback and UI are implemented
and synthetically verified. Private vault deployment and operator browser consent completed
10 November; authenticated status confirms STORED_UNVERIFIED. This confirms local storage,
not account permissions, data access or trading approval. Analytics remains active.
See [UPSTOX_OAUTH_BROWSER.md](UPSTOX_OAUTH_BROWSER.md). The encrypted
storage component is verified separately in [UPSTOX_OAUTH_VAULT.md](UPSTOX_OAUTH_VAULT.md). See
[UPSTOX_OAUTH.md](UPSTOX_OAUTH.md). No documented granular scope or PKCE parameter was
established in the reviewed pages;do not invent either. Contracts rechecked10November2026.

[Get Token](https://upstox.com/developer/api-documentation/get-token/):
`POST https://api.upstox.com/v2/login/authorization/token`; authorization codes are single-use.
Normal access tokens expire at the next 03:30 IST cutoff. An extended token is described as
read-oriented, but its precise availability, lifetime and endpoint coverage remain unresolved;
we do not use it. No refresh endpoint is assumed. Interactive reauthorization must block
requests after expiry. We do not collect broker passwords, PINs or TOTP secrets.

## Endpoint/version matrix

| Purpose | Verified official contract | Current implementation |
|---|---|---|
| Exchange state | [GET /v2/market/status/NSE](https://upstox.com/developer/api-documentation/get-market-status/) with Bearer and Accept headers | Implemented through administrator/CSRF-protected local probe |
| Account funds V3 | [GET /v3/user/get-funds-and-margin](https://upstox.com/developer/api-documentation/get-funds-and-margin-v3/), Api-Version:3.0 | Reviewed; not implemented; account/static-IP gate required |
| Account funds V2 | [GET /v2/user/get-funds-and-margin](https://upstox.com/developer/api-documentation/get-user-fund-margin/) | Reviewed only; available margin is not assumed withdrawable cash |
| Instruments | [BOD JSON files](https://upstox.com/developer/api-documentation/instruments/); prefer instrument_key over reusable exchange_token | Implemented for NSE indices/index CE/PE/FUT; versioned raw/normalized storage; units unverified |
| Historical candles | [GET /v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/) | Implemented bounded prior-day1/5/15minute subset; synthetic protocol verification only |
| Option chain | [GET /v2/option/chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/) with underlying instrument_key and actual expiry_date | Bounded snapshot capture/storage implemented; actual broker acceptance unverified |
| WebSocket feed | [Market Data Feed V3](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/) and authorized URL flow | Authorization/decoder and bounded socket lifecycle implemented; actual broker acceptance and durable recording pending |

Funds V3 separates usable cash/pledged margin from unavailable/unsettled components. These
must be modeled separately before affordability logic; totals are not withdrawal promises.
Funds V2 documents an overnight service closure (00:00–05:30 IST). Actual entitlements,
account segments and approved IP must be verified with the broker before account integration.

The exchange response contains exchange, status and millisecond last_updated. That timestamp
identifies an exchange-state update, not quote freshness or a continuously recording feed.
Only documented segment statuses are accepted; new unsupported statuses fail validation.
Source: [exchange status](https://upstox.com/developer/api-documentation/get-market-status/),
[status values](https://upstox.com/developer/api-documentation/appendix/market-status/).

Instrument JSON carries contract metadata including expiry, lot and tick sizes. Preserve
point-in-time snapshots. Confirm tick-size units before rupee calculations; do not infer a
unit conversion from examples. Current-day BOD files are not a historical options archive.
Historical V3 minute intervals1–300 and hour intervals1–5 have limited date windows; daily,
weekly and monthly intervals use1. Request-window enforcement and completed-candle checks
are enforced for the implemented prior-day minute subset; broader units remain pending.

Option-chain fields include bid/ask, quantities, volume, OI and Greeks. The reviewed response
does not establish an exchange quote timestamp for every field; a local receipt time cannot
prove freshness. Use explicit expiry dates from verified metadata, not automatic rollover
keywords, for reproducible contract selection. Bounded manual chain capture is implemented; actual broker acceptance remains unverified.

V3 streaming uses Protobuf and binary subscription messages. Normal access documents two
connections; single-category LTPC/Greeks/Full limits are5000/3000/2000, with lower mixed-mode
limits. Plus changes connection/depth entitlements; none are assumed purchased or enabled.
Implement authorized-URL validation, heartbeat/reconnect, ordering, duplicates, gaps and UTC
storage before recording observations. A connectivity probe does not start seven-day tracking.

## Rate limits and sandbox boundaries

[Standard API limits](https://upstox.com/developer/api-documentation/rate-limiting/):
50/second,500/minute,2000/30minutes, per API/user. The implemented manual probe uses a
stricter single-worker cooldown of30seconds; upstream429 uses bounded Retry-After handling.
No automatic retries or production traffic were exercised. Other clients on the same broker
account can consume shared limits and require coordination in future feed services.

[Sandbox documentation](https://upstox.com/developer/api-documentation/sandbox/) lists
specific order operations, not blanket parity with market data or OAuth. Sandbox tokens
are documented for30days. This implementation uses injected synthetic HTTP transports;
no sandbox or live broker result is claimed.

## Live trading gate remains closed

Before Phase7, independently retrieve current official SEBI, NSE and Upstox trading rules,
static outbound IP requirements, applicable registrations/approvals, algo identifiers,
headers, order restrictions and rates. Record exact source/date and operator evidence.
This iteration did not assess those execution permissions or implement an order endpoint.
Do not reinterpret a successful read-only probe as live trading authorization.

Public instrument integration was rechecked against the official NSE download on2026-11-06.
Actual file parsing and PostgreSQL archive succeeded; counts, hash and retrieval/publication
facts are recorded in INSTRUMENT_MASTER.md. This validates the observed public schema, not
exchange authorization, licensed redistribution rights, historical completeness or tick-unit
conversion. No authenticated broker account request was made.

Historical V3 contract rechecked2026-11-06. Implemented conservative prior-day minute research
imports; exact scope/source contract and unresolved identity/session limitations are documented
in HISTORICAL_CANDLES.md. No authenticated history request or additional entitlement approval
was exercised. The expired-instruments API family was reviewed for separation but not built.

## P2-003C — option-chain research (2026-11-06)

Option-chain contract reviewed2026-11-06 using official
[put/call documentation](https://upstox.com/developer/api-documentation/get-pc-option-chain/)
and [overview](https://upstox.com/developer/api-documentation/option-chain/). The bounded
GET snapshot implementation is complete; actual token acceptance/entitlements remain unverified.
No documented exchange quote timestamp is promoted from receipt time. See OPTION_CHAIN.md
for implementation safeguards and raw Greek-unit limitations. No execution approval is implied.

## P2-003D — V3 foundation (2026-11-06)

Official [V3 authorization](https://upstox.com/developer/api-documentation/get-market-data-feed-authorize-v3/)
and feed/schema reviewed. Implemented a restricted GET and server-only one-use grant,
catalog-bound LTPC subscription bytes and bounded Protobuf decoder. No actual authorization,
socket or entitlement test was performed. No connection/Plus entitlement is inferred from
documentation or local bounds. See WEBSOCKET_FEED.md for source hashes, unit/time limitations
and pending transport/observation work. No live permission is added.

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
