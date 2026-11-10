# AlgoTrade AI

Observation-first foundation for an Indian derivatives research and monitoring platform.
**Phase 2: read-only connectivity, versioned NSE metadata, historical-minute ingestion and option-chain snapshots.**
Durable bounded research recording is available; calendar-certified observation days,
simulation, signals and broker execution remain unavailable.
Balances and performance are unavailable until verified sources are integrated.
This release is not production ready.

## Local setup

Python 3.12, [uv](https://docs.astral.sh/uv/), and Docker Compose are required.

```sh
uv sync --locked
uv run python -m scripts.bootstrap_local
```

Keep Docker Desktop running. Open http://127.0.0.1:8000 and retrieve the generated
administrator password locally from `.local/runtime/admin-password.txt`. Never paste it
into chat. The helper preserves existing settings and data, creates protected missing
credentials, starts private PostgreSQL, applies migrations and verifies login/readiness.
The database has no published port; the app binds only to loopback. No broker requests or
capture start automatically. See [bootstrap safeguards and recovery](docs/LOCAL_BOOTSTRAP.md).

Without Docker, provision PostgreSQL separately, set `DATABASE_URL` to that server,
run `uv run alembic upgrade head`, then:

```sh
uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --no-proxy-headers
```

For administrator password changes and session revocation, see
[local credential rotation](docs/ADMIN_CREDENTIAL_ROTATION.md). Never share the local password.

The shell and liveness endpoint work without a database; sign-in and readiness fail closed.
No tables are silently created at application startup.

## Optional read-only broker configuration

Official API review and the initial manual exchange-status probe are implemented. The public instrument-master import is also implemented. Historical-minute and option-chain imports are implemented; no funds or order submission is implemented. Bounded LTPC streaming is available through the explicit host CLI.

```sh
uv run python -m scripts.configure_upstox
```

This prompts locally for the Analytics credential without echoing it and writes only the
broker configuration into a protected .env, preserving other settings. Configure database/admin
access using the bootstrap above, rerun it after broker configuration, sign in and use **Check read-only connection**.
No broker token is accepted through the dashboard or returned to frontend JavaScript.
See [secure setup](docs/UPSTOX_SETUP.md) and [verified API sources](docs/BROKER_COMPLIANCE.md).
A real one-day Nifty50 historical import has now succeeded; one real option-chain snapshot also succeeded; basic closed-market streaming acceptance now verified; durable/fresh-session coverage remains pending.

## Public instrument metadata

```sh
uv run alembic upgrade head
uv run python -m scripts.sync_instruments
```

These CLI commands assume PostgreSQL is reachable from the host using DATABASE_URL.
For Docker deployment, Compose applies migrations at startup; use the dashboard import
control after signing in. The private Docker database is not published on the host.

The import stores validated NSE index/option/futures metadata and an immutable compressed source
snapshot in your configured database. No broker token is needed. The dashboard also provides
an administrator-only import control. Apply the new migration before starting the updated app.
See [instrument scope, safeguards and actual evidence](docs/INSTRUMENT_MASTER.md).

See [local connection readiness](docs/CONNECTION_READINESS.md) for the verified local catalog
and remaining operator credential setup.

## Historical minute research data

After metadata import and local Analytics credential setup, use the dashboard historical form
or the host CLI `uv run python -m scripts.import_candles --help`. Only1/5/15minute intervals,
up to28 historical calendar days ending before today are supported initially. Apply
the current migration head first. Inputs/responses are validated and archived as immutable batches;
gaps are reported without fabricated bars. Real acceptance verified for75 Nifty50 five-minute bars on2026-11-05; broader coverage remains unverified.
See [scope, safe setup and limitations](docs/HISTORICAL_CANDLES.md).

## Verification

```sh
uv run pytest
uv run ruff check backend tests scripts
uv run ruff format --check backend tests scripts
uv run mypy
uv run pip-audit
```

Default tests use temporary SQLite files for isolated authentication/migration checks.
They do not validate PostgreSQL semantics. To run the ten real PostgreSQL checks:

```sh
TEST_POSTGRES_URL='postgresql+psycopg://user:password@localhost:5432/disposable_test_db' uv run pytest tests/integration/test_postgres.py
```

Use a dedicated disposable database, never an existing application database.
Each PostgreSQL test creates and drops only a unique test schema. CI provisions PostgreSQL
and runs these checks. CI execution is not claimed locally.

To start a temporary native cluster with generated credentials and run the complete suite:

```sh
uv run python -m scripts.verify_postgres --bin-dir /path/to/postgresql/bin
```

The script binds loopback, uses SCRAM authentication and a non-superuser test role, and stops
and removes only its temporary cluster afterward. It does not download or install PostgreSQL.

To validate Compose configuration and then exercise isolated containers:

```sh
uv run python -m scripts.verify_compose --config-only
uv run python -m scripts.verify_compose
```

The runtime check requires a running Docker engine. It generates temporary credentials and a
unique project/port, checks migrations, authentication, restart and database outage recovery,
then deletes only its own containers and volumes. It never overwrites your `.env`.
A standalone Compose CLI can be selected with `--compose-bin /path/to/docker-compose`.
See [actual verification results](docs/VERIFICATION.md): image build and the full container
smoke command passed locally. Temporary verification containers are removed afterward;
use the local setup instructions above for a persistent development workspace.

## Operational boundaries

- Starts in `OBSERVATION`; entries remain disabled even after readiness succeeds.
- `PAPER` is accepted as a future-mode label; no simulator exists yet.
- `LIVE` and `LIVE_ENABLED=true` fail configuration validation.
- All credentials remain server-side; session IDs are HttpOnly, CSRF tokens stay in memory.
- Session restoration permits viewing; sign in again after a page reload to enable sign-out.
- Global sign-in throttling requires exactly one application worker.
- The 35% stop/circuit-breaker values are required defaults displayed in the shell;
  risk enforcement is a later phase and is not represented as working protection.

Start future work with [CURRENT_STATE](agent_memory/CURRENT_STATE.md) and
[HANDOFF](agent_memory/HANDOFF.md). See [deployment](docs/DEPLOYMENT.md),
[security](docs/SECURITY.md), and [test plan](docs/TEST_PLAN.md).

## Option-chain snapshots

Import current metadata, configure the server Analytics credential, then use the dashboard
option-chain panel to load catalog expiries and explicitly capture a research snapshot.
Host CLI: `uv run python -m scripts.capture_option_chain --help`. Apply migration
`0005_observations` first. Quote freshness stays UNKNOWN and signals/execution remain disabled.
See [validation, API and actual acceptance evidence](docs/OPTION_CHAIN.md). One Nifty50 snapshot
for expiry2026-11-09 verified135strikes/270legs;72legs flagged, freshness UNKNOWN.

## V3 binary feed foundation

Server-only authorization grants and catalog-bound LTPC decoding are implemented. The bounded server connector is now implemented; it starts only through the explicit host CLI
and records research sessions/events in the configured database. For offline captured frames:
`uv run python -m scripts.decode_feed --help`. See [scope and timestamp limitations](docs/WEBSOCKET_FEED.md).
One20second closed-market Nifty50 grant/subscription/Protobuf/heartbeat check passed;
one stale snapshot, no durable recording or certified day. All trading flags stay disabled.

## Bounded streaming research

`uv run python -m scripts.stream_feed --help` exposes an explicit1–300second LTPC session
with protected server credentials, catalog validation and bounded reconnect/heartbeat handling.
See [connection controls and limitations](docs/FEED_LIFECYCLE.md). No automatic startup,
completed observation-day reporting or live trading is enabled. Actual broker acceptance is unverified.

## Durable research archive

The bounded streaming CLI now persists sessions, catalog attempts and validated events by default.
Apply the current migration head (0006_capture_runs). Administrator reads are available under /api/observations/sessions.
See [atomicity, recovery and sampled-span limits](docs/OBSERVATION_STORAGE.md). No real broker
capture or completed observation day has been verified.

## Calendar and coverage research

Private calendar/coverage reads and `scripts.observation_coverage --help` now report bounded
NSE derivatives sampled spans from stored events. The bundled2026 calendar includes verified
source hashes and explicit historical-hour limits. See [policy and limits](docs/CALENDAR_COVERAGE.md).
Synthetic data stays separate; no completed observation days or trading permission are certified.

## Bounded multi-session capture

`uv run python -m scripts.supervise_capture --help` adds explicit parent runtime/session/storage
quotas, cooperative stopping and durable aggregate summaries. Apply0006_capture_runs first.
See [supervision, recovery and operator limits](docs/CAPTURE_SUPERVISION.md). No background
feed starts automatically, and no genuine broker acceptance or completed observation day is claimed.

## Capture preflight

Run `uv run python -m scripts.capture_preflight --instrument-key 'NSE_INDEX|Nifty 50'` for safe
local diagnostics. It checks configuration, schema/grants, metadata, credential expiry, calendar
and quotas without starting capture. The supervisor CLI now blocks on failed preflight;
`--preflight-only` checks without launching. See [report contract and current blockers](docs/CAPTURE_PREFLIGHT.md).
A local pass does not verify broker acceptance or permit trading.

## Bounded recording in private Docker

Check the private runtime without starting capture:

```sh
uv run python -m scripts.capture_local --instrument-key 'NSE_INDEX|Nifty 50' --preflight-only
```

See
[local capture workflow and actual evidence](docs/LOCAL_CAPTURE.md) for a bounded recording
command,private archive reads and interruption limits. Trading remains disabled.

Inspect local captures with `uv run python -m scripts.capture_local --status`. Targeted
cooperative stop uses `--stop` followed by the exact capture ID;poll `--status --capture-id`
until parent and child are closed. See LOCAL_CAPTURE.md for acknowledgment/freshness limits.

Phase2 completion evidence and remaining requirements: [acceptance checklist](docs/PHASE2_ACCEPTANCE.md).
The new initial-observation report is evidence-only and never certifies elapsed days.
Google Drive is the selected future backup/archive target; see [storage decision](docs/STORAGE.md).

Google Drive OAuth and synthetic cloud storage are verified: [setup and security](docs/GOOGLE_DRIVE.md). PostgreSQL remains the working database.

Manual encrypted PostgreSQL Drive backups and isolated cloud restore are verified: [backup/recovery guide](docs/BACKUPS.md). Recovery keys stay off Drive.

Cloud-first encrypted backups run every three IST calendar days: [schedule and health](docs/BACKUP_SCHEDULE.md). Local backup caches do not accumulate.

Passphrase-encrypted Drive recovery: [RECOVERY_KIT.md](docs/RECOVERY_KIT.md).

Optional Upstox browser authorization: [UPSTOX_OAUTH_BROWSER.md](docs/UPSTOX_OAUTH_BROWSER.md).
Synthetic security/browser checks are verified. Optional private storage is available through
`docker-compose.oauth.yml`; registered-app settings and explicit deployment remain required.
Use `uv run python -m scripts.bootstrap_local --oauth-vault` for first opt-in. Later bootstrap
runs retain the existing project volume automatically; see [bootstrap](docs/LOCAL_BOOTSTRAP.md).
Save registered app settings first with `uv run python -m scripts.configure_upstox_oauth`;
enter the secret only at its hidden local prompt. This preserves the Analytics credential.
