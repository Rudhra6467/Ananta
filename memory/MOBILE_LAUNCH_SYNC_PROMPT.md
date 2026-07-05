# Ananta Mobile — Launch Sync Prompt (paste into your mobile workspace agent)

> **Context — read first.** Ananta is a cross-platform algorithmic trading app: a **React web app**, this **Expo (React Native) app**, and **one shared FastAPI + MongoDB backend**. The **web app is the source of truth**; you are bringing this Expo app to parity so we can ship to the App Store. All data comes from the shared backend at `${EXPO_PUBLIC_BACKEND_URL}/api`, authenticated with a Bearer owner token (`ananta_owner_token`). **Respond in English only.** Do not invent new backend endpoints — everything below already exists on the shared backend.
>
> There are TWO parity workstreams below: **(A) Account / Privacy overlay** (App Store requirement) and **(B) Research Lab — Modular Exit Framework + auto exit-comparison PDF** (the big new feature). Implement whichever isn't already present; verify both before launch.

---

## A. Account / Privacy overlay (App Store requirement)

Surface account + privacy info **in-app** (no external privacy URL) via an overlay opened from the Ananta logo.

1. **Logo button** — make the top-left Ananta logo a tappable `Pressable` with a pressed state + `hitSlop` (`testID="account-logo-btn"`) → `router.push('/account')`. Register `app/account.tsx` as a `presentation:'modal'` expo-router route.
2. **Overlay (`app/account.tsx`)**:
   - Header with close X (`account-close-btn`).
   - Profile header: avatar initials + real email (`account-email`) + auth badge (`account-auth-status` = `AUTHENTICATED` / `READ-ONLY`).
   - **Login & Auth card**: real email (`account-cred-email`); **masked** password `••••••••` (`account-cred-password`, NEVER the real one); "Secure token (JWT)".
   - Invite banner (`account-invite-banner`).
   - **Features** rows: `account-feature-exchange` (Kraken pill), `-referrals`, `-offers`, `-earn`, `-tax` → "Soon" pills.
   - **Settings** rows: `account-setting-payments`, `-notifications`, `-privacy` → "Soon" pills.
   - **Privacy statement** (`account-privacy-note`): *"Ananta stores only your account email and an encrypted authentication token to keep you signed in. We do not sell personal data. Trading is executed via your own exchange keys, which are stored securely and never shared."*
   - **Log out** (`account-logout-btn`, owner only) → `logout()` + `router.replace('/login')`.
3. **Needs NO new endpoints** — email/role come from `useAuth().owner`. Placeholder rows keep "Soon" pills (never dead-end). Safe-area aware, dark theme.

---

## B. Research Lab — Modular Exit Framework + auto exit-comparison PDF (NEW)

The Research Lab lets the operator backtest strategies over historical data and download a PDF report. The web app was just upgraded with a **Modular Exit Strategy Framework** and an **automatic multi-config exit-comparison table in the PDF**. Bring the mobile Lab screen to parity.

### B1. What changed on the backend (already live — do NOT rebuild)
- `POST /api/lab/runs` now accepts exit-config fields (see contract below).
- **Every backtest run automatically replays the identical entry set under 5 exit configs** — `$2.00/$1.50`, `$3.00/$2.25`, `$4.00/$3.00`, `$5.00/$4.00`, and an **ATR baseline (×2.5, 14p)** — and embeds a **comparison table** in the generated PDF (Profit factor, Win rate, Expectancy, Net return, Max drawdown per config, plus a "best engine" verdict ranked by return-over-drawdown). This is **100% server-side inside the PDF** — the mobile app needs **no UI and no extra endpoints** to render the table; it appears in the downloaded PDF for free.
- The comparison replays on the timeframes the run uses: **1h only by default**; it also adds **15m + 30m** when `compare_timeframes: true`.

### B2. Mobile Lab UI to build (mirror the web `StrategyValidationPanel`)
On the Research Lab / Validation screen, the "New validation" form must let the owner configure and submit a backtest:

- **Assets** — multi-select from `GET /api/lab/data/coverage` (returns seeded symbols; e.g. `BTC/USD`, `ETH/USD`, `SOL/USD`, `AVAX/USD`, `XRP/USD`, `PAXG/USD`, `LINK/USD`, `AAVE/USD`, `ARB/USD`, `RENDER/USD`). `testID="lab-asset-select"`.
- **Period** — `1m | 2m | 3m | quarter | 6m | 1y | 2y` (default `3m`). `testID="lab-period-select"`.
- **Strategies** — multi-select of `hunter | squeeze | continuation` ("Select all" = run every one; `null`/all = all). `testID="lab-strategy-select"`.
- **Compare timeframes** — toggle (default OFF). OFF = 1h-only (fast); ON = also runs 15m + 30m. `testID="lab-compare-tf-toggle"`.
- **Exit method** — segmented control, 3 options (`testID="lab-exit-<id>"`):
  - `native` — "Native Strategy" (each strategy's own Universal Exit Engine).
  - `atr` — "ATR Exit" (ATR trailing stop). Reveals a **collapsible** advanced panel: `multiplier` (2.5), `period` (14), `trail_activation_pct` (3), `trail_distance` (2).
  - `fixed` — "Fixed $ Target" (default). Reveals a **collapsible** advanced panel: `target_profit` ($5), `target_loss` ($4), with a live "≈X% of trade value" hint using position size $75.
- **Submit** (`testID="lab-submit-validation-btn"`) → POST the run, then poll status and show a progress bar.
- **Runs list** — poll `GET /api/lab/runs`; per DONE run show a **Download PDF** action (`testID="lab-run-pdf-<id>"`) that fetches `GET /api/lab/runs/{id}/pdf` (Bearer token) and opens/saves it. The exit-comparison table is inside that PDF automatically.

### B3. Exact backend contract (shared — do not change)
`POST /api/lab/runs` body (`LabRunCreate`):
```jsonc
{
  "kind": "backtest",                 // required
  "symbols": ["BTC/USD", "ETH/USD"],  // required (from coverage)
  "period": "3m",                     // 1m|2m|3m|quarter|6m|1y|2y|custom
  "strategies": ["hunter","squeeze","continuation"], // or null = all
  "compare_timeframes": false,        // false = 1h only; true = + 15m/30m
  "exit_method": "fixed",             // "native" | "atr" | "fixed"
  "target_profit": 5.0,               // fixed-exit take-profit ($, net)
  "target_loss": 4.0,                 // fixed-exit stop-loss ($, net)
  "atr_params": { "multiplier": 2.5, "period": 14, "trail_activation_pct": 3, "trail_distance": 2 } // only for atr
}
```
Response: `{ "id", "status", "kind" }`. Then:
- `GET /api/lab/runs` → list (has `status`, `progress_pct`, `result` when DONE).
- `GET /api/lab/runs/{id}` → single run.
- `GET /api/lab/runs/{id}/pdf` → PDF bytes (contains the auto exit-comparison table + trade log).
- `DELETE /api/lab/runs/{id}` → delete.
- `GET /api/lab/data/coverage` → seeded symbols/periods for the pickers.
All Lab endpoints are **owner-only** (Bearer `ananta_owner_token`).

### B4. Mobile constraints (React Native / Expo)
- Use `expo-router` file-based routes, `Pressable`/`TouchableOpacity` with `onPress` (never `onClick`), `<Text>` for all text, `StyleSheet.create`, safe-area insets. No HTML elements, no `className`, no CSS files, no `localStorage` (use SecureStore/AsyncStorage for the token). Use `testID` (not `data-testid`).
- For PDF: fetch with the Bearer header and open via `expo-sharing` / `WebBrowser` / `FileSystem` (whatever the app already uses). Do NOT try to render the comparison table yourself — it's baked into the PDF.

---

## C. Theme parity — align `src/theme.ts` to web
- Colors: bg `#090A0C`, card `#121418`, border `#2A2D35`, text `#E2E4E9`, accent `#C0C5CE` (matte silver, NOT teal), positive `#10B981`, negative `#F43F5E`, warning `#D9B36B`; radii 4/6/8.
- Fonts via `expo-font`: **Chivo** (headings), **IBM Plex Sans** (body), **JetBrains Mono** (numbers/labels). Labels: 10px / 700 / 0.2em uppercase, color `#878E99`.

---

## D. Definition of done (verify before launch)
1. **Account overlay:** tap logo → overlay opens; real email + `AUTHENTICATED`/`READ-ONLY` badge; password masked; privacy note visible; Features/Settings show "Soon"; close + logout work.
2. **Research Lab:** can pick assets/period/strategies, choose Native/ATR/Fixed (with collapsible advanced panels), toggle Compare Timeframes, submit a run, watch progress, and **download the PDF**.
3. **Exit-comparison PDF:** open a completed run's PDF and confirm the **"EXIT ENGINE COMPARISON"** section lists all 5 configs with Profit factor / Win rate / Expectancy / Net return (%) / Max DD (%), a ★ best row, and a "Best engine (return/drawdown)" summary line. (This is server-generated — if the web PDF shows it, mobile's will too.)
4. Matte-black/silver theme + the 3 fonts applied throughout.
