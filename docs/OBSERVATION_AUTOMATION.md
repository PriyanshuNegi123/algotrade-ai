# Finite read-only observation job

The user's 11 November 2026 request authorizes routine remaining work without repeated
minor approvals. It supersedes the earlier manual-only pilot choice for this bounded
read-only collection job. Phase order, reviewed quotas and every trading restriction remain.
This job cannot certify Phase 2 or send a later message into the Codex conversation.

## What runs

A macOS user LaunchAgent (`com.algotrade-ai.observation-pilot`) checks at 09:45, 12:15 and
14:45 IST on **12, 13, 16 and 17 November 2026**. An 18 November 09:45 check exports the
window evidence if its safety guards permit and submits a local notification requesting review. The job additionally
checks the exact year/date, pinned calendar and five-minute checkpoint window. Sleeping
through that window skips the checkpoint; there is no catch-up or automatic retry loop.
Launchd calendar entries recur annually because that interface has no year selector, but
application guards prohibit later-year captures and avoid repeated end-report generation.
The registration can be disabled after the pilot. RunAtLoad and KeepAlive are false.

Each checkpoint permits one fixed `NSE_FO|45406` attempt: 120 seconds, one child, at most
300 events and 262,144 canonical bytes. The contract is a diagnostic selection, never a
trade recommendation. A stale/missing/expired contract blocks; no automatic roll occurs.
The stored pilot budget includes manual/ad hoc/failed captures; today's three-run allowance
is already consumed. Existing per-parent enforcement is unchanged. Wrapper serialization
and checks do not become an account-wide coordinator or a backend reservation mechanism.

Docker, the private app, this Mac and its logged-in user session must remain available.
The job never starts Docker, installs a system service or renews/promotes broker credentials.
The ordinary OAuth expiry remains separate from the existing Analytics data credential.

## Checks and failure behavior

The job locks its private ledger and the existing bootstrap/capture lock. It durably marks a
checkpoint attempted before runtime work, preventing replay after crashes. Source SHA-256
fingerprints, IST system timezone and local clock rollback guards must pass. It inspects
PostgreSQL with read-only transactions and short SQL timeouts. Active/unresolved recording,
exhausted daily/window/report budgets, failed backup evidence or stale readiness blocks.

At most one official public metadata import is attempted per IST date when currentness
requires it; existing same-date imports count. Fresh preflight checks validate the fixed
contract and actual session. A bounded in-memory pg_dump size check occurs once per date;
budget, disk and readiness are checked again afterwards. No local dump file is retained.

Storage stops: less than 2 GiB free on host or PostgreSQL's Docker filesystem; database at
or above the smaller of 64 MiB and its armed baseline plus 32 MiB; custom dump at or above
24 MiB. PostgreSQL remains the operational database. No rows, volumes, source archives or
Drive files are deleted. Existing three-day encrypted Drive backups are unchanged; their
verified receipts are required, and a missed due date blocks subsequent dates' collection.
Metadata growth can reach these limits before all checkpoints finish; no limit is raised.

Parent/child closure, source, fixed request/policy and quota totals must agree. An uncertain
remote timeout is reported as **unknown**, never as confirmed stopped, and permanently
pauses subsequent checkpoints until explicit investigation. The remote supervisor still
has its existing finite deadline. Inspect the exact persisted parent before cooperative
stop; never broadly kill processes. A report failure after recording also pauses the job.
New generation-after-receipt or too-old frame counts above the armed report baseline pause
collection and request review; timestamp tolerances and archived evidence are never altered.
Existing clock anomalies remain unresolved and are not normalized or accepted as coverage.

Status, once-only ledger, arming receipt and small evidence reports live under ignored
`.local/observation-job/` with private ownership/modes and symlink rejection. Secrets remain
in existing server storage, absent from scheduler arguments and environment. Stdout/stderr
are discarded by the agent; CLI errors use fixed safe codes. No broker support message,
strategy, order, execution route, live flag, credential change or Git push is introduced.

## Operator commands

```sh
uv run python -m scripts.observation_schedule status
uv run python -m scripts.observation_job status
uv run python -m scripts.observation_schedule disable
```

The reviewed local install command is `uv run python -m scripts.observation_schedule install`.
Installation arms a baseline and installs only this exact user-agent label. Conflicting
jobs are refused. Disabling refuses an active process and preserves every evidence file.
Reinstalling never clears an uncertain-capture pause or the once-only checkpoint ledger.
Changing guarded source requires review and re-arming; do not erase a pause to bypass review.

macOS notifications contain only a fixed request to review private status. A successful
osascript exit records **submission**, not proof the notification was displayed or read;
Focus, notification settings or a sleeping/logged-out Mac can prevent timely attention.
There is no promise of a later chat notification or unattended Phase 2 completion.

## Remaining acceptance

The 11–17 November sparse pilot is evidence collection, not seven certified days. Real
elapsed time, independently reviewed coverage criteria, clock cause, calendar amendments,
field-unit clarification and hosted CI for the new commit remain gates. End-of-window
status is `WINDOW_ENDED_REVIEW_REQUIRED`; `phase2_complete` and `live_enabled` stay false.
See [PHASE2_ACCEPTANCE.md](PHASE2_ACCEPTANCE.md) and [OBSERVATION_REVIEW.md](OBSERVATION_REVIEW.md).
