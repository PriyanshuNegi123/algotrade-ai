# Local administrator credential rotation

The administrator credential belongs to AlgoTrade AI, independently of the Upstox Analytics
token. Never paste either credential into chat, screenshots, shell arguments or reports.

After rotation, open http://127.0.0.1:8000, refresh and sign in using the current password
stored locally in `.local/runtime/admin-password.txt`. Copy only the file contents, without
a newline or surrounding spaces. Existing browser sessions are deliberately revoked; the
old password must fail. Password values are never included in handoff records.

The authorized local maintenance procedure stops the sole app before revocation so new
sessions cannot race the change, deletes all administrator sessions in a database transaction,
generates a random replacement, writes its Argon2 hash into protected `.env` and stores the
new password in the protected local password file. The existing bootstrap then recreates the
app with the updated environment. Ordinary bootstrap does not rotate an existing credential.

Credential files use atomic per-file replacement and mode0600; the runtime directory uses
0700. Replacement of two separate files is not one filesystem transaction. During maintenance,
a protected `admin-password.next.txt` candidate is retained until post-start checks complete,
so an interruption can be repaired locally without restoring the exposed credential. Never
print that file; remove it after verified successful completion. No general password-reset
API or new admin mutation endpoint was introduced by this one-time maintenance operation.

Verification must include actual old-password rejection, rejection of a session created
before rotation, fresh login and CSRF logout with the replacement, zero remaining sessions,
private local readiness/preflight, and unchanged broker/database settings and market-data
archives. Do not delete database volumes or market records to reset authentication.

This local plaintext password file is protected storage, not an encrypted vault. MFA,
encrypted secret storage, production role separation and broader hardening remain pending.
Password rotation does not change OBSERVATION mode or authorize trading/capture.

## 2026-11-06T14:52:41.408698+00:00 — P2-003N administrator rotation COMPLETE

User explicitly authorized rotation of the administrator credential exposed in chat. One-time
local maintenance completed without printing/passing secrets in argv or reports. Stopped sole
app before session deletion; transactionally revoked4sessions, confirmed0, generated random
replacement/Argon2 hash, protected per-file atomic replacement of .env and local password,
then recreated app through existing bootstrap. Candidate password file removed after success.
Actual old-password POST401, pre-rotation cookie GET401, replacement login200/private GET200
and CSRF logout204. Bootstrap readiness/login/local preflight passed; zero blockers. Final
admin_sessions0. Password at .local/runtime/admin-password.txt, mode0600; .env0600, runtime0700.
Retrieve it only locally and sign in again; never reproduce the old/new password in records.

Verified unchanged parsed configuration except ADMIN_PASSWORD_HASH, including broker token,
expiry, DB credentials and OBSERVATION settings. Read-only DB manifests (counts plus row
fingerprints compared in memory, not logged) match before/after for catalogs/history/research
and schema revision. Retained1instrument snapshot,6504instruments,1history batch,75candles,
0observation sessions/events/capture runs. DB unpublished/app127.0.0.1:8000 still running.
No real broker request, source/schema/dependency/UI change or trading/capture action. Head0006.
Mode OBSERVATION; entries/live/signal/execution false, no observation clock/certified days.
Stored history acceptance retained; streaming/option-chain acceptance remains unverified.

Checks:offline locked uv sync PASS; default326passed/22PGskipped, one upstream TestClient
warning; Ruff lint/format PASS83files; strict mypy PASS36backendfiles. Full disposable PG
result added below. Explicit rotation verification against operator runtime is distinct from
disposable regression tests; tests never contact actual broker accounts. No permanent reset
CLI/API added; temporary reviewed maintenance script contains no secrets and was removed.
Files:docs/ADMIN_CREDENTIAL_ROTATION.md, LOCAL_BOOTSTRAP.md, SECURITY.md, VERIFICATION.md,
CONNECTION_READINESS.md, README.md and all eight agent_memory records. Protected operator
.env/password changed locally and remain ignored. Aggregate ignored report:reports/admin_rotation.json.
Remaining:local plaintext password storage/MFA/backups/production hardening; no encrypted
vault claim. Per-file atomic writes are not a transaction across both credential files.
Next:P2-003O bounded real option-chain acceptance:explicit current catalog expiry, one
read-only snapshot, validation/provenance/private DB read; no orders or automated capture.
