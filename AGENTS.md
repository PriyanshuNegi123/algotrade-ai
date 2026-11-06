# AlgoTrade AI — agent operating instructions

Read this file first, then `agent_memory/CURRENT_STATE.md`, `agent_memory/HANDOFF.md`,
and relevant tasks in `agent_memory/PENDING_TASKS.md`. Inspect git status and actual
source before changing anything. The user-provided source of requirements is
`docs/PROJECT_BRIEF.md`; preserve its phase order and all safety requirements.

## Current scope
Phase 1 is verified. The user authorized Phase 2: read-only broker/market-data integration.
Keep iterations scoped, tested and documented. Live execution is unavailable.
Default OBSERVATION mode; PAPER is a configuration label until its engine is implemented.
Never fabricate funds, market data, performance, approvals, test results or fills.
Broker secrets may be configured only through local environment/secret storage, never chat.

## Engineering rules
- Python 3.12, FastAPI, SQLAlchemy 2, Alembic and PostgreSQL; vanilla HTML/CSS/JS.
- Separate broker, strategy, research, risk and execution responsibilities.
- Keep execution fail-closed. No live route, order adapter or activation flag in Phase 2.
- Credentials remain server-side. Use official APIs and current primary documentation.
- Parameterized SQL, Argon2 passwords, opaque hashed sessions, origin and CSRF checks.
- No unsafe HTML insertion. No front-end balances or return guarantees invented for display.
- Scope each iteration to one clear task. Do not replace existing working code unnecessarily.
- Do not spawn concurrent agents unless the user explicitly requests delegation.

## Checks
`uv sync --locked` then `uv run pytest`, `uv run ruff check backend tests scripts`,
`uv run ruff format --check backend tests scripts`, `uv run mypy`.
Use `.venv/bin/` equivalents where uv cache permissions are restricted.
Never connect tests to a real trading account. PostgreSQL test requires a disposable database.

## Required handoff
After every iteration update current state, handoff, completed/pending tasks, decisions,
known issues, changelog and append session log. Record UTC time, objective, files,
actual tests/results, security implications, unfinished work, mode, live state and exact
next action. Update relevant docs. Do not claim production readiness or test success
without evidence. Use the final iteration summary format in the project brief.
