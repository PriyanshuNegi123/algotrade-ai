# Phase 2 acceptance and remaining gates

Reviewed 2026-11-09T14:18:10.573788+00:00 UTC. **Phase 2 remains PARTIAL, not complete.**
The working read-only Analytics path is extensively verified. Completing a test suite does
not supply genuine market-hours evidence, elapsed observation time or unconfigured OAuth.

## Requirements and evidence

| Requirement | Verified state | Remaining acceptance |
|---|---|---|
| Official API/app guidance | Analytics/auth/instrument/chain primary docs rechecked9November | Registered OAuth client ID/callback and locally stored secret still needed |
| Secure read-only authentication | Server-only Analytics token, aware cutoff, expiry/error/CSRF/origin tests; real history/chain/feed accepted | OAuth authorization/callback/token management unimplemented; no claim of completion |
| Instrument master | Immutable validated source/metadata; latest6,810 selected /84,868 source records | Recheck currentness before each future capture; tick-size units unresolved |
| Historical candles | Immutable bounded prior-day imports;75real five-minute Nifty50 bars archived | Historical point-in-time universe/session completeness remains unverified |
| Option chain | Explicit expiry/catalog validation;135strikes/270legs accepted | No source timestamp per field; Greek units unresolved; freshness UNKNOWN |
| Feed and durable archive | Decoder, ordering, duplicates, timestamps, retries/heartbeat/TLS, quotas/recovery tested | Fresh market-hours updates and real reconnect acceptance pending |
| Cooperative stop | Genuine snapshot then exact-parent stop; parent/child CLOSED; socket1→0; archive hashes checked | Complete for the bounded9November acceptance |
| Calendar and sampled coverage | Pinned source integrity, holidays/special sessions, unknown states, conservative spans tested | Amendment completeness unverified; evidence-only, no day certifier implemented |
| Initial report | New bounded hash-validated report/CLI; actual report generated | It is an interim evidence report, not a completed seven-day analysis |
| Seven-calendar-day observation | No qualifying interval/day claimed; genuine captures are closed-market stale snapshots | Actual available trading-session evidence and full window remain outstanding |
| Hosted CI | foundation/verify passed on0f2df43 | New uncommitted report code has local checks only; needs approved publication and a new CI run |
| Storage | PostgreSQL remains working transactional store; user selected Google Drive for backup/archive target | Desktop OAuth/synthetic round trip verified separately; manual encrypted backup/isolated restore verified; scheduling/key escrow pending |

## Checks executed this iteration

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

1. Supply only the public Upstox client ID and exact registered callback URL; configure the
   client secret locally. Implement and verify OAuth with one-use session-bound state,
   safe callback logging, correct cookie behavior and protected server-only token storage.
   Never paste secrets or replace the existing Analytics credential with an order-capable one.
2. Review calendar applicability, then use a current catalog and explicit supported contract
   during an eligible market session. Verify fresh updates, reconnects and honest sampled gaps.
   No automatic recording was installed; existing CLI has finite quotas.
3. Accumulate the required seven-calendar-day window using actual available sessions.
   Define/review any completion criteria before adding a certifier; current coverage always
   reports zero qualifying days. Time passing alone does not complete this requirement.
4. Resolve field-unit/calendar limitations using primary evidence and record their limits.
5. Review local changes;commit/push only when authorized,then verify CI on the new commit.

OAuth settings were requested; the user's reply specified Google Drive storage rather than
the requested OAuth settings, so those settings remain missing. No secret was requested.
See [STORAGE.md](STORAGE.md) for the storage decision.

Primary API sources rechecked9November:
[Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/),
[OAuth](https://upstox.com/developer/api-documentation/authentication/),
[instruments](https://upstox.com/developer/api-documentation/instruments/),
[option chain](https://upstox.com/developer/api-documentation/get-pc-option-chain/).
The instrument field descriptions inspected do not establish a currency unit conversion;
no conversion was inferred from numeric examples.
