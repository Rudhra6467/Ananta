# Ananta ↔ Agent Ananta Contract v0

**Version:** `agent_api_version = 0`  
**Updated:** 2026-08-20  
**Canonical copy also lives in:** `Rudhra6467/ananta-decision-agent` → `docs/AGENT_CONTRACT_V0.md`

## Rule

If Agent Ananta reasons on a fact, **Ananta must expose it** as structured truth. No hidden assumptions.

The **backend** is the contract host. The UI is one client. Agent Ananta is another. Hosting provider is irrelevant.

## Ownership

- **Ananta** owns: market data, portfolio, strategy state, orders, fills, exits, risk, telemetry, outcomes
- **Agent Ananta** owns: interpretation, ranking, decisions, explanation, evaluation, learning

Agent must never become a second hidden trading engine. Agent must never write Mongo as its architecture.

## HTTP surface Agent Ananta calls (v0)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/login` | Owner JWT `{email,password}` → `{token,email,role}` |
| `GET` | `/api/portfolio` | equity, cash, positions, `slots_used`, realized_pnl |
| `POST` | `/api/orders/manual` | Paper BUY/SELL |
| `GET` | `/api/trades` | Fills / history |
| `GET` | `/api/strategy/registry` | Strategy keys + names |
| `GET`/`PUT` | `/api/strategy/{key}/profile` | Enable/disable + regimes |
| `POST` | `/api/cycle/run` | Evaluation cycle (`/{symbol}` optional) |
| `GET` | `/health` | Liveness (no `/api`, no DB) |

There is no `/api/orders/paper`. Paper is the default execution environment; manual orders in paper mode are the agent’s execution path.

Auth is required. Do not add an unauthenticated write path for the agent.

How to run this API without the website: [LOCAL_BACKEND.md](./LOCAL_BACKEND.md).

## Minimum fields Agent expects

### portfolio_state
equity, cash, invested (`positions_value`), open_positions / slots_used, unrealized_pnl, realized_pnl (if available)

### strategy_state
key, name, enabled, status_label

### market_state
symbol, price, change_24h, regime, regime_confidence (optional)

### cycle / decision (Agent-side ledgers today)
cycle_id, action (TAKE|SKIP|HOLD|EXIT|REDUCE), strategy, confidence, reason

### trade / exit (when available)
symbol, side, quantity, price, exit_reason

## Decision vocabulary
TAKE · SKIP · HOLD · EXIT · REDUCE

## Co-design note

When adding APIs or enriching cycle/exit telemetry, prefer stable field names matching this contract so the Agent can consume them without scraping.

If a ledger needs to live in Ananta later, expose it as an API. Do not invite the agent to become a database client.
