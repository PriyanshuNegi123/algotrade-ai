# Phase 2 acceptance and remaining gates

Baseline review 2026-11-09T14:18:10.573788+00:00 UTC;readiness update10November below.
**Phase 2 remains PARTIAL, not complete.**
The working read-only Analytics path is extensively verified. Completing a test suite does
not supply elapsed observation time. Bounded genuine market-hours evidence was verified
on 11 November; it does not establish continuous or seven-day coverage. Scoped OAuth
authentication/storage and the bounded endpoint check are complete; other gates remain.

## Requirements and evidence

| Requirement | Verified state | Remaining acceptance |
|---|---|---|
| Official API/app guidance | Analytics/auth/instrument/chain primary docs rechecked9November; registered OAuth settings configured locally10November | App configuration and operator consent do not certify account permissions or trading approval |
| Secure read-only authentication | Analytics history/chain/feed accepted; OAuth browser flow/vault deployed, genuine consent/storage accepted and one bounded NSE market-status check passed10November | Scoped OAuth authentication/storage acceptance complete; account permissions and grant scope are not certified; Analytics stays active and OAuth is not promoted |
| Instrument master | Immutable validated source/metadata; latest 6,744 selected / 85,180 source records, verified 11 November | Recheck currentness before each future capture; tick-size units unresolved |
| Historical candles | Immutable bounded prior-day imports;75real five-minute Nifty50 bars archived | Historical point-in-time universe/session completeness remains unverified |
| Option chain | Explicit expiry/catalog validation;135strikes/270legs accepted; unresolved unit context exposed on reads | No source timestamp per field; primary unit review remains inconclusive; no scaling inferred; freshness UNKNOWN |
| Feed and durable archive | Decoder, ordering, duplicates, timestamps, retries/heartbeat/TLS, quotas/recovery tested; 11 November controlled reconnect archived and gap verified | Bounded genuine market-hours acceptance passed 11 November: 27 recent-trade updates and 1,946 sampled ms; controlled genuine reconnect passed with two attempts and unchanged backoff; natural outages remain unverified |
| Cooperative stop | Genuine snapshot then exact-parent stop; parent/child CLOSED; socket1→0; archive hashes checked | Complete for the bounded9November acceptance |
| Calendar and sampled coverage | Pinned source integrity, holidays/special sessions, unknown states, conservative spans tested | Amendment completeness unverified; evidence-only, no day certifier implemented |
| Initial report | New bounded hash-validated report/CLI; actual report generated | It is an interim evidence report, not a completed seven-day analysis |
| Seven-calendar-day observation | One sampled market-hours date (11 November), 18 accepted samples / 2,253 ms across two Nifty captures; zero qualifying days | Actual available trading-session evidence and full window remain outstanding |
| Hosted CI | foundation/verify passed on0f2df43 | Report/storage/test work is committed locally; latest hosted CI for these additions remains unverified |
| Storage | PostgreSQL remains working transactional store; user selected Google Drive for backup/archive target | Desktop OAuth,encrypted backup and isolated restore verified; three-day schedule installed; passphrase-encrypted kit independently verified10November; operational DB remains PostgreSQL |

## Historical checks — 9 November

- Locked offline uv sync: passed with workspace cache.
- Full disposable PostgreSQL17.11 suite: **385 passed,0failed,0skipped**;cluster removed.
- Default suite: **361 passed,24PostgreSQL skips**, one warning.
- New report tests:10SQLite/security cases plus1native PostgreSQL case. They verify empty
  seven-date windows do not certify observation, source separation, read-only queries,
  corrupt-archive refusal, HTML/Markdown escaping, bounds and private container forwarding.
- Ruff lint/format:passed89files. Strict mypy:passed37backendfiles.
- Real loopback TLS/supervision:binary subscription, Protobuf ordering, ping/pong, close,
  redirect refusal, two durable synthetic children and quota/finalization checks passed.
- pip-audit: no known vulnerabilities found in installed locked dependencies.
- Isolated Docker smoke:configuration, image build, migration, non-root UID, authentication,
  app restart, database outage/recovery, CSRF/revocation, absent live routes passed.
  Only its generated test containers/volume were removed;operator runtime retained.
- One non-fatal upstream Starlette TestClient deprecation warning remains.

Hosted proof:[foundation run42630898094](https://github.com/PriyanshuNegi123/algotrade-ai/actions/runs/42630898094),
commit0f2df43c9950ec5cdc978c5b6ae5bab55214955f,verify job129206609937.
All pytest, lint/type, TLS, dependency audit and Compose steps completed successfully.
This resolves the earlier hosted PostgreSQL failure for that commit, not future changes.

## Initial observation report

`backend/app/market_data/initial_report.py` reuses existing bounded coverage transactions
and hash/schema validation. `scripts/initial_observation.py` renders Markdown or JSON.
No HTTP mutation route, database write, broker request, scheduler or automatic capture is added.
The host `--local` path uses the verified private Docker container without tokens in argv;
server execution does not depend on scripts being packaged in the image. Output is stdout;
there is no arbitrary file-write argument.

Example read-only invocation; replace the key/dates with your explicitly reviewed inputs:

```sh
uv run python -m scripts.initial_observation --local --from-date 2026-11-03 --to-date 2026-11-09 --instrument-key 'NSE_FO|61471'
```

NSE_FO|61471 was verified in the current catalog as NIFTY FUT23NOV26. It is a report
filter, not a trade selection/recommendation or claim of historical catalog membership.
The existing NSE_FO-only/max7dates/max20keys limits remain. Indices remain rejected.

Actual ignored exports: `reports/INITIAL_OBSERVATION.md` and
`reports/initial_observation_evidence.json`, protected mode0600. The UPSTOX_V3 report finds
zero matching derivative sessions/intervals and says NOT_CERTIFIED. Prior genuine archives
contain2index sessions/9events; they are not relabeled as derivative coverage.
All ten brief-required report sections exist; indicators/patterns/signals/P&L are explicitly
not implemented or not evaluated under the later-phase plan. No financial zeroes or results
are fabricated. This interpretation preserves phase order; the end-of-week analytical
report is not complete merely because its data-quality exporter exists.

## Next actions required for completion

1. Preserve the accepted OAuth callback, encrypted storage and quarantined endpoint-check
   boundaries. They are complete locally; ordinary grant scope remains uncertified and
   Analytics remains active. Never substitute the ordinary credential into Analytics.
2. Review calendar applicability, then use a current catalog and explicit supported contract
   during an eligible market session. Verify fresh updates, reconnects and honest sampled gaps.
   No automatic recording was installed; existing CLI has finite quotas.
3. Accumulate the required seven-calendar-day window using actual available sessions.
   Follow [OBSERVATION_PLAN.md](OBSERVATION_PLAN.md) for the sparse pilot, manual budgets and
   explicit commands. This does not establish full-session or completed seven-day coverage.
   Define/review any completion criteria before adding a certifier; current coverage always
   reports zero qualifying days. Time passing alone does not complete this requirement.
4. Resolve field-unit/calendar limitations using primary evidence and record their limits.
5. Review local changes;commit/push only when authorized,then verify CI on the new commit.

Registered OAuth fields and consent were supplied later and verified10November. Google
Drive remains a separate storage integration; it is not a substitute for broker OAuth.
See [STORAGE.md](STORAGE.md) for the storage decision.

Primary API sources rechecked9November:
[Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/),
[OAuth](https://upstox.com/developer/api-documentation/authentication/),
[instruments](https://upstox.com/developer/api-documentation/instruments/),
[option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/).
The instrument field descriptions inspected do not establish a currency unit conversion;
no conversion was inferred from numeric examples.

## Market-hours readiness update — 10 November

Added [MARKET_SESSION_CHECK.md](MARKET_SESSION_CHECK.md):a read-only,fail-closed check
that requires an eligible reviewed derivative session,whole requested window fit,current
local prerequisites and matching pinned calendar evidence. It never records or certifies.
Real runtime result BLOCKED due to CURRENT_CATALOG_REQUIRED and NO_REVIEWED_SESSION
(holiday in the reviewed baseline);capture/session/event counts unchanged.25new cases;
full disposable PostgreSQL503passed/0failed/0skipped,Ruff107files/format,mypy44backend
files passed. No new real market-hours/reconnect evidence or completed day was produced.

## Catalog refresh acceptance — 10 November

Existing public importer produced a new CURRENT_METADATA snapshot:6,744selected/85,462
source records. Publication9November23:57:32UTC equals10November05:27:32IST;no timezone
or freshness relaxation was needed. Raw checksum/normalized count verified and all prior
catalog/market archives preserved by before/after hashes. Readiness now reports only
NO_REVIEWED_SESSION (reviewed holiday),with no recording or certified day. Full disposable
PostgreSQL503passed/0failed/0skipped;Ruff107files/format,mypy44backendfiles passed.
Current metadata is a verification-time fact,recheck it on the next capture attempt.

## OAuth foundation — 10 November

See [UPSTOX_OAUTH.md](UPSTOX_OAUTH.md).46synthetic security cases verify the fixed official
protocol,one-use session-bound state,bounded secret-safe responses and optional settings.
No application route/browser consent/token storage or real account call is added. The
working Analytics credential is unchanged. Latest saved project.env check:NOT_CONFIGURED;
operator asked to save the three canonical variables locally. End-to-end OAuth remains
incomplete;this does not close P2-002 or any market-observation gate.

## Encrypted OAuth storage component — 10 November

[UPSTOX_OAUTH_VAULT.md](UPSTOX_OAUTH_VAULT.md) documents the new opt-in vault and33
synthetic security cases. No real token/key/store,HTTP route or deployment was initialized.
This completes the component implementation,not browser authorization or token-storage
acceptance for the real registered app. Active Analytics and all execution controls unchanged.

## Secure browser callback implementation — 10 November

[UPSTOX_OAUTH_BROWSER.md](UPSTOX_OAUTH_BROWSER.md):authenticated/Origin/CSRF start,Strict-
cookie original-tab finish,popup-specific nonce marker,anonymous static callback,query-log
scrubbing,session revocation checks and encrypted storage.33new pytest cases (including
2disposable PostgreSQL) plus fresh-profile Chrome synthetic cross-site proof. No real broker,
operator credential or operational DB used in tests. Default missing settings keep it disabled;
current private deployment/registered consent still pending. This does not close P2-002.

## 2026-11-11T06:09:56.516396+00:00 — P2-003U bounded genuine market-hours acceptance

Completed the scoped market-hours transport/archive acceptance on 11 November. Initial
readiness correctly blocked yesterday's catalog. Refreshed the fixed official public NSE
master: 6,744 selected / 85,180 source records; publication 10 November 23:54:36 UTC.
Old catalog hashes and existing candle/chain archives matched before/after. Fresh readiness
passed; official NSE timing row was rechecked and targeted amendment search found no
contradictory notice, without claiming exhaustive amendment completeness.

Two explicit sequential research-only captures, each capped at 20 seconds, one session,
200 events and 262,144 canonical bytes. No automatic loop or recording schedule. FINNIFTY
key NSE_FO|35050: 7 events / 4,107 bytes, STALE_TRADE, zero accepted coverage. One validated
read-only Nifty chain request for explicit 17 November expiry identified a reference near
reported spot; response not archived and receipt time not treated as quote certification.
Nifty key NSE_FO|45406: 30 events / 29,597 bytes, 27 RECENT_TRADE updates, five coverage-
accepted samples and 1,946 sampled milliseconds. These are diagnostic contracts, not signals.
Both broker market-info frames reported NSE_FO NORMAL_OPEN. Parent SESSION_LIMIT and child
DURATION_LIMIT; all closed with no active parent/child left. One attempt per run, no real
reconnect. Event hashes, sequences, quotas and current catalog lineage verified, including
paginated authenticated API reads; anonymous denied and CSRF logout succeeded.

Broker frame generation was sometimes ahead of local receipt by roughly 0.1 seconds.
Cause is unverified; no clock fault attributed to either side. Strict nonnegative frame/
trade age checks preserved. Coverage reports 24 unusable frames; no offset adjustment or
stored timestamp rewrite. Seven-date report (5–11 November): 37 events, one duplicate,
zero out-of-order/disconnect events, one sampled date, assessment NOT_CERTIFIED and zero
qualifying days. Short-run evidence is not continuous-session/seven-day certification.

Fresh locked sync, Ruff lint/format (122 files), mypy (50 source files) and full disposable
PostgreSQL 17.11 suite passed: 744 passed, zero failed/skipped, one existing nonfatal
Starlette warning. Temporary test cluster removed; automated tests did not use a real
account or the operational database. Acceptance used the existing operational read-only
broker path explicitly, separately from regression tests. No source/schema/configuration/
credential/security/scheduler changes. Protected .env/admin password fingerprints unchanged.
OBSERVATION, entries/live/execution disabled; Google backup and OAuth configuration untouched.

Private ignored receipts: .local/verification/catalog_refresh_20261111.json,
market_hours_20261111.json, market_hours_nifty_20261111.json, market_hours_api_20261111.json
and market_hours_week_report_20261111.json. Files changed: all eight agent-memory documents,
LOCAL_CAPTURE.md, MARKET_SESSION_CHECK.md, PHASE2_ACCEPTANCE.md, PROJECT_STATUS.md and
VERIFICATION.md. All 13 changed Markdown files passed default Gitleaks without allowances and private
configured-credential comparison; full history passed unchanged exact historical allowances.
Whitespace check passed. Local documentation commit only; no push. Latest hosted CI unverified.
Phase 2 remains partial. Next: read-only host/container time-offset diagnostics, then plan
and verify a bounded genuine reconnect in a fresh reviewed session with catalog/readiness
rechecked. Keep freshness gates unchanged. Seven-day evidence, calendar completeness and
physical unit clarification remain outstanding. No unattended recording authorized here.

## 2026-11-11T06:19:55.417924+00:00 — P2-003W controlled genuine reconnect and read-only time diagnostics

Read-only macOS SNTP probes: Apple offset +85.321 ms with +/-93.765 ms uncertainty;
Cloudflare +66.557 ms with +/-87.767 ms uncertainty (one address timed out before a
successful response). Neither estimate establishes a root cause. Five bracketed Docker
clock reads overlap host time; no demonstrated independent container drift. No clock,
NTP settings, timestamp values or acceptance thresholds changed. See CLOCK_DIAGNOSTICS.md.

One explicit genuine NSE_FO|45406 research capture: 80-second total/session caps, one child,
two maximum attempts, 250 events / 262,144 bytes. The private acceptance connector used
existing open_feed; its event sink scheduled one orderly close of only its owned first
socket after a stored recent-trade update. No fake frames/exceptions, network-wide fault,
container restart or reduced backoff. The ordinary runner emitted FEED_DISCONNECTED/BACKOFF,
waited 31.184 seconds, obtained a new authorization and restored market-info/snapshot/update.
This is controlled disconnect acceptance, not evidence of a natural broker outage.

Parent fc1f3773acc04976be6b6346f39ab45f and child 940242fc67cb4efd9d05d4468dc90bce
closed with SESSION_LIMIT / DURATION_LIMIT. Stored 82 events / 78,177 bytes; attempts had
1 and 68 RECENT_TRADE updates. API pagination verified hashes, sequences, quotas and both
current-catalog bindings. Anonymous access denied; CSRF logout passed. A 31.488-second
snapshot gap was not bridged by coverage; 13 accepted samples / 307 sampled ms, 58 unusable
frames. All active rows and established app HTTPS sockets returned to zero. Prior catalog,
candle/chain archives and protected configuration fingerprints remained unchanged.

Fresh sync, Ruff lint/format (122 files), mypy (50 source files), full disposable PostgreSQL
17.11 regression: 744 passed, zero failed/skipped, one existing Starlette warning. Cluster
removed; automated tests used no real account/operational DB. Operational acceptance was
separate and explicitly read-only. Seven-date report now has three sessions / 119 events,
six duplicates, zero out-of-order and one controlled disconnect; zero qualifying days,
NOT_CERTIFIED. Phase 2 stays partial; latest hosted CI, absolute clock cause, natural outage,
seven-day evidence, calendar completeness and physical unit conventions remain unverified.

No application source, schema, credentials, .env, OAuth/Google settings, scheduler or security
controls changed. OBSERVATION; entries/live/execution disabled. Local documentation commit
only, no push. All 14 changed Markdown files passed default Gitleaks without allowances
and configured-credential comparison; full history passed unchanged exact historical
allowances, and whitespace check passed. Private ignored receipts: clock_diagnostics_20261111.json, reconnect_20261111.json,
reconnect_api_20261111.json and reconnect_final_20261111.json under .local/verification/.
Next: prepare a bounded multi-day observation collection plan with storage budgets and
operator-invoked commands; continue independent time checks before longer collection.
Do not enable automatic recording, infer elapsed coverage or certify days from short runs.
