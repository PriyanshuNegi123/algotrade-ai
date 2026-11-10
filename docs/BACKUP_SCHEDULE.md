# Three-day cloud backup schedule and local disk policy

User choice: back up every three days and keep backups primarily on Google Drive.
The installed macOS user LaunchAgent checks daily at21:30IST. A backup runs when at least
three IST calendar dates have elapsed since the last backup was created;otherwise it skips
without contacting Drive. Re-verifying an old backup does not postpone the next due date.
Next due after the9November acceptance:12November2026 at21:30IST.

The Mac must be available, the user logged in, Docker/private app database running and
Google authorization usable. Calendar jobs may be delayed by sleep;powered-off/logged-out
periods are not a guaranteed backup window. A later daily check catches a still-due backup.
No KeepAlive retry loop, RunAtLoad backup or autonomous Docker/broker startup is installed.
The installer requires an IST system clock;scheduled runs refuse a changed system offset
and record the condition rather than silently shifting the intended clock time.

## Commands

```sh
uv run python -m scripts.backup_job status
uv run python -m scripts.backup_job run
uv run python -m scripts.backup_schedule status
uv run python -m scripts.backup_schedule prepare
uv run python -m scripts.backup_schedule install
uv run python -m scripts.backup_schedule disable
```

`run` obeys the three-day policy. An explicit `run --force` is an immediate backup test,
not part of automatic scheduling. The installer creates only the current user's
`~/Library/LaunchAgents/com.algotrade-ai.cloud-backup.plist`;it refuses an existing job/file
with conflicting ownership/configuration. No root daemon,cron entry or trading job is added.
Program arguments are a fixed absolute venv interpreter/module,never a shell command.
Existing keys,tokens and environment values are not embedded in the plist.
`disable` removes only the matching inactive agent and refuses to interrupt a running job.

`status` reads local evidence without creating a key, contacting Google or starting capture.
It reports last backup creation,verification,next due date,last attempt and key readiness.
It cannot prove token non-revocation, remote availability or an offline recovery-key copy.
The user has not stored that recovery copy;health retains an explicit NOT_CONFIRMED warning.

## Disk and cloud behavior

New backup dumps/ciphertext exist in bounded RAM,then upload to Drive;there is no growing
local `.atbackup` cache. Isolated restores use tmpfs and remove their own temporary container.
PostgreSQL working data remains local. Moving/deleting operational data is outside this
backup policy. Keys and small per-backup receipts must remain accessible for recovery.

The earlier4,870,741-byte local encrypted copy was removed only after its Drive copy was
re-downloaded,decrypted and compared. `scripts.backup_postgres prune-local` provides the
same bounded cleanup of app-named verified cache files. It never deletes Drive files,
unverified local backups,symlinks,keys or receipts. Failed or missing cloud access preserves
the local cache. No cloud retention/deletion policy is enabled.

Only small fixed-size job status/check JSON files are updated;LaunchAgent stdout/stderr
go to/dev/null to avoid accumulating log files. The runner never copies raw subprocess
stdout/stderr into status. On failure,it records a safe state. Job overlap is locked;the
backup's existing bootstrap/Google locks still protect the underlying pipeline.
After15minutes,the wrapper requests SIGINT only on its own child and allows cleanup grace.
It does not SIGKILL a child still cleaning resources;CLEANUP_PENDING requires operator
inspection. A skipped check does not erase the last actual failure record.

## Verified evidence and remaining action

A forced cloud-only job completed upload/download/decrypt/isolated restore with no local
archive created. The installed agent then completed a real background due-check,exit0,
SKIPPED_NOT_DUE. Initial10second polling ended before startup finished;subsequent receipt
and exit status confirmed completion. No unsupported OS-permission conclusion was inferred.

Keep a separate secure recovery-key/receipt copy as described in BACKUPS.md. That step
is still outstanding and is not replaced by scheduling. No keys were uploaded to Drive.
Live trading remains disabled;no market recording or order execution was added.

Apple reference:[calendar-based LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).

Optional passphrase-encrypted off-device recovery kits are documented in
[RECOVERY_KIT.md](RECOVERY_KIT.md). Health distinguishes verified cloud kits from physical
offline copies; neither a local receipt nor scheduling proves present Drive availability.
