# Read-only market-hours acceptance readiness

Run this check before a bounded Phase2 derivative market-hours acceptance attempt:

```sh
uv run python -m scripts.market_session_check \
  --instrument-key 'NSE_FO|YOUR_IMPORTED_OPTION_KEY'
```

Replace the placeholder with an explicitly reviewed, unexpired CE/PE key in the current
imported catalog. It is not a trade recommendation. Index keys, mixed index/derivative
requests and FUT contracts cannot satisfy this acceptance check. Existing feed resolution
still validates supported instrument types, expiry, metadata and requested quotas.

Docker and the existing private app must be available. The command verifies the local
Compose project and invokes only the existing preflight-only path. It never contacts
Upstox, refreshes metadata, starts recording, writes database rows, changes permissions
or enables trading. No image deployment is required for the host-side readiness check.
The existing capture wrapper and its diagnostic closed-market behavior are unchanged.

## What READY means

`READY_FOR_REVIEWED_SESSION_ATTEMPT` means the following local checks passed at that instant:

- Preflight reports PostgreSQL connectivity, current schema/catalog, required write grants,
  configured credential validity and no blockers; all execution/signal/live flags stay false.
- The preflight is at most30seconds old, with no more than2seconds of apparent future clock
  skew. Both timestamps must be timezone-aware. There is no command-line clock override.
- The server calendar fingerprint matches the host's checksum-validated official baseline.
  Synthetic calendars cannot make this real-runtime check ready.
- The current IST date has a reviewed regular or special session, the instant is within its
  half-open window, and the entire requested duration fits before the reviewed close.

Defaults are20seconds total/session,one child,20events,64KiB canonical payload. Existing
CapturePolicy bounds apply if these are overridden. READY is a diagnostic, not permission
for orders or proof that a later run completes before close; startup, clock changes,
connectivity and cleanup can alter actual timing. Repeat immediately before an explicit
capture. A fresh report never overrides the recorder's own existing preflight.

The report always leaves recording_started,broker_access_verified,phase2_complete,
signal_eligible,execution_eligible,entries_enabled and live_enabled false. Qualifying
observation days stay zero. Fresh broker updates, real reconnect acceptance, calendar
amendment completeness and the seven-calendar-day evidence window remain unverified.

## Blocked results

Exit0 means readiness checks passed;exit2 means blocked or unavailable. Fixed safe errors
withhold subprocess/configuration details. Existing known preflight blockers are preserved;
unrecognized upstream text is not copied into the report.

| Blocker | Next action |
|---|---|
| CURRENT_CATALOG_REQUIRED | Refresh and validate public metadata with the existing import workflow before the next eligible attempt. |
| NO_REVIEWED_SESSION / OUTSIDE_REVIEWED_SESSION | Wait for an eligible reviewed session; do not label a closed-market snapshot as market-hours evidence. |
| REQUEST_EXCEEDS_SESSION_WINDOW | Shorten the requested budget or wait for another reviewed session. |
| DERIVATIVE_KEYS_REQUIRED_FOR_ACCEPTANCE | Use supported catalog CE/PE keys; do not relabel index observations as derivative coverage. |
| PREFLIGHT_CLOCK_OR_AGE_INVALID | Check clock synchronization and run a fresh diagnostic. |
| REVIEWED_CALENDAR_MISMATCH | Review/deploy matching pinned evidence; do not bypass checksum validation. |
| LOCAL_PREFLIGHT_NOT_READY | Resolve the accompanying original database/schema/credential/catalog blockers. |
| UNSUPPORTED_FEED_INSTRUMENT | Use an explicit unexpired CE/PE catalog key. FUT keys usable by evidence reports are not supported by the observation feed. |

## Future session preview

The report adds `next_reviewed_session`, `session_preview` and fixed `next_actions` for
planning. The preview scans at most fourteen IST calendar dates, including today, and
returns the earliest reviewed opening at or after the check time. During an already open
session it describes a later opening; the current session remains in `session`. Reviewed
special sessions take precedence, and holidays, weekends and unknown hours are skipped.
Nothing beyond the pinned policy's validity is extrapolated. No matching window returns
null, which is not a claim that no later exchange session exists.

A preview requires checksum-validated official evidence with the same calendar identity
as preflight. Integrity failures, synthetic calendars and identity mismatches do not produce
a preview. The extra context never removes blockers or changes capture readiness. Its
`authorizes_capture` and `amendment_completeness_verified` fields are always false. The
preview does not test whether your requested duration fits a future window. Recheck actual
metadata, expiry, calendar amendments and the entire requested window immediately before
an explicit attempt. There is no timer, scheduler or automatic recording.

Actions come from fixed local messages for known blockers, never untrusted error text.
Unsupported futures and index acceptance requests explicitly point to CE/PE catalog keys;
no contract is automatically selected and no trade recommendation is made.

## Verified acceptance — 10 November 2026

Twenty-five synthetic tests cover ordinary/special session windows, exact boundaries,
holidays/weekends/unknown dates, stale clocks, calendar hashes, index rejection, privilege/
credential/catalog failures, safe error output and the preflight-only wrapper invariant.
Full disposable PostgreSQL suite:503passed,0failed,0skipped;one existing Starlette warning.

The real private runtime was checked using an arbitrary already imported unexpired catalog
option for diagnostics only. Result:BLOCKED,CURRENT_CATALOG_REQUIRED,LOCAL_PREFLIGHT_NOT_READY,
NO_REVIEWED_SESSION. The existing reviewed baseline marks10November as HOLIDAY. Before/after
capture,observation-session and event counts matched. No broker request or recording occurred.
Private proof is ignored `.local/verification/session_readiness_acceptance.json`.

Pinned evidence and market timings were preserved. The NSE's current [market timings page](https://www.nseindia.com/static/market-data/market-timings)
was rechecked;the derivatives regular-hours row agrees with the existing baseline. This
comparison does not verify all calendar amendments or turn this tool into a live exchange
status service. No completed observation day or Phase2 completion is claimed.

## Follow-up after public catalog refresh — 10 November

The existing importer refreshed the real private runtime to CURRENT_METADATA with6,744
selected instruments from85,462source records. Prior catalogs/market archives were
checksum-verified unchanged. A subsequent read-only readiness check reports only
NO_REVIEWED_SESSION (the reviewed holiday);the earlier catalog blocker is resolved at
that instant. Recheck freshness and session readiness before any later capture. No genuine
market-hours observation,day certification or trading was started. Private receipts:
.local/verification/catalog_refresh_acceptance.json and catalog_refresh_readiness.json.

## Planning context acceptance — 10 November

Forty readiness tests now pass, including fifteen new cases for future windows, holidays,
special/weekend precedence, exact opening/closing boundaries, policy expiry, the fourteen-date
bound, mismatched/synthetic/corrupt evidence, unchanged blockers and safe actions. Full
disposable PostgreSQL suite:728passed,0failed,0skipped; one existing Starlette warning.

A report-only FUT key (`NSE_FO|61471`) correctly remained blocked as unsupported. Rechecking
the previously reviewed option key (`NSE_FO|35050`) against the actual runtime resolved all
local prerequisites and remained BLOCKED only by NO_REVIEWED_SESSION. These are diagnostics,
not trade selections. The pinned baseline marks10November as HOLIDAY and previews
11November03:45UTC (09:15IST); it does not authorize an attempt or certify amendments.
Receipt:`.local/verification/market_session_preview.json`, ignored/private. No broker request,
DB mutation, capture, schedule, credential change or image deployment occurred. This host
readiness path used unchanged deployed preflight; the preview is computed locally.

## 2026-11-11T06:09:56.516396+00:00 — P2-003U bounded genuine market-hours acceptance

Completed the scoped market-hours transport/archive acceptance on 11 November. Initial
readiness correctly blocked yesterday's catalog. Refreshed the fixed official public NSE
master: 6,744 selected / 85,180 source records; publication 10 November 23:54:36 UTC.
Old catalog hashes and existing candle/chain archives matched before/after. Fresh readiness
passed; official NSE timing row was rechecked and targeted amendment search found no
contradictory notice, without claiming exhaustive amendment completeness.

Two explicit sequential research-only captures, each capped at 20 seconds, one session,
200 events and 262,144 canonical bytes. No automatic loop or recording schedule. FINNIFTY
key NSE_FO|35050: 7 events / 4,107 bytes, STALE_TRADE, zero accepted coverage. One validated
read-only Nifty chain request for explicit 17 November expiry identified a reference near
reported spot; response not archived and receipt time not treated as quote certification.
Nifty key NSE_FO|45406: 30 events / 29,597 bytes, 27 RECENT_TRADE updates, five coverage-
accepted samples and 1,946 sampled milliseconds. These are diagnostic contracts, not signals.
Both broker market-info frames reported NSE_FO NORMAL_OPEN. Parent SESSION_LIMIT and child
DURATION_LIMIT; all closed with no active parent/child left. One attempt per run, no real
reconnect. Event hashes, sequences, quotas and current catalog lineage verified, including
paginated authenticated API reads; anonymous denied and CSRF logout succeeded.

Broker frame generation was sometimes ahead of local receipt by roughly 0.1 seconds.
Cause is unverified; no clock fault attributed to either side. Strict nonnegative frame/
trade age checks preserved. Coverage reports 24 unusable frames; no offset adjustment or
stored timestamp rewrite. Seven-date report (5–11 November): 37 events, one duplicate,
zero out-of-order/disconnect events, one sampled date, assessment NOT_CERTIFIED and zero
qualifying days. Short-run evidence is not continuous-session/seven-day certification.

Fresh locked sync, Ruff lint/format (122 files), mypy (50 source files) and full disposable
PostgreSQL 17.11 suite passed: 744 passed, zero failed/skipped, one existing nonfatal
Starlette warning. Temporary test cluster removed; automated tests did not use a real
account or the operational database. Acceptance used the existing operational read-only
broker path explicitly, separately from regression tests. No source/schema/configuration/
credential/security/scheduler changes. Protected .env/admin password fingerprints unchanged.
OBSERVATION, entries/live/execution disabled; Google backup and OAuth configuration untouched.

Private ignored receipts: .local/verification/catalog_refresh_20261111.json,
market_hours_20261111.json, market_hours_nifty_20261111.json, market_hours_api_20261111.json
and market_hours_week_report_20261111.json. Files changed: all eight agent-memory documents,
LOCAL_CAPTURE.md, MARKET_SESSION_CHECK.md, PHASE2_ACCEPTANCE.md, PROJECT_STATUS.md and
VERIFICATION.md. All 13 changed Markdown files passed default Gitleaks without allowances and private
configured-credential comparison; full history passed unchanged exact historical allowances.
Whitespace check passed. Local documentation commit only; no push. Latest hosted CI unverified.
Phase 2 remains partial. Next: read-only host/container time-offset diagnostics, then plan
and verify a bounded genuine reconnect in a fresh reviewed session with catalog/readiness
rechecked. Keep freshness gates unchanged. Seven-day evidence, calendar completeness and
physical unit clarification remain outstanding. No unattended recording authorized here.
