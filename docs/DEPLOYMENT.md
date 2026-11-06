# Development deployment

Use [secure local bootstrap](LOCAL_BOOTSTRAP.md) for the default development setup.
For manual configuration, use README setup; validate with `docker compose config --quiet` (never paste expanded
configuration because it contains secrets). Run `docker compose up --build -d` then
check `/health/live` and `/health/ready`. Readiness requires schema revision and admin hash.
Verify the application cannot accept LIVE configuration. Never expose PostgreSQL publicly.

Compose migrates before the app starts. Back up before schema changes. Initial downgrade
revokes sessions by dropping their table. `docker compose down` preserves the named data
volume; adding `-v` destroys it and must not be used against important data.

Production deployment is not approved by Phase 1. Configure registered DNS/host and exact
HTTPS origin, APP_ENV=production, COOKIE_SECURE=true, TLS reverse proxy, restricted
administrator network, secure environment storage, backup encryption and monitoring.
Set strong matching DB credentials locally. Keep `.env` mode 0600. Never copy secrets into
images or commits. Set production allowed hosts explicitly; remove `testserver`.

Run one worker. API startup does not automatically reconcile, collect data or schedule jobs;
those services are not implemented. Never interpret ready as trading authorization.
Container tags are explicit; immutable digest pinning and image vulnerability scanning remain
release gates. Compose configuration, actual image build, migrations, login, non-root UID,
application restart and database outage/recovery checks have passed locally on Docker 29.9.2
with Compose 5.6.1. Native PostgreSQL tests also passed. CI execution remains unverified.

Use `uv run python -m scripts.verify_compose` for an isolated build/auth/restart/outage check.
The script creates a unique project and temporary credentials, then removes only those
resources. It does not replace the operator .env. APP_ENV_FILE selects a service environment
file (default .env); APP_BIND_PORT selects the loopback app port (default 8000).
See VERIFICATION.md for actual results and remaining production limitations.

If this terminal was open before Docker Desktop installation and cannot find docker, use:

```sh
export PATH="/Applications/Docker.app/Contents/Resources/bin:$HOME/.docker/bin:$PATH"
```

Keep Docker Desktop running while using containers. Docker context selects the user engine
socket; a global /var/run/docker.sock symlink is not required for this verified setup.

For this iteration, apply `uv run alembic upgrade head` before running the updated app.
The required revision is0002_instruments; readiness fails with the old revision or missing
catalog tables. `uv run python -m scripts.sync_instruments` imports to the configured DB.
This needs internet access to the fixed public assets host, not a broker token. Back up before
downgrading:0002 downgrade deletes catalog archives/entries but preserves admin sessions.
Automatic source-archive retention and backup scheduling are not implemented.

Current head is0003_candles. Apply reviewed migrations before starting this update; readiness
requires both historical tables in addition to catalog/session tables. Downgrading0003 removes
history and preserves catalog/sessions, but readiness fails until the current schema returns.
For host-reachable DBs use scripts.import_candles; for private Docker DBs use the authenticated
dashboard. Only configure actual Analytics credentials locally; mock tests need none.

## P2-003C — option-chain research (2026-11-06)

Upgrade to revision0004_option_chain before updated app startup. Readiness checks chain
snapshot/leg tables. Configure credentials only through existing protected local setup. Host
CLI scripts.capture_option_chain requires host-reachable PostgreSQL; Docker's private DB uses
the dashboard. Current metadata plus explicit catalog expiry are required. Back up before
upgrade/downgrade;0004 downgrade deletes only chain data. No persistent deployment was started.

## P2-003D — V3 feed foundation (2026-11-06)

Sync the updated uv.lock before running:protobuf6.33.6 is a runtime dependency; generated
schema/classes ship under backend/vendor/upstox. types-protobuf is development-only; protoc
is not required at startup. Rebuild the Docker image to include decoder/runtime. No migration
is introduced; current required revision remains0004_option_chain. No automatic feed connection
or observation job starts. scripts.decode_feed requires the host's configured reachable DB.

## P2-003E — bounded feed lifecycle (2026-11-06)

Sync updated uv.lock; runtime websockets16.1.1 is added. Rebuild image for transport/lifecycle
modules. No migration; required revision remains0004_option_chain. No startup connection or
persistent feed service. Host scripts.stream_feed requires configured reachable DB, current
catalog and local server credential; max300seconds. stdout is not a durable observation store.
The loopback verification script requires openssl and cleans up its synthetic certificate.

## P2-003F — durable research observations (2026-11-06)

Required head is0005_observations. Apply alembic upgrade head before updated app; readiness
checks all three archive tables. Host stream_feed now records by default and needs configured
reachable DB/current catalog/local protected credential. No feed automatically starts. Back up
before downgrade;0005 deletes observations only. Recovery runs before a new CLI session and
marks expired leases without claiming an actual end time. No dependency changed this increment.

## P2-003G — calendar/coverage baseline (2026-11-06)

Ship backend/app/market_data/calendar_data with the image:reviewed policy, source manifest and
original evidence bytes. Loader verifies hashes locally; no runtime network refresh. Schema
remains0005_observations. Rebuild image for new modules/assets. Host observation_coverage CLI
needs reachable configured DB, not a broker token. PostgreSQL report uses read-only repeatable
read and bounded candidates/events/bytes. No new background process or frontend control.

## P2-003H — bounded supervision (2026-11-06)

Upgrade to0006_capture_runs before updated app/CLI; readiness checks parent table and child FK
column. Rebuild image. New host supervise_capture command requires configured reachable DB and
protected local credentials/current catalog. Defaults600s/3sessions/8MiB/20k events; hard maxima
documented in CAPTURE_SUPERVISION.md. No daemon installed. SIGINT/SIGTERM cooperative stop.
Downgrade drops grouping but preserves child observation data. No dependency changes.

## P2-003I — safe capture preflight (2026-11-06)

Use scripts.capture_preflight or supervise_capture --preflight-only before operator capture.
Blocked supervisor CLI exits2 before recovery or new records. Apply current head0006 separately;
preflight never migrates/creates tables. It requires PostgreSQL, current metadata and declared
credential lifetime covering budget+60s. Host CLI works for local DB-unavailable diagnostics;
HTTP needs existing admin auth. Actual local run found missing credential/unavailable DB.
No settings were written. See CAPTURE_PREFLIGHT.md.
