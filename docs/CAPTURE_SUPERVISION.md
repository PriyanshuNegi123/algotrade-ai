# Bounded multi-session research capture

P2-003H adds an explicit host supervisor, a durable parent quota ledger and private summary reads.
It never starts on application boot, resumes a crashed subscription or enables trading. No real
credential/account capture was exercised. All verification records are labeled SYNTHETIC.

## Limits and lifecycle

| Control | Default | Hard maximum |
|---|---|---|
| Total monotonic budget, including setup/wait | 600 seconds | 3,600 seconds |
| Child session duration | 300 seconds | 300 seconds |
| Number of sessions | 3 | 12 |
| Aggregate canonical payload bytes | 8 MiB | 64 MiB |
| Aggregate recorded events | 20,000 | 100,000 |

Each child retains existing per-session32MiB/11,000event storage bounds and the bounded feed
runner's frame/retry limits. Parent quotas count only sessions linked to that parent. They are
not filesystem quotas or account-wide limits; database/index/summary overhead is additional.
Defaults are caps, not promises that every session will fit the total runtime. Coverage report
candidate/event/byte bounds are separate; large runs may exceed a report's permitted window.

Every new session has a new durable identity, fresh catalog resolution and newly acquired one-use
connection grants. No cached socket URL/subscription is reused. Rollover waits30seconds after a
child closes. Production cannot disable this delay through CLI arguments. Mock/local TLS tests
inject a no-wait function solely for verification. Existing child retry/backoff limits still apply.

Only a FRAME_LIMIT/DURATION_LIMIT child that persisted a snapshot and has no unresolved transport
retry can roll over. Auth/permission, malformed protocol, recording/sink or storage failures stop
the parent. Retry-pending is carried explicitly by the child runner so a duration ending during
backoff cannot start a new child and bypass its failure or Retry-After. A successfully recovered
connection clears that flag only after its snapshot is accepted. A snapshot may be partial/empty;
it does not prove complete coverage, executable freshness or broker entitlements.

Total budget includes setup, authorization, child processing and rollover waits. No child starts
when less than one second remains. Child duration is clipped to whole remaining seconds. When the
budget expires, the active child/wait is cancelled and drained, its session finalized, then the
parent closed. DB checkout/I/O and cleanup can extend nominal timeout while durable work settles;
the supervisor does not forcibly terminate database threads or claim a guaranteed hard wall-time.

The host CLI handles SIGINT/SIGTERM by setting a cooperative stop event. A preset stop causes no
capture record or broker request. Stop during capture cancels/drains the child and closes it before
closing the parent. Cancellation arriving during DB creation waits for the returned identity so
newly committed children can be finalized; external task cancellation is re-raised after cleanup.
Repeated forced termination/process kill can still interrupt cleanup and requires lease recovery.
No callback or cancellation path logs a credential-bearing URL or raw upstream exception.

## Durable ledger, concurrency and crash recovery

Revision0006_capture_runs creates capture_runs and adds nullable supervisor_id FK/index to
observation_sessions. Existing standalone sessions stay unlinked. Parent records store source,
requested keys, validated policy, UTC lifecycle/lease fields, session/event/byte counters and
normalized aggregate diagnostics. Child sessions retain their own catalog attempts and event hashes.

A writer first locks the parent, then its child session. Each append checks aggregate quotas and
updates parent statistics, child counters and canonical event in one transaction. Rejected writes
change none of these. Concurrent sessions cannot race beyond a parent budget. Identical receipt
replay remains idempotent. Child creation and parent session count are also one transaction with
source/key/policy checks. There is no public mutation or limit-changing API.

Parent aggregate observations/duplicates/out-of-order/disconnect/idle/snapshot counters reflect
committed records. Last recorded health includes its event time and remains health_current=false;
reading a summary never refreshes old market observations. Per-child sampled spans remain separate;
no interval bridges sessions, processes or reconnects. These counts are not unique exchange ticks,
completed market days or evidence of exact feed completeness.

The parent lease is creation+configured total budget+120seconds grace. A bounded pre-run recovery
pass marks expired RUNNING parents and still-running linked children INTERRUPTED/LEASE_EXPIRED,
records recovery time and leaves unknown actual end times null. Reads derive ABANDONED for an
expired still-RUNNING parent. Old groups are not resumed. If DB finalization/cleanup fails, the
CLI reports a safe error and leaves durable state for recovery, rather than printing false success.
Independent unlinked sessions do not consume parent quotas. The instance lock does not coordinate
other supervisor processes or users sharing a broker account; operator coordination remains required.

Downgrading0006 removes parent grouping/counters and detaches supervisor_id while preserving child
observation sessions/events, catalog, history, chain and admin sessions. Parent linkage is lost;
back up before downgrade. Updated app readiness fails until the current schema is restored.

## Explicit operator use

Apply the new schema, configure current metadata/protected server credentials and a host-reachable
PostgreSQL database, then invoke deliberately:

```sh
uv run alembic upgrade head
uv run python -m scripts.supervise_capture --instrument-key 'NSE_INDEX|Nifty 50' --total-seconds 600 --session-seconds 300 --max-sessions 3 --max-payload-bytes 8388608 --max-events 20000
```

Repeat --instrument-key for up to100 unique supported catalog keys. Arguments never accept tokens,
socket URLs, HTTP methods or trading modes. Real configuration can contact Upstox; development
verification did not. The command prints its final durable parent summary. Private reads can
inspect running groups without waiting for the CLI to finish:

| Administrator-only route | Behavior |
|---|---|
| GET /api/observations/captures | ID-ordered parent summaries, default20/max50, optional32hex after |
| GET /api/observations/captures/{id} | Consistent read-only parent plus up to12 linked child summaries |

Invalid IDs/cursors/limits422; missing parent404; unauthenticated401. No HTTP start/stop or mutation
route and no automatic service/daemon are introduced. Production uses PostgreSQL; local verification
uses isolated SQLite only under APP_ENV=test. Docker's DB remains private; host CLI requires a
reachable configured DB. Existing stream_feed still supports a single unlinked bounded session.
All responses retain live/signal/execution false and qualifying_observation_days=0.

## Verification and next task

319 native PostgreSQL tests pass with zero skipped; default299 pass/20 PG skip.18 new cases cover
multi-session grants/IDs/accounting, byte/event quotas before network, terminal failures and pending
retry, cooperative stop/cancellation during creation, recovery, API privacy, hard bounds, runtime
expiry, concurrent aggregate charging, atomic rollback, restart and downgrade preservation.
Ruff77/mypy34/lock pass. No dependency versions changed. New verify_supervision command combines
existing real local TLS framing/ping/pong/redirect checks with two durable supervised synthetic
sessions; all temporary DB/certificate/server resources are removed. CI step updated, not run remotely.
See VERIFICATION.md for Docker evidence. Frontend unchanged; no new browser check.

Next P2-003I:operator capture preflight with safe configuration/schema/metadata/credential-expiry/
calendar/quotas checks, private readiness output and host CLI guidance. Actual broker acceptance,
genuine prolonged recording, calendar amendment completeness and completed-day evaluation remain
unverified gates. No manufactured seven-day result, strategy permission or automatic phase promotion.

## P2-003I — safe capture preflight (2026-11-06)

The host supervisor CLI now runs safe local preflight before recovery or creating records.
--preflight-only prints diagnostics without launching. A blocker exits2; a passing explicit
capture command still revalidates runtime conditions. Direct library fixtures/single-session
CLI retain their own controls. Preflight neither reserves capacity nor verifies broker account
acceptance. See CAPTURE_PREFLIGHT.md.
