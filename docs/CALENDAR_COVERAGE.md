# NSE derivatives calendar and sampled coverage

P2-003G provides a versioned calendar evidence snapshot and bounded read-only coverage reports.
Scope is NSE_FO instrument keys; cash/index-reference sessions are not inferred from derivatives
hours. Reports do not certify completed market days, exact tick completeness or trading permission.
Actual authenticated capture remains unverified. Synthetic records are always a separate source.

## Verified sources and temporal limits

Baseline reviewed2026-11-06;bounded source/amendment follow-up2026-11-10:

| Evidence | Use |
|---|---|
| [NSE/FAOP/71777](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf) | Published2026 F&O holiday baseline |
| [NSE/FAOP/72262](https://nsearchives.nseindia.com/content/circulars/FAOP72262.pdf) | Additional January15 closure |
| [NSE/FAOP/72352](https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf) | Explicit February1 historical normal session09:15–15:30 IST |
| [NSE/FAOP/76940](https://nsearchives.nseindia.com/content/circulars/FAOP76940.pdf) | November8 special continuous session14:20–15:40 IST |
| [NSE market timings](https://www.nseindia.com/static/market-data/market-timings) | Current F&O normal window09:15–15:40 IST |

Original downloaded bytes, URLs/retrieval instants and SHA-256 hashes are in
backend/app/market_data/calendar_data. The policy JSON pins all six evidence/manifest hashes;
loading verifies them, then caches the reviewed policy. Responses include the policy content
identity, source references/URLs, evidence hashes, review instant and validity. These are local
integrity/version checks, not a signed NSE calendar or proof that no other notice exists.
Downloaded HTML is hashed data only; it is never executed or served as application frontend.

The current timing page does not establish when its current hours first became effective.
Therefore the local regular-hours review boundary is2026-11-06, not a claimed exchange-effective
date. Earlier2026 ordinary weekdays are UNKNOWN_HOURS. Holidays and explicitly documented
special sessions remain classified using their dated circulars. Outside2026 is UNKNOWN_CALENDAR.
The baseline must be deliberately reviewed/versioned for future years or further amendments.
No request downloads a new calendar or silently substitutes a third-party holiday library.

Classification priority:out-of-validity unknown, explicit special session, explicit holiday,
weekend, unknown historical hours, then reviewed regular baseline. November8 therefore remains
a special Sunday session. Times use Asia/Kolkata and convert to aware UTC. Windows are half-open
[open,close); pre-open, trade-modification and cash closing auctions are outside this scope.
Reports always expose amendment_completeness_verified=false and realtime_calendar=false.
Future regular dates are baseline schedules, not a guarantee against subsequent changes.

## Bounded amendment follow-up — 10 November

The review found the additional dated F&O circular above and verified its original PDF
table visually. It adds one historical Sunday exception; pre-open and trade modification
are excluded. Regular hours/review boundary, existing holidays and the November exception
are unchanged. Fresh downloads of the three existing circular PDFs matched pinned bytes;
the current timing page's F&O row still agrees with the baseline. Archived HTML is preserved.

The new PDF is archived and SHA-256 pinned. sources.json gains its fixed primary URL and
retrieval time;the policy pins that manifest's new hash and records the updated review
instant. The loader's exact evidence-file allowlist grows by that one filename;missing or
tampered evidence still fails closed. Calendar identity changes deliberately, so host/runtime
must be deployed together before readiness can match again. Existing observation archives
are not rewritten or retroactively certified.

Searches covered official-domain annual-holiday modifications, special F&O sessions and
the immediate upcoming date. Wrong-segment and mock-session hits were excluded. This is
a bounded discovery review,not an exhaustive authenticated exchange circular register scan.
amendment_completeness_verified and realtime_calendar remain false. UNKNOWN_HOURS before
the ordinary-hours boundary remains unchanged outside explicit dated evidence. Historical
coverage queries can now describe the documented exception;this is a policy correction,
not captured data or a completed observation day.

Verification adds exact historical window boundaries, preservation of neighboring unknown
hours, strict evidence-set rejection and tamper checks. Automated tests use synthetic clocks
and disposable databases. The original PDF was retrieved over IPv4 after a direct Python
request timed out;no mirror, broker credential or private endpoint was used. Public-source
downloads and web review are separate from automated tests,which prohibit outbound requests.

## Report inputs, snapshot and bounds

A request contains inclusive from_date/to_date (at most7 dates),1–20 unique NSE_FO keys and
source UPSTOX_V3 (default) or SYNTHETIC. Index keys/URLs, duplicate or excessive keys and invalid
ranges are rejected. Calendar inspection permits up to31 dates. Source categories never mix;
SYNTHETIC is prominently returned, and fixture calendars remain SYNTHETIC_FIXTURE internally.
Only the bundled official baseline can be selected through HTTP/CLI; no caller-supplied source
URL, SQL, policy path, certification flag or as-of time is accepted.

PostgreSQL reports run inside a repeatable-read, read-only transaction with2second statement
timeout. Candidate sessions are bounded by source and UTC date overlap; immutable payloads and
metadata are read from the same snapshot. Bounds:100 candidate sessions,20,000 total events,
8MiB total recorded canonical bytes. The candidate bound applies before filtering JSON requested
keys. Limit exhaustion fails the whole report, never returns a partial result presented as complete.
Database/index/Python overhead is additional; this is a bounded research report, not an unlimited
warehouse query. No mutation, migration, automatic stream or dependency was added. Head stays0005.

Each event's canonical SHA-256 and typed schema are revalidated before aggregation. A corrupt
archive fails closed. Original session/attempt boundaries, generation/receipt and monotonic times
are retained. The report does not modify event archives, counters, leases or global mode.

## What sampled coverage means

For each requested key, count accepted positive-price observations with last-trade age0–15seconds
and source generation age0–10seconds at receipt. These checks are recomputed from stored times;
a stored freshness label alone is not evidence. A source sample must fall inside the reviewed
session window and before the report's server-generated as_of time.

A sampled interval requires adjacent qualifying records for that key, same session/attempt/date,
positive receipt and monotonic deltas each <=10seconds. Credit the smaller delta, clipped to the
window. Non-data/status/PLAN/idle/disconnect/backoff/out-of-order/empty events break continuity;
an intervening frame omitting the key also breaks its continuity. Never bridge distinct sessions,
reconnects, stale/missing trades or unknown windows. This deliberately understates evidence during
incremental quiet feeds. It does not infer nonexistent exchange trades or fill any prices.

Intervals are unioned across overlapping sessions per key/date, so duplicate simultaneous runs
cannot double-count time. accepted_samples counts stored accepted observations, not unique exchange
ticks. Duplicate/out-of-order/disconnect counters describe selected stored events; exact loss is
unknown because the implemented feed provides no exchange sequence. outside_or_unusable_frames
counts frames excluded by date/window/generation-time checks before per-tick qualification.

Each date returns scheduled_ms, elapsed_scheduled_ms and per-key sampled_interval_ms,
uncovered_elapsed_ms, sampled_fraction and evidence state. Future unopened windows have zero
elapsed duration and null fraction; no future time is reported as missing. Known closures have
zero scheduled duration. Unknown hours/calendar have null scheduled/uncovered durations; missing
time is not guessed. NO_RECORDED_INTERVAL describes absence of interval evidence, not proof of
an exchange outage. Health of unrequested keys and full-universe coverage are not asserted.

The calendar snapshot is a review baseline, and sampled spans do not establish complete market
sessions. All reports retain calendar_verified=false, qualifying_observation_days=0, false
signal/execution eligibility and live_enabled=false. Global observation_started_at stays null.
No seven-day result or strategy/live activation is inferred from a percentage.

## Private reads and offline command

All endpoints require an administrator session:

| Route | Parameters |
|---|---|
| GET /api/observations/calendar | from_date/to_date; max31 inclusive dates |
| GET /api/observations/coverage | from_date/to_date; repeated instrument_key; optional source; bounds above |

Invalid input/report limits422, missing/invalid calendar evidence or corrupt archive503,
database failure503. Unauthorized401. No write/start control exists. Coverage/schema validation
errors never echo secrets or raw upstream content. No frontend changes were made.

With the configured host-reachable PostgreSQL:

```sh
uv run python -m scripts.observation_coverage --from-date 2026-11-06 --to-date 2026-11-06 --instrument-key 'NSE_FO|ACTUAL_CATALOG_KEY'
```

Use an actual recorded option key. This command reads stored events only, does not request broker
data or need a broker credential. Database secrets stay in protected server settings. Docker's
private DB remains unpublished. Calendar source files must ship with the backend image.

## Actual verification and next task

301 passed on disposable PostgreSQL17.11; default283 passed/18 PG skipped.25 new cases cover
source hashes, Sunday override/holiday amendment, UTC/local boundaries, unknown hours/year,
request bounds, source separation, overlap union, discontinuities, empty/future/closed windows,
archive/resource failure, private nonmutating endpoints and native snapshot/restart behavior.
Ruff70/mypy31/lock pass; no dependency changes. See VERIFICATION.md for container evidence.
All stored market data in these tests is synthetic; the source calendar documents are genuine.

Next P2-003H:bounded multi-session capture supervision with explicit total runtime/session/byte
quotas, cooperative stop, fresh authorization/catalog resolution and aggregate health. Actual
broker acceptance and genuine prolonged observation remain operator-dependent, unverified gates.
Do not fabricate days or promote strategy/live permissions.

## P2-003H — bounded supervision (2026-11-06)

Bounded multi-session supervision is implemented separately (CAPTURE_SUPERVISION.md). It
creates distinct durable sessions with explicit discontinuities and quotas; reporting continues
to union qualifying same-source spans without connecting those boundaries. Supervision does
not relax static calendar/amendment limits or certify complete days. Schema now0006.
