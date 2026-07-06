# Ananta Platform Architecture — Destination Blueprint

> Vision: an **AI-native** cloud trading platform (research → validation → optimization → explainability
> → execution → marketplace). We build in phases but design for the destination so later phases are
> **expansions, not rewrites**. This doc is the shared source of truth for both Emergent workspaces.

## Layered model (design for the destination)
```
Strategy → Parameter Schema → Configuration → Validation → Execution → Performance DB → AI Learning Layer
```
- **Strategy** — pure logic, registered in a REGISTRY, VERSIONED (`hunter@1.0.0`), never overwritten.
- **Parameter Schema** — a strategy's self-description (params: type/range/default/grid/visibility/group + DNA).
  One param object drives: Research Lab form, optimizer search space, Beginner/Pro UI adaptivity, marketplace validation.
- **Configuration** — SPARSE overrides against a schema. Tenant-aware, VERSIONED, INHERITABLE
  (`parent_config_id`) so you never duplicate 100 params. Origin: builtin | user | marketplace | optimizer.
- **Validation** (Phase 3) — promotion gate: min trades / PF / drawdown / Sharpe / walk-forward /
  out-of-sample / confidence. A config cannot go live until `validation_status = passed`.
- **Execution** (Phase 2) — ExchangeAdapter interface (paper first, Coinbase Advanced next); idempotent
  order routing, retries, partial fills, reconciliation, audit log; strict paper/live isolation.
- **Performance DB** (Phase 4) — every live/paper trade stored (entry/exit/MFE/MAE/ATR/regime/volume/
  reasoning/result/exit-efficiency/hold-time). Becomes the training corpus.
- **AI Learning Layer** (Phase 4) — AI is an **analyst, not an autonomous trader**: reads the perf DB and
  proposes hypotheses ("Hunter loses most in low-volume reversals"; "ATR 1.75 > 2.5 for BTC") for the
  human to test. Keeps AI out of the money-moving loop.

## Roadmap (agreed)
- **Phase 1 (DONE):** Strategy Registry + Parameter Schema + Strategy Configs (versioned, tenant-aware,
  inheritance, DNA, rating/validation hooks).
- **Phase 2:** Research Lab reads schemas + edits configs; AI Optimization Engine (grid/random over
  `grid`/ranges → rank by PF/Sharpe/DD/stability → overfitting/confidence score).
- **Phase 3:** Validation Engine + Promotion gate + Config Ratings + strategy version control UI.
- **Phase 4:** Performance Database + AI Quant Analyst + Learning Engine.
- **Phase 5:** Marketplace (templates, copy trading, signals, user-created strategies) + Live exchange +
  Visual Strategy Builder (blocks emit a Config).

## Phase 1 implementation (this workspace, backend)
Package `/app/backend/strategy/`:
- `core.py` — `ParamSpec` / `StrategyDNA` / `StrategySchema`, `StrategyConfig` (tenant-aware, sparse,
  inheritable, versioned; `rating` + `validation_status` placeholders for Phase 3), REGISTRY (`register`/
  `get_schema`/`list_schemas`, versioned via `key@version`), `validate_params`, `resolve_config`
  (schema defaults ← parent chain root→leaf ← self; cycle-safe).
- `definitions.py` — built-in schemas + DNA for **hunter (v1.0.0)**, **squeeze (v1.0.0)**,
  **continuation (v1.0.0)**. Param ids map to real `RiskSettings` fields where `engine_backed=True`;
  a few forward-looking knobs (e.g. `time_exit_hours`) declared with `engine_backed=False`.

API (in `server.py`, `/api/strategy/*`, tenant = `"owner"` for now):
- `GET  /strategy/registry` — all strategies + DNA + schema (public).
- `GET  /strategy/{key}/schema?version=` (public).
- `GET  /strategy/configs?strategy_key=` — list (public read).
- `GET  /strategy/configs/{id}` — returns `{config, resolved_params}`.
- `POST /strategy/configs` (owner) — validates against schema; supports `parent_config_id`.
- `PUT  /strategy/configs/{id}` (owner) — validates; can set name/parent/rating/validation_status.
- `DELETE /strategy/configs/{id}` (owner) — blocks deleting builtins or configs that still have children.
- `POST /strategy/seed-defaults` (owner) — idempotent; creates one `builtin` Default per strategy (inheritance roots).

Mongo collection: `strategy_configs` (every row `tenant_id`-scoped). Tests: `tests/test_strategy_foundation.py`.

## Invariants to preserve as we expand
1. Strategy logic stays storage/tenant/exchange-agnostic (only reads a resolved config + market data).
2. Every persisted row is `tenant_id`-scoped from day one (single-tenant today, multi-tenant later, no migration).
3. Schemas are versioned and immutable; new behavior = new version, old versions remain switchable.
4. Configs are sparse + inheritable; the optimizer/marketplace/builder all just produce Configs.
5. Anything touching money carries a `mode: paper|live` discriminator and stays isolated.
