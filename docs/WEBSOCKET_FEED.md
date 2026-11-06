# V3 feed authorization and decoder foundation

Latest actual acceptance2026-11-06:one20second closed-market Nifty50 connection verified
authorization/subscription/Protobuf/ping-pong/cleanup. One stale snapshot; no durable capture
or certified day. Older unverified-acceptance statements below describe prior iterations.

Current update:P2-003E bounded transport/lifecycle is implemented; see [FEED_LIFECYCLE.md](FEED_LIFECYCLE.md).
The foundation scope below describes P2-003D. P2-003F now adds durable research archives;
see OBSERVATION_STORAGE.md. Calendar-certified observation days remain unavailable.

P2-003D implements internal authorization grants, catalog-resolved LTPC subscriptions and
an offline binary decoder. It does not open sockets or record observation days. Full Phase2
remains incomplete. No genuine authorization grant or market frame was obtained in verification.

## Official contract reviewed 2026-11-06

[Authorize V3](https://upstox.com/developer/api-documentation/get-market-data-feed-authorize-v3/)
provides a one-use authorized connection URL. [V3 feed documentation](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/)
requires binary subscription messages and Protobuf decoding. The server sends market information,
a snapshot and subsequent updates; ping/pong frames maintain idle connections. The
[Analytics credential category](https://upstox.com/developer/api-documentation/analytics-token/)
includes WebSocket access. Actual account entitlements and acceptance remain unverified.

The published [schema](https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto)
is vendored unchanged with SHA-256, official SDK commit provenance and MIT attribution in
backend/vendor/upstox/README.md and SDK-LICENSE. SDK differences are inline comments only.
Generated Python/stub files use grpcio-tools1.76.0 (protoc Python6.31.1). The locked application
runtime is protobuf6.33.6; types-protobuf6.32.1.20260221 is development-only. Compilation tools
are isolated, not runtime dependencies. Generated code is excluded from Ruff; a targeted mypy
exception permits its unparameterized Mapping annotations while application checks remain strict.

## Implemented behavior

- `ReadOnlyUpstox.authorize_feed()` issues only the fixed HTTPS V3 authorization GET through
  existing bounded, expiry-checked, no-redirect/no-proxy/no-retry transport. Response limit16KiB.
  Authentication, timeout, upstream failure and throttling retain safe existing error codes.
- Strict JSON/envelope parsing accepts only a `wss://<single-label>.upstox.com` host with the
  documented exact V3 feed path and exactly one requestId/code pair. Userinfo, explicit ports,
  fragments, control characters, other hosts/paths and excess query parameters are rejected.
  URL-safe16–256-character values are a conservative local policy, not a broker guarantee.
  Unexpected future host/token formats fail closed pending official review.
- `FeedGrant` hides its URL in repr, holds it as SecretStr, and permits one synchronous consume.
  The URL is cleared on consumption/expiry. A60second local lifetime is conservative policy,
  not a documented upstream expiry. Do not log, serialize, persist or send the consumed URL to
  the browser. No public endpoint or CLI obtains/returns grants in this increment.
- `FeedRequest` accepts1–100 unique NSE index/FO keys. `resolve_feed` binds every key to one
  latest current catalog snapshot and accepts only indices/unexpired CE/PE. Futures are excluded.
  The conservative current-catalog IST-date policy still applies on weekends/holidays.
- `FeedPlan.subscription()` returns binary UTF-8 JSON containing a fresh GUID, sub method,
  ltpc mode and resolved keys.100 is a local bound, not a certified broker entitlement limit.
- `decode_frame()` accepts nonempty binary frames <=512KiB. It validates the receipt offset,
  message type, positive representable millisecond generation time, subscribed identities,
  feed count, LTPC oneof/mode and known market-status enums with <=64 bounded segment names.
  Generation time may be at most5seconds after receipt; trade time at most5seconds after generation.
- Negative/nonfinite/excessive prices and negative quantities are rejected. Zero/default
  proto3 scalars stay explicit, flagged for unknown scalar presence; zero trade time becomes
  null. The optional indicative price wrapper retains presence. Unsupported full-depth/Greeks
  modes fail rather than masquerading as LTPC. Empty updates produce no invented ticks.
- Market-info output contains known segment statuses only. CAS/pre-open detail and unknown
  fields are excluded, not interpreted as trading-session permission. Standard Protobuf
  last-value/map semantics apply; this decoder does not implement a second wire parser.

## Time, precision and scope

Wire prices are doubles. Decimal(str(value)) preserves their shortest decimal representation,
not exact original exchange precision; WIRE_DOUBLE_PRICE and PROTO3_SCALAR_PRESENCE_UNKNOWN
flags make this explicit. No tick-unit conversion or alignment is inferred.
`currentTs` is generation time; `ltt` is last-trade time, not the freshness of all quote fields.
Old frames remain valid research inputs. Freshness is NOT_EVALUATED; signal/execution eligibility
is always false. Receipt time and decoder success do not authorize signals, fills or trading.

This foundation is stateless. It does not enforce first-message ordering, detect duplicate
updates, infer sequence gaps, classify staleness, manage heartbeats/reconnects or persist feeds.
Those require the next transport/lifecycle and recording increments. Future connectors must
consume grants only server-side, disable redirects/proxies and URL logging, bound socket frames,
respect shared account connection/rate limits and discard stale subscriptions on reconnect.
The deprecated V2 feed is not used. No schema migration, API route or dashboard control was added.

## Offline use

With the configured PostgreSQL reachable from the host and current metadata already imported:

```sh
uv run python -m scripts.decode_feed --help
uv run python -m scripts.decode_feed /path/to/frame.bin --instrument-key 'NSE_INDEX|Nifty 50' --received-at '2026-11-06T04:00:00+00:00'
```

Use the frame's actual original receipt time and subscribed keys. Output includes only validated
normalized data, never authorization grants. The command does not connect to the broker or
persist decoded frames. Database credentials remain in protected server configuration.

## Verification and next task

53 new synthetic cases plus existing regressions:235 passed on disposable PostgreSQL17.11;
default222 passed/13 PostgreSQL skipped. Covers schema hash and independent binary scalar
vector, grant destination/query validation, one-use/expiry/redaction, credential and HTTP errors,
catalog/expiry, binary subscriptions, unknown-field exclusion, timestamps, modes and numerics.
Ruff, strict mypy, lock check and dependency audit pass. Container evidence is in VERIFICATION.md.
Frontend behavior was unchanged; its previous browser evidence was not rerun this increment.

P2-003E is now implemented separately in FEED_LIFECYCLE.md with mock-socket tests for grant
consumption, binary subscription, message ordering, ping/pong timeout, reconnect/backoff,
duplicate/out-of-order updates and freshness. Durable observation/calendar/reporting follow;
no seven-day observation clock has started and no strategies/orders are implemented.

## 2026-11-06T15:52:35.233597+00:00 — P2-003P bounded real streaming acceptance COMPLETE

Explicitly authorized live-broker acceptance outside pytest. One Nifty50 index-only LTPC
subscription, duration20s,max_attempts1,max_frames10,poll2s. Local preflight passed without
blockers inside running private Compose app; token/schema/current catalog/calendar/grants
checked. Ran2026-11-06T15:50:39.131804+00:00 to2026-11-06T15:50:59.188955+00:00; runner elapsed20051ms,
reasonDURATION_LIMIT,stateSTOPPED,retry_pendingfalse. One authorization GET; one validated
single-use grant; secure WebSocket connection/binary subscription succeeded. No grant/URL/
token/raw-frame logging, no permission-policy bypass or decoder changes.

Actual events:PLAN1,MARKET_INFO1,SNAPSHOT1,IDLE9. Two binary Protobuf frames decoded in required
order. Nine explicit ping/pong round trips verified, connection State.CLOSED at exit. Broker
NSE_INDEX=CLOSING_END,NSE_FO=NORMAL_CLOSE; MCX/other segment status is not an index trading
permission. One normalized index observation,last_trade_at2026-11-06T10:30:00Z,correctly
STALE_TRADE. No UPDATE events/recent-trade/live-session completeness claimed. Idle health
progressed to DELAYED_FRAME; pong transport health never refreshed quote freshness.

Acceptance sink retained aggregates only in memory; no durable recorder was invoked.
DB counts unchanged:1catalog/6504instruments,1history batch/75candles,1chain snapshot/270legs,
0observation sessions/events/capture runs. Global observation_started_at null, qualifying days0.
Mode OBSERVATION; entries/live/signals/execution false. No orders, scheduler, auto restart,
strategy/paper promotion or certified day. Safe ignored report:reports/local_stream_acceptance.json.
Temporary one-time harness removed; no backend/source/dependency/schema/UI change.

Running image uses pre-formatting calendar evidence identity1cf89790c47a376a72e714e0e405e46173ae67e7a101b6312d855e23ac98dc58.
Host normalized-evidence identityee64ddfb593679cca9396b8646c61d458ce07147ea0c7f27c03b940eee3ed053.
Both loaders validate; all parsed policy fields excluding evidence hashes compared identical.
This provenance-only difference reflects approved whitespace cleanup; no market hours changed.
Before durable deployment verification rebuild via existing protected bootstrap so the current
reviewed manifests are deployed. Never relax integrity checks or alter calendar times to pass.

Checks:offline locked uv sync PASS; default326passed/22PGskipped; full disposable PG17.11
suite348passed/zero skips,temporary cluster stopped/removed. One upstream TestClient warning.
Ruff lint/format PASS83files;strict mypy PASS36backendfiles. Tests used synthetic transports;
actual broker acceptance ran separately. No settings,broker credential or admin password change.
Official V3 auth/feed sequence docs rechecked. Files:README.md,MASTER_PLAN.md,docs/PROJECT_STATUS.md,
WEBSOCKET_FEED.md,FEED_LIFECYCLE.md,CONNECTION_READINESS.md,VERIFICATION.md and all8agent_memory
records. Existing Git state preserved; no staging,commit,push,force-push or history rewrite.
Next:P2-003Q reproducible bounded durable capture workflow inside private Compose runtime,
rebuild reviewed image,verify persisted events/stop status/quotas without fabricating days.
Fresh market-hours observations and longer coverage still need explicit reviewed runs.
