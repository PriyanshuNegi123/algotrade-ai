# Bounded V3 WebSocket lifecycle

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
