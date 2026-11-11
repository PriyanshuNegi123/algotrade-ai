# Bounded multi-day observation pilot

Prepared 11 November 2026. Candidate evidence window: **11–17 November inclusive (IST)**.
This is a sparse data-quality pilot. It cannot establish continuous session coverage or
complete the seven-calendar-day requirement by itself. All reports remain NOT_CERTIFIED;
qualifying days remain zero until separately reviewed criteria and evidence support them.
PostgreSQL remains the operational database. Live trading stays disabled.

## Dates and optional checkpoints

| IST date | Pinned baseline | Plan |
|---|---|---|
| 11 November | Regular baseline | Three acceptance captures already consumed today's three-run allowance; no additional capture under this plan |
| 12 November | Regular baseline | Up to three explicit runs after fresh checks |
| 13 November | Regular baseline | Up to three explicit runs after fresh checks |
| 14 November | Weekend | No planned capture; preserve missing coverage |
| 15 November | Weekend | No planned capture; preserve missing coverage |
| 16 November | Regular baseline | Up to three explicit runs after fresh checks |
| 17 November | Regular baseline | Up to three explicit runs; recheck expiry and supported contract before every attempt |

Optional checkpoints on eligible regular dates are **09:45, 12:15 and 14:45 IST**. These
are operator reminders, not timers or scheduled commands. Skip missed checkpoints; do not
backfill timestamps or run catch-up loops. Unexpected closures, changed sessions and failed
checks override this table. Recheck the whole requested window before each actual run.

The [NSE timing page](https://www.nseindia.com/static/market-data/market-timings) currently
lists F&O normal hours 09:15–15:40 IST. Its [annual holiday circular](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf)
and the pinned amendment evidence were reviewed for planning. This table is a baseline
preview, not certification of future amendments or current exchange availability.

## Capture and report budgets

| Scope | Maximum created parents / children | Canonical payload | Events | Requested data window |
|---|---:|---:|---:|---:|
| One run | 1 / 1 | 262,144 bytes (256 KiB) | 300 | 120 seconds |
| One IST date | 3 / 3 | 786,432 bytes (768 KiB) | 900 | 6 minutes |
| All seven dates, conservative ceiling | 21 / 21 | 5,505,024 bytes (5.25 MiB) | 6,300 | 42 minutes |
| Five baseline eligible dates | 15 / 15 | 3,932,160 bytes (3.75 MiB) | 4,500 | 30 minutes |

Startup/backoff and quotas can shorten actual recording; a 120-second parent can have a
119-second child. Normal retries retain existing backoff and never reset the parent budget.
The default lifecycle permits at most three attempts within the finite child window. Do
not inject further disconnects for this pilot; controlled reconnect acceptance is separate.

Per-run quotas are enforced by the existing recorder. The daily/window ceilings are
**manual operator limits**, not new backend enforcement. Count every created genuine parent,
including failed, interrupted and ad hoc acceptance runs; do not retry beyond the daily cap.
A preflight-only check creates no capture. Check persisted records before repeating after
an interrupted client; the bounded remote process may still be running.

At planning time, 11 November has three closed parents, 119 events and 111,881 payload bytes.
Those runs already count toward the ceilings. Under the five-date baseline, at most twelve
additional runs remain: 3,145,728 additional payload bytes; 3,257,609 bytes including existing
payload. Other new captures must be subtracted from that remaining allowance.

The existing coverage reader permits at most 100 matching sessions, 20,000 events and 8 MiB
of stored payload per report, across at most seven dates and twenty distinct keys. The
conservative 21-run envelope fits those bounds for this pilot. Recompute with all matching
existing/ad hoc sessions and every rotated key; this is not a reservation or guarantee.
Do not raise report bounds or delete archives to make a report pass.

## Before each run

1. Keep Docker and the private app available. Verify OBSERVATION mode, disabled entries/live
   and no active capture/child. Coordinate other account consumers; this plan adds no
   account-wide connection coordinator.
2. Check time independently as described in [CLOCK_DIAGNOSTICS.md](CLOCK_DIAGNOSTICS.md).
   Do not adjust archived timestamps or relax nonnegative coverage-age checks. Stop and
   investigate malformed/future timestamps or new clock anomalies.
3. Import current official NSE metadata through the signed-in dashboard's **Import official
   NSE metadata** control when required. Validate currentness and an explicit unexpired CE/PE
   contract. No more than one new catalog snapshot per date is budgeted here. Import failures
   must be investigated, not bypassed with stale metadata or repeated downloads.
4. Review calendar applicability/amendments and both daily and report budgets. Record date,
   key, catalog ID, intended quotas, readiness timestamp and remaining budget in a private
   ledger under ignored `.local/verification/`. Never include tokens, passwords or grant URLs.
5. Run fresh readiness with exactly the intended recording quotas. READY is a local check;
   it does not enforce the manual daily cap or certify broker freshness/calendar completeness.

Example diagnostic key only: `NSE_FO|45406` was verified on 11 November as Nifty 25400 CE,
17 November expiry. It is not a recommendation or a permanent valid selection. Review it
again before use; record any explicitly reviewed replacement and report both archived keys.
Never automatically roll an expired/missing contract or infer a tradable expiry cutoff.

```sh
observation_key='NSE_FO|45406'
uv run python -m scripts.capture_local --status
uv run python -m scripts.market_session_check --instrument-key "$observation_key" \
  --total-seconds 120 --session-seconds 120 --max-sessions 1 \
  --max-events 300 --max-payload-bytes 262144
```

Only after all checks pass, the operator can explicitly start one bounded run:

```sh
uv run python -m scripts.capture_local --instrument-key "$observation_key" \
  --total-seconds 120 --session-seconds 120 --max-sessions 1 \
  --max-events 300 --max-payload-bytes 262144
```

No capture scheduler, shell loop, cron job, LaunchAgent or automatic startup is installed by
this plan. The three-run daily limit is already consumed on 11 November.

## After each run and at window review

Record actual parent/child IDs, UTC start/end times, close reasons, event/byte totals,
lineage, freshness, duplicates, ordering/disconnects and accepted sampled intervals. Use the
signed-in private APIs and paginated reads to verify hashes and closure. A successful CLI
exit alone does not prove a successful child. Keep all gaps and unusable frames explicit.
For cooperative stop, use the exact returned parent ID with `scripts.capture_local --stop`
and verify final closure; never broadly kill processes or remove volumes.

Read-only evidence export (include every explicitly used key, including earlier controls):

```sh
uv run python -m scripts.initial_observation --local \
  --from-date 2026-11-11 --to-date 2026-11-17 --source UPSTOX_V3 \
  --instrument-key 'NSE_FO|35050' --instrument-key 'NSE_FO|45406'
```

The report now exposes [window progress and review reasons](OBSERVATION_REVIEW.md).
Its date filter is not a verified recording start, and elapsed dates never certify days.
Before the window ends this is an interim report; future dates and unsampled periods are
not evidence. Store only small protected reports locally; the operational archive remains
in PostgreSQL and is backed up through the existing encrypted Drive workflow. At review,
list available sessions and missing dates, measured spans and remaining gaps. A short
sample on a date is not an observed full day. Synthetic tests and deliberate disconnects
must remain distinguishable from ordinary market behavior. No P&L, fills or signals belong
in this phase. A report cannot advance phases or enable trading.

## Disk and cloud policy

Canonical byte limits exclude PostgreSQL rows/indexes/TOAST/WAL, catalogs, Docker images and
filesystem overhead. New metadata snapshots may grow storage more than the feed itself.
There is no automatic archive retention/deletion or operational database offload to Drive.

Measured 11 November (one point in time): database 28,191,891 bytes (~26.9 MiB); snapshot
and normalized metadata tables 8,855,552 and 10,502,144 bytes; observation-events table
262,144 bytes including indexes/TOAST. A bounded read-only pg_dump produced 9,732,125 bytes
in RAM; no local archive, upload or new restore was made. Dump size is not database size.
The existing backup export limit is 32 MiB; restore data tmpfs is 256 MiB with a 512 MiB
container memory limit. These limits are unchanged; current fit does not prove future fit.

Operator pause rules for this pilot: host free space below 2 GiB; database at/above 64 MiB
or growth of 32 MiB from the measured baseline; measured custom dump at/above 24 MiB;
a backup failure, unsafe active state, exhausted report/daily budget or unresolved readiness
blocker. These are conservative review thresholds, not implemented disk guards or storage
predictions. Re-measure actual sizes before extending collection; do not increase resource
limits or delete existing data as a workaround. Recheck Docker's available allocation too;
host free space alone does not establish container-volume capacity.

Use the existing every-three-IST-date backup policy and encrypted Drive recovery workflow:

```sh
uv run python -m scripts.backup_job status
uv run python -m scripts.backup_schedule status
```

Local health at planning time: last backup created 9 November, next due **12 November**;
installed check time is **21:30 IST**, subject to Mac/user/Docker/network availability. No
schedule change is made. Status does not contact Drive or prove current cloud access. New
backups use bounded RAM and isolated tmpfs restores, avoiding a growing local archive cache.
Local `.atbackup` cache measured zero bytes. PostgreSQL still needs local disk; Drive's
user-reported capacity is not verified here and cannot serve as its working data directory.

Do not remove database rows, volumes, source catalogs, keys or receipts. Never delete Drive
files for this plan. Preserve the separately held recovery-kit passphrase; never put it in
chat, the ledger or commands. Verify the next due backup/restore receipt before relying on
cloud protection for newly collected evidence. See [BACKUP_SCHEDULE.md](BACKUP_SCHEDULE.md).
