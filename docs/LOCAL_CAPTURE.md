# Bounded recording in the private local Docker runtime

Keep Docker Desktop running. The local database is unpublished; use the wrapper below rather
than exposing PostgreSQL or changing the internal DATABASE_URL. Broker credentials remain in
the app container's protected server settings and are never supplied in command arguments.

Deploy the current reviewed image using the existing credential-preserving bootstrap:

```sh
uv run python -m scripts.bootstrap_local
```

Run read-only diagnostics first (no broker request or recording):

```sh
uv run python -m scripts.capture_local --instrument-key 'NSE_INDEX|Nifty 50' --preflight-only
```

Only an explicit command without `--preflight-only` starts a recording:

```sh
uv run python -m scripts.capture_local --instrument-key 'NSE_INDEX|Nifty 50' --total-seconds 20 --session-seconds 20 --max-sessions 1 --max-events 20 --max-payload-bytes 65536
```

Defaults match that short policy:20seconds,one child,20events,64KiB canonical payload.
Existing server policy bounds and preflight enforce supported keys/quotas. The child duration
is rounded down to fit remaining parent time, so a20second cap can produce a19second child.
Payload quotas cover canonical records, not database/index overhead. Re-run freshness checks
for future dates; a current catalog at one verification time is not permanently current.

The wrapper verifies a local Unix-socket Docker engine and a unique running app container
whose Compose working directory matches this repository. It sends only the trusted repository
supervisor CLI source over stdin; the Dockerfile does not need to package host scripts.
It validates inputs using the existing request/policy models, forwards diagnostic mode,
and returns the supervisor's safe JSON report. No remote hostname, URL or shell command input
is accepted. No source, credentials or settings are edited by the wrapper. The workspace
bootstrap lock serializes local wrapper/bootstrap operations; it is not distributed account
coordination or protection against unrelated external recorder processes.

Inspect the returned parent and child `status`, `reason`, event counts and payload bytes.
A command exit0 means a valid supervisor report was returned; a CHILD_FAILED report must
still be treated as a failed capture. Blocked preflight exits2 without creating records.
Raw subprocess errors and secrets are withheld. The host timeout includes cleanup grace;
in-flight database cleanup may extend the capture's data window. If the host client is
interrupted or disconnected, the remote bounded process may continue to its configured
limit. Inspect its persisted status and use the targeted stop command below. A client
interrupt is not a confirmed remote stop. Do not kill container processes or delete volumes.

Read records after dashboard login using the existing admin-only APIs:
`GET /api/observations/captures/{parent_id}` and
`GET /api/observations/sessions/{child_id}` (bounded pagination). No new capture-start HTTP
endpoint or UI control is introduced. Historical health is never current trading permission.
The coverage endpoint accepts reviewed NSE_FO keys only; an index request is intentionally
rejected. Do not bypass that restriction to claim an index observation day.

## Status and cooperative stop

List up to20capture summaries without starting recording:

```sh
uv run python -m scripts.capture_local --status
```

Use the exact32character capture ID returned by status. Replace the quoted placeholder:

```sh
uv run python -m scripts.capture_local --status --capture-id 'CAPTURE_ID'
uv run python -m scripts.capture_local --stop 'CAPTURE_ID'
```

Status and stop verify the local Docker engine/project directory but do not take the
recording/bootstrap lock,so they remain usable while the foreground recorder holds it.
Control commands never start capture or contact the broker. There is no HTTP stop route.

Stop persists a timestamp on only the requested active capture's existing stats ledger under
its row lock. Repeated requests preserve the first timestamp. Closed/expired captures are
not changed;unknown/malformed IDs fail closed. No PIDs,signals,process-name matches,ownership
changes or new DB grants are used. The supervisor checks for that timestamp during child
sessions and rollover waits at up to0.5second polling intervals,subject to DB latency.
It requests cooperative cancellation,drains the child,and records COOPERATIVE_STOP only
through the existing finalization path. Poll status until parent/children are CLOSED.
The initial response deliberately says final_state_verified:false;acceptance is not closure.
If the recorder is dead/unreachable,the request cannot manufacture a clean stop. Existing
lease interruption/recovery rules and finite runtime still apply. No automatic resume.

Implementation verification:367tests passed with disposable PostgreSQL,0failed/0skipped;
default344passed/23PGskipped. Synthetic active-child and rollover stop tests verify targeted
closure,repeat idempotence and no second subscription;PostgreSQL test verifies persistence.
Actual private-runtime status and stop on the existing closed genuine capture were nonmutating;
protected settings unchanged. A new active-broker stop run was not attempted because IST
midnight made the current catalog stale;preflight correctly returned CURRENT_CATALOG_REQUIRED.
Refresh/validate metadata before any future capture;do not bypass the date/freshness policy.
An initial default suite hit a pre-existing clock-sensitive coverage fixture near ISTmidnight;
its isolated rerun and final full suites passed. Deterministic fixture-clock work is now verified under P2-003S;see TEST_PLAN.md.
One upstream TestClient warning remains. Hosted GitHub Actions resolution is unconfirmed.

## Actual acceptance — 2026-11-06

One genuine Nifty50 recording ran18:19:48–18:20:07UTC. Parent
`3de3b096dbc947e0a91a9e95825ba68f` closed with SESSION_LIMIT; child
`8f64416c29ac40d28a9bb8fbfdb510b8` closed with DURATION_LIMIT. Stored6events:
PLAN1,MARKET_INFO1,SNAPSHOT1,IDLE3;3,527canonical bytes,within all configured caps.
The single observed index trade was STALE_TRADE and later idle health DELAYED_FRAME;
no fresh update or continuous market-hours coverage was asserted. Sampled interval0ms,
qualifying days0,global observation_started_at null. Entry/signal/execution/live flags false.

All event hashes, contiguous sequences and catalog-attempt linkage verified through private
reads. Anonymous access denied. Records and authenticated session survived an app restart;
CSRF logout succeeded. Existing credentials/settings unchanged; catalog/history/chain retained.
Preflight-only created no records. Reviewed calendar manifests now deployed; image and host
policy identity both `ee64ddfb593679cca9396b8646c61d458ce07147ea0c7f27c03b940eee3ed053`.
An initial verification expected coverage for an index, but received the intentional422;
verification was corrected to respect the existing derivatives-only boundary. No policy or
validation was relaxed. Safe aggregate evidence is in ignored reports/local_durable_capture.json.

Full disposable PostgreSQL regression356passed/zero skipped;default334passed/22PGskipped.
Eight new wrapper security cases passed;Ruff85files,mypy36backendfiles passed. One upstream
Starlette TestClient deprecation warning remains. Hosted GitHub Actions resolution is still
unconfirmed; the previous local348result precedes these8new cases. No commit/push or live
activation is implied by acceptance. Status/stop handling is implemented above;active broker-stop acceptance awaits a fresh catalog.

## 2026-11-09T14:05:58.802923+00:00 — P2-003R-A genuine active-broker stop acceptance COMPLETE

P2-003R-A verified on2026-11-09: current public catalog imported (6,810 selected records);
unchanged preflight passed. Genuine Nifty50 snapshot then exact-parent stop produced
CLOSED/COOPERATIVE_STOP and child CLOSED/CANCELLED. Stored3events/2,388bytes; hashes,
sequences, lineage, totals and private API access/logout verified. HTTPS socket1→0; no
active rows remain. Quote STALE_TRADE;0sampledms/0qualifying days. No credential/settings
or runtime-source change;OBSERVATION/live off. Fresh disposablePG374pass/0fail/0skip;
Ruff/format/mypy/sync pass,one upstream warning;hosted CI unconfirmed. No commit/push.
NextP2-003U: bounded genuine observation in a reviewed eligible market session; no scheduler
or short-run day certification. Full timestamps, IDs and evidence:latest docs/VERIFICATION.md.

Final checks: all11changed Markdown files passed default-rule Gitleaks without ignores; full-history scan passed existing exact allowances. Git whitespace check passed. No index changes, commit, push or history rewrite.

## Initial observation report

Read-only evidence export is now available through `scripts.initial_observation --local`.
It shares existing coverage bounds and does not record data or contact Upstox. See
[PHASE2_ACCEPTANCE.md](PHASE2_ACCEPTANCE.md) for the command, actual results and unfinished
gates. A seven-date request does not certify seven days; synthetic data stays separate.
