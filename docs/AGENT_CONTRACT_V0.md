# Ananta ↔ Agent Ananta Contract v0

**Version:** `agent_api_version = 0`  
**Canonical copy also lives in:** `Rudhra6467/ananta-decision-agent` → `docs/AGENT_CONTRACT_V0.md`

## Rule

If Agent Ananta reasons on a fact, **Ananta must expose it** as structured truth. No hidden assumptions.

## Ownership

- **Ananta** owns: market data, portfolio, strategy state, orders, fills, exits, risk, telemetry, outcomes
- **Agent Ananta** owns: interpretation, ranking, decisions, explanation, evaluation, learning

## Minimum fields Agent expects

### portfolio_state
equity, cash, invested, open_positions / slots_used, unrealized_pnl, realized_pnl (if available)

### strategy_state
key, name, enabled, status_label

### market_state
symbol, price, change_24h, regime, regime_confidence (optional)

### cycle / decision (Agent-side ledgers)
cycle_id, action (TAKE|SKIP|HOLD|EXIT|REDUCE), strategy, confidence, reason

### trade / exit (when available)
symbol, side, quantity, price, exit_reason

## Decision vocabulary
TAKE · SKIP · HOLD · EXIT · REDUCE

## Co-design note

When adding APIs or enriching cycle/exit telemetry, prefer stable field names matching this contract so the Agent can consume them without scraping.
