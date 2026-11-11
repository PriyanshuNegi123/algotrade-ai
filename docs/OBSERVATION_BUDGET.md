# Read-only observation pilot budget

The pilot's daily limits remain operator policy. `scripts.observation_budget` makes current
usage visible from stored ledgers; it does not change the recorder, enforce a global daily
quota, reserve a slot, start capture or contact Upstox/Drive. PostgreSQL remains operational
storage. There is no new HTTP route, migration, scheduler or trading permission.

```sh
uv run python -m scripts.observation_budget --local \
  --from-date 2026-11-11 --to-date 2026-11-17
```

Use the private Docker runtime's reviewed image. The host-only `--local` wrapper verifies
the existing Unix-socket engine/project directory and sends only the trusted CLI source
through stdin. Dates are the only inputs; credentials, URLs, instrument filters, alternate
SQL and policy overrides are not accepted. The host CLI never publishes the private DB.
Without `--local`, it reads the explicitly configured database using the existing Settings.

Exit 0 means budget diagnostics are available for further checks. Exit 2 means a valid
blocked budget report; unavailable/invalid execution exits nonzero with sensitive details
withheld. Neither successful exit nor `BUDGET_AVAILABLE_FOR_RECHECK` authorizes capture.
Always run current catalog/expiry/calendar/time/storage and market-session readiness checks.
The checker considers dates, not whether the instant is inside an open session.

## What is counted

- The fixed profile matches [OBSERVATION_PLAN.md](OBSERVATION_PLAN.md): 120 seconds, one
  child, 300 events and 262,144 canonical bytes. Three standard runs per eligible IST date.
- All genuine `UPSTOX_V3` parents created in the requested range count, regardless of key,
  status, success or child count. Failed/interrupted attempts cannot recover a run slot.
- Standalone genuine sessions created in range also consume a slot and their actual usage.
  Synthetic history is excluded from genuine usage. Any RUNNING parent or session, including
  synthetic or outside the requested dates, blocks diagnostics pending local review.
- Parent/child session, event and byte totals are checked for consistency. Sessions that
  overlap the range from an external parent/date are included in report-headroom totals and
  require review; they cannot silently disappear at a midnight boundary.
- Headroom conservatively includes all genuine keys in overlapping sessions. A particular
  filtered coverage report may use fewer rows; no instrument filter can hide usage here.
  Canonical payloads are not loaded and their hashes are not revalidated by this diagnostic.
  Use the normal archive reader for integrity/freshness/coverage assessment.

All summaries come from one repeatable-read, read-only PostgreSQL transaction with a bounded
statement timeout. The two ledger reads are each capped at 100 rows plus one overflow probe;
overflow is refused rather than truncated. Active-row counts are aggregate queries. SQLite
is supported for synthetic tests, not operational acceptance. No locks or writes reserve
capacity. Another process can consume capacity immediately afterward; this is not account-
wide connection coordination, a disk monitor or a replacement for capture preflight.

## Output and limitations

`daily_usage` and `window_usage` show runs, child sessions, events and canonical bytes.
`remaining_standard_runs_today` accounts for all four daily dimensions, window quotas and
report headroom. The window uses three runs per pinned baseline date with a session window;
unknown or synthetic calendars require review. `remaining_window_run_slots_before_session_checks`
is storage/run capacity, not a catch-up allowance or permission to record on missed dates.

The existing coverage limits remain 100 sessions, 20,000 events and 8 MiB across at most seven
dates. A full additional standard run must fit all applicable limits. `blockers` identifies
daily/window exhaustion, report headroom, active/unresolved rows, unsupported calendar dates
or ledger review. A ROW_LIMIT/unavailable result requires inspection; do not raise caps,
delete archives, relabel sources or ignore unknown evidence to obtain an available state.

Calendar integrity is checked through the existing loader. Amendment completeness remains
unverified. Date selection does not establish a verified observation start, current market
availability or complete calendar history. Requested ranges are limited to seven dates.
`authorizes_capture`, `reservation_created`, `daily_limit_enforced_by_recorder`,
`recording_started`, `phase2_complete`, `entries_enabled` and `live_enabled` remain false;
qualifying observation days stay zero. Existing timestamp/freshness rules are unchanged.

Disk/index/WAL/catalog growth, compressed dump size and current cloud availability are
outside this ledger report. Keep the separate manual storage pause rules and three-day
cloud backup checks. The operational database stays local; no archive deletion is added.
