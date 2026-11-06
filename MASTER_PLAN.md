# Master plan

The authoritative specification is [PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md).

| Phase | Scope | State / gate |
|---|---|---|
| 1 | Foundation, PostgreSQL, authentication, frontend shell, Docker, checks, documentation | Complete: native PostgreSQL, image build and Docker auth/restart/outage smoke verified |
| 2 | Official read-only broker OAuth, instruments, candles, quotes, observation | Started: API review, read-only probe and versioned index metadata and historical-minute ingestion and synthetic option-chain snapshots verified; V3 authorization/decoder foundation verified; bounded socket lifecycle verified with mocks/local TLS; durable bounded recording verified; calendar baseline and bounded sampled-coverage reports verified; bounded multi-session supervision verified; safe operator preflight verified; persistent local bootstrap and real public catalog onboarding verified; real one-day history acceptance verified; one real option-chain snapshot verified; basic closed-market feed acceptance verified; durable broker recording/fresh-session coverage/completed-day certification/OAuth pending |
| 3 | Curated knowledge, indicators, controlled research | Not started |
| 4 | Deterministic strategies, contract filters, affordability | Not started |
| 5 | Event-driven backtests, historical options, costs, walk-forward | Not started |
| 6 | Paper ledger, fills, risk controls, net reporting | Not started |
| 7 | Broker execution, compliance, reconciliation, recovery | Not started; LIVE still disabled |
| 8 | Full operational dashboard and reports | Not started; Phase 1 contains shell only |
| 9 | Security hardening, audits, backup restore | Not started |
| 10 | Extended paper testing, approvals, production readiness | Not started |

No phase completion grants live authorization. Current release cannot place an order.
Seven calendar days of observation begin only when genuine data capture is implemented.
No automatic withdrawals, no short options, no futures execution in the initial release.
