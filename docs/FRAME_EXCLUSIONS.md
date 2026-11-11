# Coverage frame-exclusion diagnostics

Coverage JSON now adds `unusable_frame_reasons`; the initial observation JSON forwards it
and Markdown renders a **Frame exclusion diagnostics** table. This is read-time metadata.
No archive/schema/hash, timestamp, decoder tolerance, report quota or capture behavior changes.
Signal/execution/live flags remain false; completed observation days remain zero.

## Primary reason counts

| Reason, in evaluation order | Existing rejection condition |
|---|---|
| OUTSIDE_REQUESTED_DATES | Receipt's IST date is outside the requested range |
| NO_REVIEWED_SESSION_WINDOW | The pinned calendar has no opening/closing window for that date |
| OUTSIDE_REVIEWED_SESSION_WINDOW | Receipt is outside the half-open reviewed session window |
| RECEIPT_AT_OR_AFTER_REPORT_TIME | Receipt is at or after the report's as-of instant |
| GENERATION_AFTER_RECEIPT | Broker frame generation timestamp is later than local receipt |
| GENERATION_TOO_OLD | Receipt minus generation exceeds ten seconds |

Exactly one primary reason is counted for each frame in the legacy
`outside_or_unusable_frames` aggregate. All six keys exist, including zero values. Their
sum equals that aggregate. If several conditions fail, the first row above wins; these
are not independent counts of every possible defect.

The acceptance predicate is unchanged: receipt must be within requested dates, a reviewed
session and strictly before report time; generation age must be between zero and ten seconds
inclusive. Even a negative age of one microsecond remains excluded. Rejected frames clear
sample continuity, so later data cannot bridge the rejected interval.

## Scope and interpretation

The aggregate and reason counts consider only archived SNAPSHOT/UPDATE events that have a
frame and observations. Empty observations, non-data lifecycle events and per-key trade
filters keep their existing behavior. These counters do not enumerate every missing tick,
unknown trade time, stale trade, zero price, duplicate, protocol error or gap. Per-key
sampled intervals and health remain separate evidence. Checksum/schema/resource failures
still stop the report rather than returning partial diagnostics.

GENERATION_AFTER_RECEIPT identifies a timestamp relation, not which clock/source is wrong.
Do not add offsets, clamp negative ages, rewrite archives or relax freshness rules to
improve coverage. Continue independent [clock diagnostics](CLOCK_DIAGNOSTICS.md) and preserve
uncertainty until the cause is supported by evidence. A small positive measured span is
not full-session coverage, a completed day or permission to trade.

The existing authenticated `GET /api/observations/coverage` exposes the additive field;
authentication and all query bounds remain unchanged. No new route, write or broker call
was added. The existing `scripts.initial_observation --local` command also includes the
counts without recording or fetching new market data. The deployed image must contain the
reviewed backend version. See [OBSERVATION_REVIEW.md](OBSERVATION_REVIEW.md).

## Actual deployed verification — 11 November 2026

The three stored genuine derivative sessions contain 119 events. The original outside/
unusable count remains 82; all now classify as GENERATION_AFTER_RECEIPT, with the other
five counters zero. Existing accepted samples and measured spans match the earlier report.
CLI and authenticated API agree; archive/configuration hashes match before/after deployment,
anonymous access is denied and CSRF logout passed. No extra recording or broker request.
Full disposable PostgreSQL regression: 809 passed, 0 failed, 0 skipped; one existing Starlette
warning. 25 new cases include exact zero/ten-second boundaries and negative-microsecond ages.
