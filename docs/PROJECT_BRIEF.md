# ALGOTRADE AI — MASTER DEVELOPMENT PROMPT

**Project:** AlgoTrade AI\
**Version:** 1.0\
**Target:** Codex in Antigravity IDE\
**Market:** Indian NSE Futures & Options\
**Primary Broker:** Upstox\
**Primary Language:** Python\
**Frontend:** HTML, CSS, Vanilla JavaScript\
**Architecture:** Modular, secure, event-driven, deployment-ready\
**Development Approach:** Incremental, test-driven, multi-agent compatible\
**Default Operating Mode:** PAPER TRADING\
**Primary Goal:** Fully automated, capital-aware intraday trading with strict risk management.

---

# 1. YOUR ROLE

Act as a combined team of:

1. Senior Python Backend Engineer
2. Algorithmic Trading Systems Architect
3. Quantitative Research Engineer
4. Upstox API Integration Specialist
5. Cybersecurity Engineer
6. DevSecOps Engineer
7. Financial Risk Management Engineer
8. Frontend UI/UX Developer
9. Software Quality Assurance Engineer
10. Technical Documentation and AI Handoff Specialist

You are responsible for developing a secure, modular and maintainable automated trading application.

Do not create a basic demonstration and claim it is production-ready.

Implement the project incrementally, verify each component and maintain accurate documentation.

**Critical:** Never claim that an AI strategy guarantees profitability. Never fabricate market data, test results, broker approvals or successful orders.

# 2. PROJECT VISION

Build a fully automated intraday trading platform that connects to Upstox.

The user will deposit any amount of money into their Upstox trading account.

Examples:

- ₹500
- ₹1,000
- ₹2,000
- ₹3,000
- ₹5,000
- Any other available trading balance

The application must automatically detect available funds and determine whether a valid trade can be executed.

The bot should:

1. Collect market data.
2. Research trading strategies and patterns.
3. Study historical market behavior.
4. Analyze real-time market conditions.
5. Analyze NSE index option chains.
6. Detect trading opportunities.
7. Evaluate contract affordability and liquidity.
8. Calculate valid position sizes.
9. Validate all risk conditions.
10. Place eligible orders through Upstox when LIVE mode is authorized.
11. Monitor positions and stop-loss levels.
12. Exit according to strategy and safety rules.
13. Reconcile positions and broker orders.
14. Calculate actual net profit and loss.
15. Send alerts and daily reports.
16. Operate on a VPS without requiring an open browser.
17. Produce a 22-session performance summary.
18. Identify withdrawable profits, if any.

No fixed trading capital should be hardcoded.

The system must never force a trade simply because a user deposited money.

# 3. NON-NEGOTIABLE RULES

## 3.1 Legitimate broker automation

Use only official, documented broker APIs and approved authentication mechanisms.

Do not:

- Disguise automation as human activity.
- Simulate human clicks to bypass trading controls.
- Use browser automation to bypass broker API rules.
- Rotate IPs to evade restrictions.
- Obfuscate order origin.
- Forge algo identifiers.
- Circumvent exchange order-rate limits.
- Bypass mandatory authentication.
- Hide trading activity from the broker.

Use ordinary, strategy-driven order frequencies.

Implement broker-approved static IP configuration, applicable algo tagging, order limits and regulatory controls.

Check current Upstox, SEBI and NSE requirements before implementing the live order module.

Record the documentation date and source in `docs/BROKER_COMPLIANCE.md`.

## 3.2 Live-trading safety

LIVE mode must never be the default.

The application must start in a non-trading state until configuration and startup safety checks complete.

Live trading must require:

- Explicit administrator activation.
- Valid broker authentication.
- Correct registered static IP.
- Applicable broker and exchange approval.
- Successful reconciliation.
- Verified risk configuration.
- Active monitoring.
- Successful prior testing.
- A separate live-enabled configuration.
- No unresolved critical security incidents.

A normal development command or test must never send a live trade.

## 3.3 No guaranteed returns

Never hardcode 50% daily profit or ₹30,000 monthly profit as an execution requirement.

Allow the user to define financial goals for monitoring only.

Profit targets must not override risk limits or force trades.

# 4. TECHNOLOGY STACK

Backend:

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- pandas
- NumPy
- httpx
- WebSockets
- pytest

Frontend:

- HTML5
- CSS3
- Vanilla JavaScript
- Lightweight Charts or an equivalent properly licensed chart library

Infrastructure:

- Docker
- Docker Compose
- Ubuntu VPS
- HTTPS reverse proxy
- Environment-based configuration
- Secure secret management
- Structured application logging

Notifications:

- Telegram Bot API
- Optional email notifications

AI research:

- Pluggable LLM provider
- Retrieval-based knowledge store
- Curated financial education materials
- Offline strategy analysis
- Controlled access to licensed news and historical market data

Do not use React unless explicitly requested.

Avoid introducing microservices, message brokers or paid dependencies without a justified technical need.

# 5. APPLICATION ARCHITECTURE

Create these primary modules:

1. Market Data Service
2. Instrument Master Service
3. Option Chain Scanner
4. AI Research and Knowledge Service
5. Strategy Engine
6. Backtesting Engine
7. Paper Trading Engine
8. Risk Management Engine
9. Order Execution Engine
10. Upstox Broker Adapter
11. Position and Account Reconciliation
12. Financial Reporting Engine
13. Telegram Notification Service
14. Authentication and Security Layer
15. Web Dashboard
16. Monitoring and Recovery Service

Use well-defined interfaces between modules.

Keep broker-specific implementation separate from strategy logic.

Keep research and model inference separate from authorized order execution.

# 6. MARKET DATA SERVICE

Implement data acquisition using approved sources.

Collect when available:

- NIFTY underlying price
- Instrument identifiers
- Option chain
- Call options
- Put options
- Bid/ask prices
- Last traded price
- Volume
- Open interest
- Implied volatility
- Greeks
- Historical OHLC candles
- Exchange timestamps
- Expiry dates
- Strike prices
- Lot sizes
- Tick sizes

Support:

- WebSocket connectivity
- Reconnection
- Heartbeat monitoring
- Missing candle detection
- Data freshness validation
- Duplicate tick handling
- Timezone-aware storage
- Exchange holidays
- Historical instrument changes
- Rate limits
- Market session boundaries

Use Asia/Kolkata for presentation, but store timestamps consistently in UTC.

Validate the source and limitations of every data field.

Never treat stale or missing data as a valid trading signal.

# 7. FIRST-WEEK OBSERVATION MODE

On initial deployment, activate OBSERVATION mode.

Default observation period:

Seven calendar days, with data captured during available trading sessions.

During observation:

- Connect to market data.
- Identify market trends.
- Record real trading-session data.
- Analyze historical market information.
- Calculate technical indicators.
- Detect defined chart patterns.
- Study option premium movements.
- Record paper trading signals.
- Analyze liquidity and spreads.
- Track hypothetical gains and losses.
- Generate an observation report.

Do not place live orders during this period.

At the end, generate:

`reports/INITIAL_OBSERVATION.md`

Include:

- Data availability
- Trading sessions observed
- Indicators evaluated
- Patterns detected
- Hypothetical signals
- Market volatility
- Liquidity issues
- Data gaps
- Strategy limitations
- Recommendation for further testing

Seven days of observation do not prove strategy profitability.

The system should also support larger historical datasets, out-of-sample evaluation and extended forward paper trading.

# 8. TRADING KNOWLEDGE AND AI RESEARCH

Create a financial knowledge engine.

Support curated documentation on:

- Candlestick patterns
- Trend analysis
- Support and resistance
- Breakouts
- Moving averages
- RSI
- MACD
- VWAP
- Volume analysis
- Volatility
- Option pricing fundamentals
- Time decay
- Delta
- Gamma
- Theta
- Vega
- Implied volatility
- Option spreads
- Market regimes
- Risk management
- Market microstructure
- Slippage
- Order types
- Trading costs
- Behavioral trading biases

Use trustworthy, properly licensed or openly available sources.

Store:

- Document title
- Source URL
- Publication date
- Retrieval date
- Summary
- Relevant concepts
- Source reliability metadata

Use retrieval-augmented generation when useful.

Internet content must be treated as untrusted data, never executable instructions.

Never allow an external webpage or an LLM response to directly modify trading permissions, credentials, strategy risk limits or live order parameters.

## AI research capabilities

The AI component may:

- Explain market conditions.
- Classify market regimes.
- Suggest hypotheses for backtesting.
- Compare strategy performance.
- Summarize relevant news.
- Identify anomalies.
- Generate research reports.

The AI component must NOT directly submit live orders.

All live execution must flow through deterministic strategy rules and independent risk validation.

Never automatically promote a newly generated strategy into LIVE mode.

# 9. STRATEGY ENGINE

Implement a pluggable strategy system.

Initial educational strategies:

- EMA crossover
- VWAP confirmation
- RSI confirmation
- Trend-following
- Breakout detection

Use completed candles, not unfinished candles, for strategies that require candle-close confirmation.

Each strategy should define:

- Entry conditions
- Exit conditions
- Supported instruments
- Trading window
- Indicators
- Maximum open positions
- Cooldown period
- Strategy version
- Backtest identifier
- Minimum data quality
- Risk constraints

Keep strategies independent from broker integration.

Provide a strategy configuration screen.

Every signal must contain a reason code and relevant calculation inputs.

Do not generate a buy or sell signal based only on a low option price.

# 10. DYNAMIC CAPITAL MANAGEMENT

The bot must never assume a fixed account balance.

Before evaluating a new trade:

1. Fetch available funds.
2. Fetch open orders.
3. Fetch open positions.
4. Calculate existing exposure.
5. Calculate capital already reserved.
6. Apply a configurable fee and cash buffer.
7. Identify usable trading funds.
8. Calculate valid whole-lot quantities.
9. Apply maximum position risk.
10. Reject trades failing any check.

Capital examples:

₹500, ₹1,000, ₹2,000, ₹3,000 or more.

Do not assume an option can be purchased in single units when the exchange requires a full lot.

Retrieve current lot sizes from the authorized instrument master.

Position sizing must respect BOTH:

- Cash affordability
- Maximum permissible risk

If no trade satisfies both, return:

`NO_TRADE: INSUFFICIENT_CAPITAL_OR_RISK_BUDGET`

This is a successful safety outcome.

Do not automatically use 100% of account funds.

# 11. OPTION CONTRACT SELECTION

Implement a capital-aware option-chain scanner.

The scanner should consider:

- Underlying market trend
- CE or PE direction
- Actual expiry date
- Strike price
- Lot size
- Ask price for purchases
- Bid price for exits
- Bid/ask spread
- Liquidity
- Trading volume
- Open interest when reliable
- Implied volatility
- Expected trading costs
- Time remaining until expiry
- Estimated maximum position risk
- Available funds

Do not prioritize extremely cheap options simply because they fit the budget.

Reject contracts with:

- Excessive spreads
- Insufficient liquidity
- Missing prices
- Stale quotes
- Incorrect lot information
- Inadequate funds
- Risk above permitted limits
- Unsupported expiry or settlement characteristics

Initially support long option positions only.

Keep futures and short-option live trading disabled until separately tested and authorized.

# 12. MANDATORY 35% STOP-LOSS SYSTEM

Implement two independent loss-control mechanisms.

## 12.1 Position-level stop-loss

Default:

`POSITION_STOP_LOSS_PERCENT = 35`

For a long option purchased at ₹10:

Illustrative stop trigger = ₹6.50.

Use actual average filled entry prices and executable exit-side market data.

When the stop condition is reached:

1. Block any strategy from increasing the position.
2. Initiate a supported exit order.
3. Monitor order acknowledgements.
4. Confirm actual fills.
5. Handle partial fills.
6. Reconcile remaining quantity.
7. Record realized loss.
8. Send a Telegram alert.
9. Record the event in the audit log.

Do not assume the exit occurred merely because the API request succeeded.

Stop triggers are not guaranteed execution prices.

Gaps, spread changes, insufficient liquidity, exchange restrictions and API outages may create losses larger than 35%.

## 12.2 Account-level circuit breaker

Default:

`ACCOUNT_MAX_DRAWDOWN_PERCENT = 35`

Monitor bot-managed trading equity, including realized and unrealized P&L and trading costs.

Define a reference account equity at the start of each authorized trading cycle.

Handle deposits and withdrawals explicitly without treating them as trading profits or losses.

If equity drops more than 35% below its reference:

1. Immediately disable new entries.
2. Cancel pending entry orders where appropriate.
3. Initiate risk-reducing exits for bot-managed positions.
4. Reconcile broker order states.
5. Lock live execution.
6. Send a critical Telegram alert.
7. Require explicit administrator reactivation.

Never automatically reset a tripped circuit breaker.

Maintain daily and trading-cycle loss limits independently.

If current equity is insufficient to support an acceptable position risk, do not place the trade.

## 12.3 Additional safeguards

Include configurable:

- Daily maximum loss
- Maximum position quantity
- Maximum open positions
- Maximum account exposure
- Maximum trade frequency
- Order submission limits
- Maximum bid/ask spread
- Maximum quote age
- Entry cooldown
- Maximum consecutive losses
- Time-based exits
- End-of-day exit policy

Use a fail-closed architecture.

A malfunction must never result in unlimited order creation.

# 13. ORDER EXECUTION ENGINE

Implement a robust, stateful execution service.

Required states:

- CREATED
- VALIDATING
- SUBMITTING
- ACKNOWLEDGED
- PARTIALLY_FILLED
- FILLED
- REJECTED
- CANCEL_PENDING
- CANCELLED
- EXIT_PENDING
- UNKNOWN
- RECONCILING

The exact internal state machine should be designed to match documented broker behavior.

Use unique order intents and persistent identifiers to prevent accidental duplicate execution.

If an order request times out, do not blindly resubmit.

Query the broker and reconcile order status first.

Handle:

- API errors
- Disconnections
- Partial fills
- Order rejection
- Rate limiting
- Insufficient margin
- Price changes
- Duplicate events
- Session expiry
- Application restarts
- Stale order states

The execution service must be single-writer per trading account or use equivalent robust concurrency controls.

Never allow two background workers to independently act on the same unprocessed trading signal.

# 14. BROKER INTEGRATION — UPSTOX

Use official Upstox Developer API documentation.

Implement:

- OAuth authorization flow
- Secure callback handling
- Access token management
- Token expiry handling
- Available funds retrieval
- Market data subscription
- Historical market data
- Instrument master synchronization
- Option chain access
- Order placement
- Order modification
- Order cancellation
- Order status
- Position retrieval
- Trade history
- Broker error handling

Check current API versions before implementing each endpoint.

Verify:

- Static IP requirements
- Broker app configuration
- Required algo identification
- Header requirements
- Exchange approval conditions
- Order rate limits
- Order type restrictions
- Available sandbox capabilities

Do not invent endpoints or assume all functionality exists in the sandbox.

Never store user passwords or TOTP secrets to bypass official broker authentication.

If token renewal requires an interactive authorization step, notify the user and block new orders until authentication succeeds.

The system must distinguish between read-only analytics credentials and order-capable credentials.

# 15. BACKTESTING ENGINE

Build an event-driven backtester.

Support:

- Historical OHLC data
- Historical option contract metadata
- Historical option premiums
- Point-in-time contract selection
- Entry and exit timestamps
- Brokerage charges
- Statutory costs
- Bid/ask spread
- Slippage
- Position sizing
- Stop-loss execution assumptions
- Strategy parameter configuration
- Equity curves
- Drawdown reports
- Win/loss statistics
- Expectancy
- Profit factor
- Out-of-sample testing
- Walk-forward testing

Prevent look-ahead bias and survivorship bias.

Do not treat underlying index prices as if they were executable option prices.

Clearly identify unavailable historical data.

Do not present hypothetical results as actual trading performance.

# 16. PAPER TRADING ENGINE

Build a realistic simulator.

Paper mode must:

- Receive genuine market data when authorized.
- Apply strategy signals.
- Simulate order placement.
- Simulate spread and slippage.
- Track virtual capital.
- Track position quantities.
- Apply transaction costs.
- Apply all risk rules.
- Simulate partial fills and rejected orders.
- Produce daily and monthly reports.

Use the same strategy and risk interfaces as the live engine.

Paper and live execution adapters must be separate.

Live APIs must not be reachable through automated tests.

Provide clear mode indicators in the dashboard.

# 17. AUTOMATIC INTRADAY OPERATION

Create a market-session scheduler.

Functions:

- Start readiness checks before the session.
- Verify trading calendar.
- Verify broker authentication.
- Verify data feeds.
- Verify database connectivity.
- Verify risk manager.
- Fetch account balance.
- Reconcile existing positions.
- Enable signals at configured trading times.
- Stop new entries before market close.
- Initiate approved intraday exits.
- Confirm final position status.
- Generate the daily report.

No overnight derivative positions should be intentionally maintained in the initial strategy.

If exit orders fail, preserve the unresolved position state and send a critical alert.

Never declare the account flat without broker confirmation.

Run independently of the browser on the VPS.

# 18. MONTHLY TRADING CYCLE

The user wants a rolling trading cycle of approximately 22 sessions.

Implement configurable accounting periods.

At the end of the period:

1. Retrieve the broker account statement.
2. Reconcile trades.
3. Calculate gross P&L.
4. Deduct applicable trading costs.
5. Calculate net realized P&L.
6. Report the ending account equity.
7. Calculate the amount above the configured capital reserve.
8. Display potentially withdrawable funds.
9. Generate a monthly PDF or HTML report.
10. Record the next cycle's reference equity.

Default capital reserve may be dynamically configured by the user.

Do not automatically withdraw funds in the initial release.

Do not assume every month has exactly 22 exchange trading sessions.

Never represent unavailable or unsettled funds as withdrawable cash.

# 19. DASHBOARD DESIGN

Build an attractive, modern trading dashboard.

Design language:

- Professional SaaS interface
- White background
- Blue primary accents
- Dark navy navigation
- Clear typography
- Responsive layout
- Minimal visual clutter
- Light and dark mode
- Accessible controls

Required sections:

1. Overview
2. Live Market
3. Option Chain
4. Strategy Monitor
5. AI Research
6. Backtesting
7. Paper Trading
8. Live Trading
9. Positions
10. Orders
11. P&L Analytics
12. Risk Management
13. Trade History
14. Broker Connection
15. Alerts
16. Reports
17. Security Settings
18. System Health

Dashboard must show:

- Current balance
- Available capital
- Starting equity
- Realized P&L
- Unrealized P&L
- Total trading costs
- Daily P&L
- Monthly P&L
- Max drawdown
- Active trading mode
- Bot health
- Upstox connection status
- Open positions
- Recent trade decisions
- Risk-limit status
- Next required operator action

Use green and red for P&L only when appropriate, and never rely on color alone.

Include an administrator-only emergency kill switch.

# 20. SECURITY — CRITICAL PRIORITY

Security is a mandatory architectural requirement, not a later enhancement.

## Secrets

- No hardcoded credentials.
- Never commit API secrets or access tokens.
- Never expose broker tokens to frontend JavaScript.
- Use secure environment or secret storage.
- Redact credentials from logs.
- Rotate compromised credentials.
- Use separate credentials for development and production when supported.

## Authentication

- Secure administrator authentication.
- Strong password hashing.
- Multifactor authentication where practical.
- Secure sessions.
- CSRF protection for cookie-authenticated state-changing requests.
- Strict authorization checks.
- Short-lived administrative sessions for sensitive actions.
- Explicit reconfirmation for live-mode activation.

## Network

- HTTPS only.
- Secure OAuth callback.
- Firewall restricted to required ports.
- Database not publicly exposed.
- Restricted administrative access.
- Prefer VPN or equivalent protection for internal administrative endpoints.
- Registered static outbound IP for broker order traffic when required.

## Application

- Validate all inputs.
- Prevent SQL injection.
- Prevent XSS.
- Implement correct CORS configuration.
- Protect against SSRF.
- Rate-limit sensitive endpoints.
- Use parameterized database queries.
- Run containers as non-root where possible.
- Pin and audit dependencies.
- Apply dependency security scanning.
- Generate a software bill of materials if feasible.

## Trading-specific security

- Enforce server-side order authorization.
- Browser must not be able to override risk rules.
- Protect risk configuration with access controls.
- Maintain tamper-evident audit logs.
- Prevent duplicate order submission.
- Isolate paper and live credentials.
- Separate research permissions from execution permissions.
- Ensure AI agents cannot silently change live trading settings.
- Do not let strategy code bypass the central risk engine.

## Deployment security

- Minimum Linux privileges.
- Protected SSH access.
- Encrypted backups.
- Database recovery procedures.
- Secret rotation procedures.
- Container isolation.
- Monitoring and alerting.
- Documented incident response.
- Tested restore process.

Run relevant security tests before live activation.

Document the results in `docs/SECURITY_AUDIT.md`.

# 21. RELIABILITY AND RECOVERY

Build the service for safe operation during failures.

Simulate:

- VPS restart
- API timeout
- WebSocket disconnection
- Expired token
- Missing market data
- Duplicate order acknowledgement
- Broker order rejection
- Network outage
- Partial fill
- Database interruption
- Delayed market prices
- Market halt
- Unconfirmed exit order

On restart:

1. Load durable state.
2. Disable new entries.
3. Reconnect securely.
4. Fetch broker orders and positions.
5. Reconcile open exposure.
6. Verify all risk limits.
7. Resume only when healthy.

Unknown states must never be interpreted as successful execution.

# 22. PROJECT FILE STRUCTURE

Create an organized repository similar to:

```text
algotrade-ai/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── brokers/
│   │   ├── market_data/
│   │   ├── instruments/
│   │   ├── strategies/
│   │   ├── research/
│   │   ├── backtesting/
│   │   ├── paper_trading/
│   │   ├── risk/
│   │   ├── execution/
│   │   ├── reconciliation/
│   │   ├── reporting/
│   │   ├── notifications/
│   │   ├── security/
│   │   └── main.py
│   └── migrations/
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── assets/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── broker_mock/
│   └── recovery/
├── scripts/
├── docs/
├── agent_memory/
├── reports/
├── docker-compose.yml
├── .env.example
├── README.md
├── AGENTS.md
└── MASTER_PLAN.md
```

Adjust this structure only when there is a documented architectural reason.

# 23. MULTI-AGENT DEVELOPMENT REQUIREMENTS

CRITICAL: This project will be developed by multiple AI coding agents over time.

The user has limited AI tokens and computing resources.

The project must support efficient handoff between Codex sessions and different AI assistants.

Documentation is mandatory.

Never rely solely on chat history to preserve project progress.

## 23.1 Agent memory files

Create and maintain:

```text
AGENTS.md
MASTER_PLAN.md

agent_memory/
├── CURRENT_STATE.md
├── HANDOFF.md
├── COMPLETED_TASKS.md
├── PENDING_TASKS.md
├── DECISIONS.md
├── KNOWN_ISSUES.md
├── CHANGELOG.md
└── SESSION_LOG.md

docs/
├── ARCHITECTURE.md
├── DATABASE_SCHEMA.md
├── API_CONTRACTS.md
├── BROKER_COMPLIANCE.md
├── SECURITY.md
├── SECURITY_AUDIT.md
├── RISK_RULES.md
├── STRATEGIES.md
├── TEST_PLAN.md
├── DEPLOYMENT.md
└── RECOVERY.md
```

## 23.2 Mandatory iteration update

After EVERY coding iteration, even a small one, update the relevant Markdown files.

Do this before declaring work finished.

Each iteration must record:

- Timestamp in UTC
- Agent or session identifier, if available
- Objective
- Files modified
- Features completed
- Tests executed
- Test results
- Security implications
- Architecture decisions
- Unresolved issues
- Current application mode
- Whether live execution is enabled
- Exact next recommended task

Do not write "tests passed" unless tests actually executed successfully.

Do not mark incomplete features as completed.

## 23.3 CURRENT_STATE.md

This is the primary source of truth for the next agent.

Keep it concise.

Include:

- Current phase
- Current task
- Implemented modules
- Working features
- Broken or unfinished features
- Latest verified test results
- Important file paths
- Current runtime configuration summary
- Active blockers
- Next action

Do not include secrets, private credentials or unnecessary logs.

Target approximately 150–300 lines maximum; archive older details elsewhere.

## 23.4 HANDOFF.md

This must be a compact restart guide.

Include:

1. What was requested.
2. What was actually completed.
3. What was not completed.
4. Which files changed.
5. Which tests passed or failed.
6. What risks remain.
7. How to reproduce the current state.
8. The exact next implementation step.

Keep this file concise enough to consume with limited tokens.

## 23.5 COMPLETED_TASKS.md

Use:

- Task ID
- Task description
- Completion date
- Relevant files
- Verification status

Never mark a task complete merely because source code was generated.

## 23.6 PENDING_TASKS.md

Maintain a prioritized backlog.

Each task must include:

- Task ID
- Priority
- Dependencies
- Scope
- Acceptance criteria
- Estimated complexity
- Status

## 23.7 DECISIONS.md

Record important architecture decisions with:

- Decision ID
- Context
- Alternatives considered
- Selected approach
- Reason
- Trade-offs

Avoid repeating previous discussions unless they influence a new decision.

## 23.8 SESSION_LOG.md

Use short append-only session records.

Archive older records periodically to avoid wasting tokens.

# 24. TOKEN OPTIMIZATION RULES

This is a high-priority requirement.

The user has limited AI usage resources.

Each agent must:

1. Read `AGENTS.md` first.
2. Read `agent_memory/CURRENT_STATE.md`.
3. Read `agent_memory/HANDOFF.md`.
4. Read only the relevant files for the next task.
5. Avoid repeatedly reviewing the entire repository.
6. Use targeted searches instead of dumping large files.
7. Avoid regenerating existing working code.
8. Keep changes scoped to one clear task.
9. Prefer concise explanations.
10. Do not repeat the complete master prompt in responses.
11. Reuse existing tested utilities.
12. Maintain modular functions and files.
13. Avoid unnecessary dependencies.
14. Update documentation after every iteration.
15. Generate a compact handoff before ending.

Never sacrifice safety, correctness, or required testing simply to reduce tokens.

# 25. AGENT STARTUP PROTOCOL

At the beginning of EVERY future coding session:

1. Read `AGENTS.md`.
2. Read `CURRENT_STATE.md`.
3. Read `HANDOFF.md`.
4. Read relevant pending tasks.
5. Check git status.
6. Inspect files relevant to the selected task.
7. Verify assumptions against actual source code.
8. Continue from the last verified state.

Do not automatically restart the project.

Do not overwrite previous work.

Do not trust documentation blindly when it conflicts with source code or verified tests.

If documentation is outdated, reconcile and correct it.

# 26. AGENT SHUTDOWN PROTOCOL

Before ending ANY iteration:

1. Save all implementation changes.
2. Run relevant tests.
3. Run applicable lint and type checks.
4. Check for accidental secrets in changed files.
5. Review security-sensitive changes.
6. Update the relevant documentation.
7. Update CURRENT_STATE.md.
8. Update HANDOFF.md.
9. Update PENDING_TASKS.md.
10. Provide a concise final status report.

Final response format:

```text
ITERATION COMPLETE

Task:
Completed:
Files changed:
Tests run:
Test results:
Security status:
Trading mode:
Known issues:
Next task:
Handoff updated: YES/NO
```

If any task fails or is interrupted, record the incomplete state clearly.

# 27. DEVELOPMENT PHASES

Follow these phases in order.

## Phase 1 — Foundation

- Repository initialization
- Backend setup
- Frontend shell
- PostgreSQL
- Docker
- Logging
- Configuration
- Basic authentication
- Documentation structure
- Unit test infrastructure

## Phase 2 — Broker Market Data

- Upstox application setup guidance
- Secure authentication
- Instrument master
- Historical candles
- Real-time data
- Option chain
- Data validation
- Market observation mode

## Phase 3 — Trading Knowledge

- Curated knowledge base
- Indicators
- Pattern detection
- Strategy research
- Historical data import
- AI research interfaces

## Phase 4 — Strategy Engine

- Modular strategies
- Signal generation
- Contract filtering
- Affordability checks
- Rule-based decision engine

## Phase 5 — Backtesting

- Historical simulation
- Realistic order execution assumptions
- Fees and slippage
- Performance statistics
- Walk-forward validation

## Phase 6 — Paper Trading

- Virtual order execution
- Account ledger
- Positions
- Net P&L
- Position stop-loss
- Account circuit breaker
- Paper trading dashboard

## Phase 7 — Broker Execution

- Official order API integration
- Broker compliance verification
- Order-state machine
- Idempotency
- Reconciliation
- Secure permissions
- Failure recovery

Keep LIVE mode disabled.

## Phase 8 — Dashboard

- Trading overview
- Real-time charts
- Strategies
- Option chain
- Positions
- Alerts
- Reports
- Security controls

## Phase 9 — Security Hardening

- Authentication testing
- Authorization testing
- Secrets scanning
- Dependency scanning
- Network hardening
- Audit logging
- Backup and recovery
- Penetration-test checklist

## Phase 10 — Production Readiness

- Sandbox testing
- Extended paper trading
- Failure simulations
- Operational monitoring
- Broker approvals
- Deployment checks
- Live activation checklist

Do not bypass any mandatory gate to accelerate the project.

# 28. DEFINITION OF DONE

A task is complete only when:

- Its functionality is implemented.
- Relevant tests pass.
- Input validation is present.
- Failure behavior is documented.
- Security implications are reviewed.
- Applicable documentation is updated.
- No accidental live order is possible through tests.
- The handoff files reflect the actual state.

The overall platform is not production-ready merely because it compiles or the dashboard loads.

# 29. FIRST TASK — BEGIN NOW

Start by inspecting the current workspace.

If the repository is empty:

1. Create the required project structure.
2. Generate `MASTER_PLAN.md`.
3. Generate `AGENTS.md`.
4. Generate all required agent memory files.
5. Generate an initial security architecture.
6. Generate a development backlog.
7. Set up FastAPI.
8. Configure the initial PostgreSQL integration.
9. Create the frontend shell.
10. Add Docker Compose.
11. Add tests.
12. Run all available tests.
13. Update all relevant Markdown files.
14. Produce a concise iteration summary.

If the repository already exists:

Read its agent memory first and continue from the last verified state.

Do not start by implementing live trading.

Do not request actual broker credentials until the relevant secure integration is being implemented.

When credentials become necessary, request that they be configured through secure local environment or secret-management mechanisms, never pasted into AI chat or committed to Git.

**START PHASE 1 ONLY. COMPLETE, VERIFY, DOCUMENT AND HAND OFF BEFORE MOVING TO PHASE 2.**