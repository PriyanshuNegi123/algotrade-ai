# Bounded V3 WebSocket lifecycle

Latest actual acceptance 11 November 2026: bounded genuine market-hours updates and a
controlled reconnect with fresh authorization, unchanged backoff and durable gap/closure
verification. No natural outage or certified day is claimed. See the dated acceptance below
and [clock diagnostics](CLOCK_DIAGNOSTICS.md). Older unverified statements are historical.

P2-003F update:the host CLI now persists research sessions/events by default; see
[OBSERVATION_STORAGE.md](OBSERVATION_STORAGE.md). The lifecycle scope below originated in P2-003E.

P2-003E adds a server-side connector and explicit host CLI for bounded LTPC research sessions.
No background task starts with the application. No HTTP/WebSocket control route, dashboard
change, strategy or order permission is introduced. P2-003F adds storage/migration separately.
Actual broker acceptance remains unverified:verification used mock sockets and local TLS only.

## Sources and dependencies

Reviewed2026-11-06:official [Upstox V3 feed](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/),
[authorization](https://upstox.com/developer/api-documentation/get-market-data-feed-authorize-v3/),
and [websockets asyncio client](https://websockets.readthedocs.io/en/16.0/reference/asyncio/client.html)
and [keepalive](https://websockets.readthedocs.io/en/16.0/topics/keepalive.html) contracts.
The library supports automatic ping/pong, configurable resource limits and proxy control.
The pinned runtime is websockets16.1.1; the existing pinned V3 schema/Protobuf decoder is reused.
See WEBSOCKET_FEED.md for schema provenance and precision/presence limitations.

## Connection and credential controls

`open_feed` consumes the server-only one-use grant immediately before dialing WSS. It does
not forward the bearer credential to the socket. TLS certificate/hostname verification remains
enabled. All redirect handshakes are blocked, including same-host redirects. Proxy discovery
and message compression are disabled. A dedicated disabled, non-propagating logger suppresses
handshake URI, frame contents and close reasons. Exceptions become safe fixed transport codes;
raw upstream exception text, grant query, close reason and headers are never emitted.

Connection settings:10second opening timeout,20second periodic ping,5second pong timeout,
3second close timeout,512KiB incoming-message maximum, queue4 and32KiB write limit. The library
responds to upstream ping frames automatically. Queue bounds apply backpressure, not silent drops.
The existing authorization destination/path/query checks, credential expiry and local60second
grant lifetime still apply. These conservative local policies are not broker-certified limits.

## Bounded lifecycle

- Each explicit run permits1–300seconds (default60), at most3 total attempts and10,000 decoded
  frames. The total timeout includes authorization, processing and backoff. One runner instance
  rejects concurrent runs; no cross-process/account scheduler is claimed. Operators must
  coordinate other consumers sharing the broker's account-wide connection/request budget.
- Each attempt checks credentials, resolves a fresh current catalog plan, obtains a fresh grant
  and sends binary LTPC subscription JSON with a new GUID. Grants are never reused. Reconnect
  discards prior per-connection state and creates new watermarks and catalog binding.
- The first decoded message must be market_info; data before it fails closed. Market information
  and the subsequent snapshot each have a10second deadline. The first data frame is treated as
  the snapshot even when the broker labels it live_feed; it may be empty or cover only a subset.
  Missing keys remain AWAITING_FIRST_TICK. Repeated status messages do not extend the deadline.
- Credential availability is checked before/after receives. Frames received after expiry are
  rejected; an idle connection notices expiry on its next bounded poll/pong cycle (normally
  <=10seconds). This does not imply upstream revocation detection or credential auto-renewal.
- Live receives poll every5seconds. An idle poll emits a health event and sends a bounded ping.
  A pong confirms only transport health; it neither creates ticks nor refreshes market times.
  No market frames can be legitimate during closed/quiet sessions; healthy idle sockets remain
  open within the overall time budget. Market calendars are not inferred from silence.
- Disconnects/transient authorization or handshake errors retry with fresh state. Local spacing
  is30 then60seconds plus0–5seconds jitter; larger bounded upstream Retry-After is respected.
  No automatic infinite reconnect. Authentication/permission, invalid grant, TLS, redirect,
  schema/protocol/catalog and consumer failures stop. Retry budget never resets after a connection.
- Consumer delivery has a2second asynchronous deadline. Slow/failed consumers stop the session.
  Cancellation propagates and context cleanup closes the socket. The final summary reports
  a safe reason, attempt/frame counts, disabled entries/live and null observation_started_at.
  Custom sinks must yield to the event loop; synchronous blocking work is not made cancellable
  by an asyncio timeout. The CLI writes normalized JSON to its operator-controlled stdout.

## Update filtering and health

Per-connection generation timestamps cannot regress. Older frames are dropped with an
OUT_OF_ORDER event. Per-key last-trade-time regressions are also excluded. Identical last
normalized ticks are counted as duplicates; equal-time changed values remain research updates,
not certified exchange corrections. Missing trade times do not erase prior time watermarks.
No exchange sequence exists in the implemented schema; exact tick loss cannot be calculated.
Reconnects create explicit discontinuities rather than fabricated gap counts or filled prices.

Only accepted observations appear in event.frame.ticks and event.observations; duplicate/out-of-
order counts are separate. Known normalized data only is emitted. No raw binary archive or
unknown broker fields appear in output. Generation/receipt/last-trade times stay distinct.

Health ages for every subscribed key are recomputed on data and idle events. Default local
research diagnostics:frame age>10seconds DELAYED_FRAME, trade age>15seconds STALE_TRADE,
missing trade time UNKNOWN_TRADE_TIME, missing/zero price ZERO_OR_MISSING_PRICE; otherwise
RECENT_TRADE. Never-seen keys remain AWAITING_FIRST_TICK. A delayed-frame diagnostic takes
precedence. The decoder's5second future-clock tolerance still applies. These thresholds are
not exchange guarantees, market-session validation or executable quote freshness.

All event/frame/tick signal and execution eligibility remains false. Decoder-level freshness
stays NOT_EVALUATED; lifecycle diagnostics are carried separately. Wire doubles and implicit
proto3 scalar presence retain their explicit flags. LTPC lacks executable bid/ask/depth context.
RECENT_TRADE does not authorize a fill, strategy or live trading. On disconnect/backoff the
consumer must invalidate prior connection health; old observations do not carry forward.

## Explicit host use

With current metadata, host-reachable configured PostgreSQL and a locally protected server
Analytics credential (never pasted into chat):

```sh
uv run python -m scripts.stream_feed --help
uv run python -m scripts.stream_feed --instrument-key 'NSE_INDEX|Nifty 50' --duration 60
```

Repeat --instrument-key for up to100 unique current catalog indices/unexpired CE/PE keys.
The private Docker DB remains unpublished; this CLI requires a deliberately host-reachable DB.
No token/URL/method parameter is accepted. The command can contact the broker when explicitly
run with real settings; development verification did not do so. Stdout is normalized research output. P2-003F additionally persists it; schema now requires
0005_observations. Calendar-certified observation days remain unavailable.

## Executed checks and next work

25 new lifecycle tests plus existing suite:260 pass on disposable PostgreSQL17.11; default
247 pass/13 PostgreSQL skip. Mock checks cover ordering, binary subscription, one-use grants,
re-resolution/reconnect/backoff/rate limits, credential expiry, heartbeat/initial timeout,
cancellation, consumer failure, duplicate/time watermarks and aged health. Normal pytest blocks
both real HTTP and WebSocket client connections. A separate verification command:

```sh
uv run python -m scripts.verify_feed_transport
```

uses an ephemeral self-signed certificate trusted only by its local test client, real loopback
TLS/WebSockets, binary framing, server ping/client pong and a real302 rejection. It cleans up
servers/certificates and never dials Upstox. The CI workflow includes it; CI itself was not run
here. No frontend changes or new browser run. See VERIFICATION.md for Docker and audit evidence.

P2-003F now implements durable research observation sessions/events with lineage, disconnect/gap markers,
rollback/restart behavior and private bounded reads. Calendar/session completeness and genuine
seven-day reporting follow separately. No observation clock or real seven-day result is claimed.

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

## 2026-11-11T06:19:55.417924+00:00 — P2-003W controlled genuine reconnect and read-only time diagnostics

Read-only macOS SNTP probes: Apple offset +85.321 ms with +/-93.765 ms uncertainty;
Cloudflare +66.557 ms with +/-87.767 ms uncertainty (one address timed out before a
successful response). Neither estimate establishes a root cause. Five bracketed Docker
clock reads overlap host time; no demonstrated independent container drift. No clock,
NTP settings, timestamp values or acceptance thresholds changed. See CLOCK_DIAGNOSTICS.md.

One explicit genuine NSE_FO|45406 research capture: 80-second total/session caps, one child,
two maximum attempts, 250 events / 262,144 bytes. The private acceptance connector used
existing open_feed; its event sink scheduled one orderly close of only its owned first
socket after a stored recent-trade update. No fake frames/exceptions, network-wide fault,
container restart or reduced backoff. The ordinary runner emitted FEED_DISCONNECTED/BACKOFF,
waited 31.184 seconds, obtained a new authorization and restored market-info/snapshot/update.
This is controlled disconnect acceptance, not evidence of a natural broker outage.

Parent fc1f3773acc04976be6b6346f39ab45f and child 940242fc67cb4efd9d05d4468dc90bce
closed with SESSION_LIMIT / DURATION_LIMIT. Stored 82 events / 78,177 bytes; attempts had
1 and 68 RECENT_TRADE updates. API pagination verified hashes, sequences, quotas and both
current-catalog bindings. Anonymous access denied; CSRF logout passed. A 31.488-second
snapshot gap was not bridged by coverage; 13 accepted samples / 307 sampled ms, 58 unusable
frames. All active rows and established app HTTPS sockets returned to zero. Prior catalog,
candle/chain archives and protected configuration fingerprints remained unchanged.

Fresh sync, Ruff lint/format (122 files), mypy (50 source files), full disposable PostgreSQL
17.11 regression: 744 passed, zero failed/skipped, one existing Starlette warning. Cluster
removed; automated tests used no real account/operational DB. Operational acceptance was
separate and explicitly read-only. Seven-date report now has three sessions / 119 events,
six duplicates, zero out-of-order and one controlled disconnect; zero qualifying days,
NOT_CERTIFIED. Phase 2 stays partial; latest hosted CI, absolute clock cause, natural outage,
seven-day evidence, calendar completeness and physical unit conventions remain unverified.

No application source, schema, credentials, .env, OAuth/Google settings, scheduler or security
controls changed. OBSERVATION; entries/live/execution disabled. Local documentation commit
only, no push. All 14 changed Markdown files passed default Gitleaks without allowances
and configured-credential comparison; full history passed unchanged exact historical
allowances, and whitespace check passed. Private ignored receipts: clock_diagnostics_20261111.json, reconnect_20261111.json,
reconnect_api_20261111.json and reconnect_final_20261111.json under .local/verification/.
Next: prepare a bounded multi-day observation collection plan with storage budgets and
operator-invoked commands; continue independent time checks before longer collection.
Do not enable automatic recording, infer elapsed coverage or certify days from short runs.
