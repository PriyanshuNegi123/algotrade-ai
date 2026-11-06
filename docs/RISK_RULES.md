# Risk rules

Phase 1 enforces only the absolute execution boundary: no entries, no orders, no live mode.
The dashboard displays future default limits; the following financial controls are pending.

- Whole-lot sizing using current instrument master; funds, exposure, reservations and costs.
- Position stop trigger at 35% loss using actual average filled price and executable bid.
- Independent cycle account drawdown at 35%, cash-flow adjusted, requiring manual reactivation.
- Independent daily loss, exposure, position count/quantity, quote freshness/spread, cooldown,
  rate limits, consecutive-loss and end-of-day controls.
- Risk-reducing exits must confirm fills and reconcile remaining quantities.
- Unknown/stale data, missing lot sizes or insufficient budget mean NO_TRADE.
- No forced trades or guaranteed returns; no assumption of execution at the stop trigger.

Neither readiness nor a mode label constitutes risk authorization. No reference equity,
observation start date or funds are invented. Formal calculation/rounding rules and tests
must be implemented before paper execution and reused by a later live gate.
