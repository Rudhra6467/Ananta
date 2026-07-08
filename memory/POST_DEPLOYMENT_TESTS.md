# Ananta.AI — Post-Deployment Test Scenarios

Run these end-to-end after you **Publish / redeploy** to production. Log in as owner first.
Production has its own DB + env vars — set `OWNER_EMAIL` / `OWNER_PASSWORD` there before testing.

---

## Scenario 1 — Strategy lifecycle gate (LIVE / PAPER / DISABLED controls entries)
**Goal:** Prove the Strategy Center status actually governs the live engine.

Steps:
1. Go to **Strategies** → open **Hunter** → set status to **DISABLED** (owner only).
2. Wait for 2–3 engine cycles (~3–5 min) or trigger a manual cycle.
3. Open **Logs** → confirm Hunter shows a reason code `STRATEGY_DISABLED hunter status=DISABLED`
   on any bar where it would otherwise have signalled BUY. No new Hunter position opens.
4. Set Hunter back to **PAPER**. Confirm new Hunter entries can resume on the next qualifying setup.

**Expected:** DISABLED → zero new Hunter entries (open positions still managed by the exit engine).
PAPER/LIVE → entries resume. Squeeze/Continuation are independently gated the same way.

---

## Scenario 2 — Strategy Health Score + Timeline are truthful
**Goal:** Prove the one-number health and lifecycle timeline reflect real ledger data.

Steps:
1. Strategies → open any strategy → **Overview**: read the **Health** gauge (0–100) and the
   six component bars (Win Rate, Risk-Adjusted, Recent Form, Consistency, Sample Confidence, Owner Rating).
2. Confirm the headline number equals the average of the visible component bars (transparent).
3. Open the **Timeline** tab: Created → Last Optimized → Validation → First Paper Trade → Live → Latest Trade.
   Dates should match your actual config saves and trade history.

**Expected:** Health = mean of component scores (no "magic" number). Timeline milestones marked done only
when the underlying event exists (e.g. "Live Trading" is filled only when status = LIVE).

---

## Scenario 3 — Guided workflow / "one question per page"
**Goal:** A first-time judge understands the product in under a minute.

Steps:
1. Walk the nav in order: **Cockpit → Portfolio → Strategies → Logs → Research Lab**.
2. On each page confirm the cyan question line at the top:
   - Cockpit: "What is happening right now?"
   - Portfolio: "How much am I making?"
   - Strategies: "What strategies do I own?"
   - Logs: "Why am I winning or losing?"
   - Research Lab: "Does my strategy actually work?"
3. From a strategy, run a validation in **Research / Validation** and confirm results attach back.

**Expected:** Every screen answers exactly one question; navigation reads as a workflow, not a settings tree.

---

## Notes
- All AI surfaces (Architect, AI Analyst) consume LLM credits and are behind visible owner-only toggles.
- These tests are non-destructive except toggling strategy status (revert to PAPER when done).
- If any heavy page 502s on prod, bump the container memory tier (known OOM on large prod DB) and retry.
