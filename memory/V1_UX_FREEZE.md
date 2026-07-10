# ANANTA v1 UI/UX FREEZE — Master Specification (source of truth)

> **MANDATE:** This document defines the production-ready v1. Nothing here is optional.
> Preserve ALL existing backend functionality. Refactor only frontend, navigation,
> interaction, and the minimal backend surface noted below. If a requirement conflicts
> with current implementation, implement the requirement UNLESS it breaks trading safety
> or business logic. Mobile-first spatial redesign; **feature parity on web** (web keeps its
> desktop grid but gets every feature + renames + copy cleanup + light density).
> After v1: freeze layout, shift to strategy quality / execution / reliability / testing.

## LOCKED DECISIONS (2026-07-09)
1. Web = full FEATURE parity; layout stays desktop-grid (no web re-architecture). Mobile = full spatial redesign.
2. Ask Ananta = FULL version (Q&A + context-aware + action-executor). Owner **feature toggle in Workspace** (off until launch). LLM only called on user send. Every mutating action → explicit confirmation modal.
3. Trading Wizard reuses existing backtest + arm-to-PAPER; no net-new engine.
4. Manual Order = real paper order (NET-NEW endpoint) + Active-Strategies toggle grid + sticky bottom AI Coach + Add Strategies.
5. "+" menu routes to EXISTING flows (Import JSON / Manual Builder / AI Wizard=Architect).
6. Spot-only (hide futures in AI strategy schema).

## GLOBAL DESIGN RULES
- 8pt spacing scale: section 24 · cards 16 · title→content 12 · controls 8 · related labels 4. No arbitrary 30-40px gaps.
- Reduce vertical padding ~20-35% between stacked components.
- Delete decorative eyebrow copy when the title already says it (e.g. "HOW IS ANANTA SET UP?", "POSITION MODIFIERS", "SWITCH THE LENS…", "Which engine do you want to validate?").
- Increase density WITHOUT shrinking charts, legend text, buttons, or touch targets (≥44px).
- Action-first: "What can I do?" at top, analytics below.
- Feel: TradingView clarity + Bloomberg density + Linear spacing/typography + Apple HIG motion.

## BACKEND AUDIT (Phase 0)
- EXISTS: `PUT /strategy/{key}/state` (toggles), `trading_mode` + `POST /cycle/run[/{sym}]`, backtest (declarative + Lab), `ai_analyst.answer_question(db, session_id, q, strategy)`, coach endpoints, per-strategy configs, library/import.
- NET-NEW: (a) `POST /api/orders/manual` paper buy/sell (market/limit) reusing `_execute_buy`/sizing; (b) Ask Ananta: context-aware prompt + intent/action layer + `ask_ananta_enabled` setting; (c) list of "running strategies" for the toggle grid (derive from strategy_meta enabled + registry).

## NAVIGATION PHILOSOPHY (one question per tab)
Cockpit = "What is happening?" · Trade = "What should I do?" · Strategy = "What do I own?" · Research = "Does it work?" · Workspace = "How is my system configured?"

---
## TAB-WISE CHANGES

### COCKPIT ("What is happening?")
- Remove large whitespace above metrics; reduce card padding + vertical margins.
- Metric reflow into 2 cols following generation→filter→qualified flow:
  - LEFT: Setups, Rejected · RIGHT: Scanned, Qualified (+ Regime line).
- **Start Trading CTA**: full-width primary button at BOTTOM of the metrics card (not beside refresh). Opens **Trading Wizard**:
  Mode (Paper/Live) → pick 1-3 strategies → Paper Forward Test OR Backtest → if Backtest: 70/30 split or 100% historical → Launch.
- **Move AI Trading Coach OUT of Cockpit → into Trade tab.**
- Active Watchlist: compress height, reduce padding, move Validate + Sync closer, reduce gap above "Charts" shortcut.
- Trade Lifecycle: keep viz, reduce padding above, denser.

### TRADE ("What should I do?") — swipeable subtabs
- Subtab order: **Orders (default)** · Positions · History (horizontally scrollable, momentum, animated auto-centering underline; desktop static).
- **ORDERS screen** (top→bottom):
  1. **Create Manual Order** card at very top — Buy/Sell · Market/Limit (paper order via new endpoint).
  2. **Active Strategies toggle grid** — every running strategy w/ instant On/Off (calls state endpoint; no Workspace dive).
  3. **Sticky bottom actions**: [AI Trade Coach] [Add Strategies] always visible.
- **POSITIONS**: strong already — only density (card padding, gaps, button spacing). Keep Exit, P/L, Average, LTP, Investment.
- **HISTORY**: show 3 → "More" → 15 → internal scroll after 15. Never load hundreds.

### STRATEGY CENTER ("What do I own?")
- Header: **Add ("+") button top-right** aligned with title. Remove standalone "Import Strategy" pill.
- "+" opens **bottom sheet**: Import Strategy (Paste JSON) · Write Strategy (Manual Builder) · Describe & Build (AI Wizard). Plus rotates 45° when open. aria-label "Add Strategy"; desktop tooltip.
- Keep search. Filter chips: reduce spacing, wrap cleanly.
- Leaderboard: reduce row height slightly (keep readability), show more.
- AI strategy creation returns deterministic JSON schema (name, description, market=spot, timeframe, entry.conditions[], exit.conditions[], risk{stop_loss,take_profit,trailing_stop}, filters{}, position_sizing{}, metadata{created_by:AI,source}).

### RESEARCH ("Does it work?")
- Leaderboard/Analytics card: remove subtitle; dropdown directly under title; bring chart + legend up; reduce legend row gaps. Keep chart size/font/colors. Target ~30-40% less height.
- Validation wizard: reduce spacing between progress icons / title / cards; remove "Which engine do you want to validate?" subtitle.

### WORKSPACE ("How is my system configured?")
- Rename title "How is Ananta setup?" → **"Ananta Setup"**.
- Header: left "Engine & Risk"; right button **"Stop Engine"** (was "Emergency Stop").
- Entry & Exit Engine card: entire card clickable; remove "Open Engine" button; add **Edit icon** beside title (card OR edit → same page). Reduce top/bottom padding, show more settings.
- Remove "POSITION MODIFIERS" eyebrow.
- **Ask Ananta chip** docked bottom-left (see below).

---
## ONBOARDING SYSTEM (Phase 3)
Combine three layers (like Linear/Notion/Figma):
1. **Guided spotlight tour** — first login (+ optional after major releases, + "Take a Tour"). Spotlight overlay dims screen except highlighted element; [Skip] [Next]; advances on tap (NOT timed); remembers completion per tour.
   - Cockpit: welcome → market metrics → Start Trading → watchlist → lifecycle.
   - Trade: Orders → strategy toggles → AI Coach → Positions.
   - Strategy: search → filters → "+" → leaderboard.
   - Research: Validate → AI Analysis → Closed trades.
   - Workspace: Entry/Exit Engine → Risk Monitor → Exchange Connections → Ask Ananta.
2. **Progressive first-visit tips** — small "💡 Tip:" hints only first few visits per feature; may fade (supplemental). e.g. Strategy "Tap + to create/import"; Research "Validate before deploying"; Workspace "Configure exit engine before live".
3. **Help mode** — "?" in Workspace: Replay Product Tour · per-tab walkthroughs · What's New · Keyboard Shortcuts (web).
- Persistence: store completed tours/tips in backend (owner prefs) or AsyncStorage/localStorage.

## ASK ANANTA — embedded trading copilot (Phase 4)
- Docked **chip** bottom-left of Workspace (later all tabs). ~44-48px. First launch shows "✦ Ask Ananta" pill → collapses to icon after few seconds → tap expands → long-press quick actions. Never covers key controls.
- First open = onboarding panel with suggested questions (context-aware per tab):
  - Workspace: Explain this page · Configure Risk Monitor · Explain ATR Trailing Stop · What does Breakeven Arm do? · Paper vs Live?
  - Strategy: Best strategy? · Explain Hunter · Import/build a strategy.
  - Research: How do I validate? · Explain AI Score · Why did this fail?
  - Trade: Explain this position · Why is LINK open? · Pause Hunter · Add strategy.
  - Cockpit: Today's performance · Why rejected? · Market regime · Start paper trading.
- Q&A: reuse `ai_analyst.answer_question` + inject current tab/page context.
- **Action-executor (full v1):** parse intents → CONFIRMATION modal → call existing endpoint. Examples: "Pause Hunter"→state toggle; "Run research on EMA Cross"→open Research preselected; "Start paper trading with Hunter"→wizard; "Change stop loss to 2%"→Workspace setting prefilled; "Why did BTC exit?"→trade explanation. NEVER auto-mutate.
- **Feature toggle:** `ask_ananta_enabled` owner setting (Workspace). LLM only called on send. Off until launch after testing.

## EXECUTION PHASES
0. Backend audit (DONE) + net-new endpoints (manual order, ask-ananta layer, prefs).
1. Nav + layout foundation: 8pt tokens, swipeable subtabs (animated auto-center underline), global padding cut, remove decorative copy.
2. Screen-by-screen refactor (Cockpit, Trade/Orders, Strategy, Research, Workspace) — mobile spatial + web feature parity.
3. Onboarding (tour + tips + help).
4. Ask Ananta (chip + context Q&A + action-executor + toggle).
5. Polish (motion, gestures, safe-area, responsiveness, touch targets).
6. Full regression (testing agent, both platforms, all prior flows).

## TESTID CONVENTIONS
kebab-case, function-based. Web `data-testid`, mobile `testID`. New: `cockpit-start-trading`, `wizard-*`, `trade-subtab-orders|positions|history`, `manual-order-*`, `strategy-toggle-{key}`, `sticky-ai-coach`, `sticky-add-strategy`, `strategy-add-btn`, `add-menu-*`, `workspace-stop-engine`, `engine-card-edit`, `tour-next`, `tour-skip`, `ask-ananta-chip`, `ask-ananta-send`, `ask-ananta-toggle`.
