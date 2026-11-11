# Evidence-only observation-window review

The initial observation report now includes `window_progress` in JSON and an
**Observation-window progress** section in Markdown. It reuses the existing bounded,
hash-validated, read-only coverage transaction. No additional query, broker request,
recording, scheduler, observation-start write or trading control is introduced.

## What the fields mean

| Field | Meaning |
|---|---|
| `range_state` | FUTURE before the requested first IST midnight; IN_PROGRESS until midnight after the final date; otherwise ELAPSED |
| `starts_at_ist`, `ends_at_exclusive_ist` | Boundaries of the requested date filter, with the IST offset |
| `elapsed_calendar_dates`, `remaining_calendar_dates` | Fully elapsed dates in that filter, clamped to the requested range; today counts as elapsed only after its final midnight |
| `seven_date_range_elapsed` | Exactly seven dates were requested and their exclusive end has passed; this is a date-range fact, not observation completion |
| `calendar_session_dates` | Dates with opening and closing windows in the pinned calendar, including dated special sessions |
| `elapsed_calendar_session_dates` | Those calendar windows whose closing instant has passed, including the exact close |
| `elapsed_session_dates_without_sampled_intervals` | Closed calendar-window dates with no positive measured interval for any requested key |
| `unknown_calendar_dates` | Requested dates with UNKNOWN_CALENDAR or UNKNOWN_HOURS |
| `review_blockers` | Fixed evidence/review reasons; these are separate from capture preflight blockers |

Sampling one key on a date does not establish coverage for all requested keys or the entire
session. Per-key samples, measured spans and missing time remain in the existing `days`
records. A lone accepted sample without an interval does not count as a sampled date.
Historical or rotated contracts are not assumed to be required on every date merely because
they appear in a report filter. Calendar windows do not prove the exchange actually opened.

## Review reasons

| Code | Meaning |
|---|---|
| `SEVEN_CALENDAR_DATES_REQUIRED` | The report filter covers fewer than the required seven dates |
| `REQUESTED_RANGE_NOT_ELAPSED` | At least one requested IST date has not fully elapsed |
| `SYNTHETIC_SOURCE` | Synthetic fixtures cannot satisfy genuine observation requirements |
| `SYNTHETIC_CALENDAR` | A fixture calendar is not official session evidence |
| `UNKNOWN_CALENDAR_WINDOWS` | At least one requested date has unknown hours/calendar |
| `CALENDAR_AMENDMENTS_UNVERIFIED` | Pinned source integrity does not establish amendment completeness |
| `ELAPSED_SESSION_DATES_WITHOUT_SAMPLED_INTERVALS` | A closed calendar window lacks any positive sampled interval for the requested keys |
| `ACCEPTANCE_CRITERIA_REVIEW_REQUIRED` | Required coverage quality/completion criteria still need review; no numerical threshold was invented |

`requested_range_is_verified_observation_start`, `minimum_coverage_threshold_defined`,
`review_complete` and `phase2_complete` remain false. Existing `assessment=NOT_CERTIFIED`,
zero qualifying days and disabled signal/execution/live flags are preserved. Even an elapsed
seven-date filter with samples on every calendar session date does not clear review.

The date filter does not set or recover a verified recording start, prove a full seven-day
connection history, or replace genuine timestamps/catalog lineage. Weekends/holidays do not
become missing trading sessions; explicit weekend special windows still need evidence.
Future windows are planning context only. No full-session coverage percentage is prescribed
without reviewing requirements, field semantics, clocks and actual data availability.

## Use the existing report command

```sh
uv run python -m scripts.initial_observation --local \
  --from-date 2026-11-11 --to-date 2026-11-17 --source UPSTOX_V3 \
  --instrument-key 'NSE_FO|35050' --instrument-key 'NSE_FO|45406'
```

Add `--format json` for the structured output. The Docker image must contain the reviewed
backend version. This command reads stored evidence; it never selects a current contract,
refreshes metadata or starts a capture. Keep private exports outside Git. Follow
[OBSERVATION_PLAN.md](OBSERVATION_PLAN.md) for operator budgets and fresh capture checks.

## Remaining completion work

Continue genuine collection only within the explicit pilot policy. Review minimum coverage,
missing-data handling, calendar applicability, timestamp uncertainty and report limitations
before considering a separate certifier. Later-phase indicators, patterns, paper signals
and performance analysis remain explicitly unimplemented in this Phase 2 evidence report.
No report or date arithmetic grants phase advancement or trading permission.
