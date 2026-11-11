# Phase 2 local verification packet — 11 November 2026

Tested application source: `64c35bc`. This packet consolidates local evidence after the
observation progress and budget additions. No application, dependency, credential or CI
configuration fix was needed. It is not production approval, a penetration test, or a
successful GitHub Actions run. Phase 2 remains partial.

## Results

| Check | Actual result |
|---|---|
| Locked uv sync | Passed; uv 0.12.19, Python 3.12.14 |
| Ruff lint and format | Passed, 126 files |
| Strict mypy | Passed, 51 source files |
| Full suite, native PostgreSQL 17.11 | 784 passed, 0 failed, 0 skipped |
| Full suite, Docker PostgreSQL 17.6 | 784 passed, 0 failed, 0 skipped |
| Dependency audit | 73 installed packages, 0 known vulnerabilities, 0 skipped packages |
| Real loopback TLS/WebSocket checks | Passed using synthetic grants and temporary certificates |
| Secret/whitespace checks | All 14 changed files passed default Gitleaks without allowances; history passed unchanged exact allowances; whitespace clean |
| Durable synthetic supervision | Two bounded sessions, subscriptions, quota totals and closure passed |
| Compose configuration with OAuth volume | Private database, loopback app and literal secret handling passed |
| Disposable Compose bootstrap and OAuth lifecycle | Passed non-root/mode, encrypted roundtrip, persistence and recreation checks |
| Disposable restart/outage/auth checks | Passed readiness failure/recovery, session durability, CSRF, revocation and absent execution routes |

Both full suites reported the existing non-fatal Starlette TestClient deprecation warning.
The dependency result is dated and covers Python dependencies, not container/OS CVEs,
private code vulnerabilities or future advisories. No dependency was upgraded or ignored.

## PostgreSQL and CI comparison

`.github/workflows/ci.yml` uses `postgres:17.6-bookworm`. In addition to the normal 17.11
native harness, a generated disposable 17.6 container was bound to an automatically assigned
loopback-only port with tmpfs data and a 512-MiB memory limit. Generated credentials existed
only for that temporary database. The full suite received only its private test URL through
the child environment; no URL/password was printed or committed.

The native setup role is non-superuser with CREATEROLE for temporary permission fixtures.
The extra Docker setup role matched CI's PostgreSQL-initialization superuser behavior;
this was confined to the temporary test database. The restricted execution fixture still
uses a separate non-owner, non-superuser role and verifies effective INSERT denial. The
previously failing privilege test passed in both environments. Tests were not skipped,
weakened or deleted, and no production ownership/grant changes were made.

The database image/version and uv version match the workflow, but local host architecture,
runner/platform and GitHub execution are not certified by this packet. A new hosted workflow
must pass after an approved push before CI success can be claimed for these commits.
Nothing was pushed during this verification.

## Isolation and cleanup

The TLS/supervision verifier uses loopback sockets, synthetic frames and a temporary SQLite
archive. It does not dial a broker. Its shortened synthetic rollover wait is test-only;
production retry/backoff was not changed. Temporary certificates, servers and archive were
removed by their context cleanup.

The Compose verifier generated a unique project and protected temporary environment file.
It exercised the real bootstrap helper using those settings, including retaining an exact-
project OAuth volume after recreation without repeating opt-in. Only synthetic OAuth data
was stored. App UID 10001, private file/directory modes, read-only code, callback denial/CSRF,
encrypted storage and volume persistence passed. No actual provider consent/token request
was made. Database outage testing stopped only that verification project's database.

The temporary Compose containers/volumes and CI-version container were removed. Native
PostgreSQL and its temporary directory were removed. Docker build images/cache were not
pruned; no unrelated runtime resources or cloud files were deleted.

Independent before/after checks confirmed the operator container ID, image and start instant
were identical: it was not restarted. Protected .env/admin-password fingerprints and all
existing instrument/candle/chain/capture/session/event archive hashes matched. No active
operator captures/children remained; mode was OBSERVATION with entries/live disabled.
The three-run daily allowance was not expanded and no new genuine recording occurred.

## Reproduction and private evidence

The existing commands used, without operator credentials:

```sh
uv sync --locked
uv run ruff check backend tests scripts
uv run ruff format --check backend tests scripts
uv run mypy
uv run python -m scripts.verify_postgres --bin-dir .local/verification/postgres/17/bin
uv run python -m scripts.verify_supervision
uv run pip-audit --progress-spinner off
uv run python -m scripts.verify_compose --config-only --oauth-vault
uv run python -m scripts.verify_compose --bootstrap --oauth-vault
```

The extra 17.6 full-suite check used a private disposable harness matching the service image
in `ci.yml`. It created and removed only its own generated container. Do not point
TEST_POSTGRES_URL at an existing/operational database to reproduce this test.

Protected ignored evidence under `.local/verification/` includes:
`verification_packet_before_20261111.json`, `verification_packet_20261111.json`,
`dependency_audit_20261111.json`, `ci_postgres_20261111.json` and its redacted test output.
No real credentials or raw provider responses belong in public evidence.

## Remaining gates

Continue the explicit [observation plan](OBSERVATION_PLAN.md) only after current checks.
Seven-date requests and sparse samples are not completed observation days. Calendar/unit
clarification, timestamp uncertainty, minimum completion criteria, ordinary OAuth expiry
and a new hosted CI result remain unresolved. The next backup is due under the unchanged
three-day policy; this packet did not perform a Drive backup or restore. Live execution
remains unavailable and no later-phase strategy, paper engine or P&L claim is added.
