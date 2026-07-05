# Ananta — Mobile Parity Pack (web = source of truth)

Paste this whole file into the external mobile workspace agent.

## 1. DESIGN TOKENS (exact web values — replace mobile `src/theme.ts`)

### Colors (matte-black cockpit, matte-silver accent — NOT teal, NOT blue-black)
```
bg            #090A0C   // app background (near-pure matte black)
panel/card    #121418   // cards / panels
panelHover    #1A1D24   // pressed / hover surface
border        #2A2D35   // hairline borders
text          #E2E4E9   // primary text (off-white, NOT pure #FFFFFF)
textSecondary #878E99   // muted labels
textTertiary  #5C6370   // faint meta
accent        #C0C5CE   // MATTE SILVER accent (interactive / active). NOT #14E0C9 teal
positive      #10B981   // gains (emerald)
negative      #F43F5E   // losses (rose)
warning       #D9B36B   // caution (muted gold)
```
- P&L color rule: positive/zero -> `#10B981`, negative -> `#F43F5E` (do NOT use teal for gains).
- "Glow" on active dots = 1px silver ring `rgba(192,197,206,0.3)`, not a neon glow.

### Radius
```
sm 4   md 6   lg 8   (pills for chips only)
```

### Fonts (load via expo-font — currently mobile uses system fonts = mismatch)
```
Headings  -> Chivo            (weights 400–900)
Body      -> IBM Plex Sans    (weights 300–700)
Mono/nums -> JetBrains Mono   (weights 300–700)  // ALL numbers, tickers, labels
```
- Install: `npx expo install expo-font @expo-google-fonts/chivo @expo-google-fonts/ibm-plex-sans @expo-google-fonts/jetbrains-mono` and load in the root `_layout.tsx` with `useFonts`, gate render on `fontsLoaded`.
- Label style (the "LABEL-TAG" used everywhere on web): JetBrains Mono, 10px, weight 700, `letterSpacing: 2` (0.2em), UPPERCASE, color `#878E99`.
- Numeric/tabular values: JetBrains Mono. Never render money/percent in a sans font.

### Suggested theme.ts replacement
```ts
export const colors = {
  bg: "#090A0C", card: "#121418", cardPressed: "#1A1D24", border: "#2A2D35",
  text: "#E2E4E9", textMuted: "#878E99", textFaint: "#5C6370",
  accent: "#C0C5CE", positive: "#10B981", negative: "#F43F5E", warning: "#D9B36B",
};
export const pnlColor = (v: number) => (v >= 0 ? colors.positive : colors.negative);
export const radius = { sm: 4, md: 6, lg: 8, pill: 999 };
export const fonts = { heading: "Chivo_700Bold", body: "IBMPlexSans_400Regular", mono: "JetBrainsMono_500Medium" };
```

## 2. BACKEND CONTRACT (shared FastAPI — no backend changes, mobile just calls these)
Base: `${EXPO_PUBLIC_BACKEND_URL}/api`  · Auth: `Authorization: Bearer <token>` (token key `ananta_owner_token`)

### Auth
- `POST /auth/login {email,password}` -> `{token,email,role}`
- `GET /auth/me` · `POST /auth/logout`

### Market / Portfolio / Trades
- `GET /market/snapshots` · `GET /market/snapshot/{base}` · `GET /market/candles?symbol=&timeframe=&limit=`
- `GET /portfolio` · `POST /positions/{base}/close` · `GET /trades?limit=`
- `GET /pending_orders` · `GET /levels/{base}` · `GET /risk/status` · `GET /live/status`
- `GET /environment` · `POST /environment/{mode}`  (PAPER|DRY_RUN|LIVE)
- `GET /reasoning?limit=&symbol=` · `GET /news/current`

### Research (Datalogs) — mobile is MISSING most of these
- `GET /research/summary` · `GET /research/funnel` · `GET /research/rejections`
- `GET /research/winner_profile` · `GET /research/missed_opportunities`
- `GET /research/rsi_distribution` · `GET /research/zone_effectiveness`
- `GET /research/strategy_lab` · `GET /research/staged_exit` · `GET /research/entry_quality`
- `GET /research/log?symbol=&limit=`

### Settings
- `GET /settings` · `PUT /settings {..patch..}`  (incl. `manual_kill_switch: bool`, `trading_mode`, `enabled_symbols`)
- `GET /watchlist/validate`

### RESEARCH LAB / VALIDATION (NEW — mobile is MISSING all of these)
- `GET /lab/data/coverage` -> `{ periods:[...], symbols:[{symbol, bars_1h, ...}] }`
- `GET /lab/presets` -> `{ presets:[{id,label,description}] }`
- `POST /lab/runs` -> `{ id, status, kind }`  BODY:
  ```json
  {
    "kind": "backtest",              // or "walk_forward"
    "symbols": ["BTC/USD","ETH/USD"],
    "period": "3m",                  // 1m|2m|3m|quarter|6m|1y|2y|custom
    "strategies": ["hunter","squeeze","continuation"],  // NEW: subset; omit/null = all
    "compare_timeframes": false,      // NEW: false = 1h only (fast); true = also 30m/15m
    "preset": "<preset id>"           // optional (Mode C)
  }
  ```
- `GET /lab/runs?limit=` -> `{ runs:[{id,kind,status,progress_pct,symbols,strategies,compare_timeframes,...}] }`
- `GET /lab/runs/{id}` -> full run incl. `result.per_symbol`, `result.multi_timeframe`
- `DELETE /lab/runs/{id}` · `GET /lab/runs/{id}/pdf`
- `POST /lab/runs/{id}/propose` · `GET /lab/proposals` · `POST /lab/proposals/{id}/apply|reject`

### Push (mobile-only)
- `POST /notifications/register {push_token, platform, prefs}` · `POST /notifications/test`

## 3. VALIDATION UI PARITY (match the new web Research Lab)
Three compact controls (on mobile = bottom-sheet checklists, not popovers):
- **Strategy** multi-select with a "Select all" row. Options: Hunter, Volatility Squeeze, Continuation. Default = all selected. Sends `strategies[]`.
- **Assets** multi-select with "Select all" (from `/lab/data/coverage` symbols where `bars_1h > 0`). Sends `symbols[]`.
- **Historical Period** single-select dropdown (from coverage `periods`). Sends `period`.
- **Compare 30m & 15m timeframes** checkbox — DEFAULT OFF. Sends `compare_timeframes`.
- Poll `GET /lab/runs` every ~2.5s while any run is QUEUED/RUNNING; show `progress_pct`.

## 4. PARITY CHECKLIST (how to verify)
- [ ] `theme.ts` bg is `#090A0C`, accent is `#C0C5CE` (silver, not teal), positive `#10B981`, negative `#F43F5E`.
- [ ] Chivo / IBM Plex Sans / JetBrains Mono loaded via expo-font; all numbers use JetBrains Mono.
- [ ] Uppercase mono labels with 0.2em letter-spacing, color `#878E99`.
- [ ] Cards: bg `#121418`, 1px border `#2A2D35`, radius 8.
- [ ] `src/api.ts` includes ALL `/research/*` + `/lab/*` endpoints above.
- [ ] Validation screen has strategy + asset multi-selects + period + compare-TF (default off).
