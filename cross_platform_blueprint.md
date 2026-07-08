# Cross-Platform Port Blueprint: Web to Mobile

## 1. Detection & Setup
*   **Source Platform:** Web (`/app/frontend` - React, Tailwind, shadcn/ui)
*   **Target Platform:** Mobile (`/app/mobile` - Expo React Native)
*   **Evidence:** The `/app/frontend` folder contains a fully evolved React application with an updated 5-tab layout (`Dashboard`, `Trade`, `StrategyCenter`, `Research`, `Workspace`). The `/app/mobile` folder contains an outdated Expo router skeleton with only 4 tabs (`index`, `portfolio`, `reports`, `settings`) that no longer aligns with the Web feature set.

## 2. Existing App Map (Web Frontend)
*   **Screens / Routes** (`react-router-dom` in `App.js`):
    *   `/judge`: Standalone route rendering `JudgeView.jsx` (Human-in-the-loop overrides/approvals).
    *   `/`: Main layout wrapper (`AppShell.jsx`) using 5 primary tabs for navigation.
*   **Primary Navigation (5 Tabs)**:
    1.  **Dashboard (Cockpit)**: Real-time market status, environment mode (Paper vs Live), killswitch controls.
    2.  **Trade**: Active positions list, unrealized PnL, manual exit execution, and pending orders.
    3.  **Strategy**: Strategy registry (Hunter, Squeeze), toggle LIVE/PAPER/SHADOW states, Strategy Architect chat, Monte Carlo simulations.
    4.  **Research**: AI Analyst Terminal, Strategy Validation, closed trades analysis.
    5.  **Workspace**: System settings, risk parameters, engine health, and environment controls.
*   **Key Components & State**:
    *   **Context:** `AuthContext.js` (owner authentication), `AppDataContext.js` (global SWR-like data polling).
    *   **Components:** `EnvironmentToggle`, `ManualExitButton`, `AIAnalystTerminal`, `LabModal`, `SavedConfigsPanel`.
*   **Primary User Flows**:
    *   **Auth Flow:** Email/password login saving token to localStorage.
    *   **Trading Lifecycle:** Market scans -> Active Trades -> Manual/Auto Close -> Review in Workspace/Research.
    *   **Strategy Engineering:** Chat with AI Architect -> Run Lab/Monte Carlo -> Propose config -> Promote strategy to SHADOW/PAPER.

## 3. Shared Backend API Surface (Reusable Endpoints)
All API endpoints live under the `/api` prefix on the shared FastAPI backend (`/app/backend/server.py`). The mobile app MUST use these exact endpoints via standard JWT Bearer auth.

*   **Auth & System**
    *   `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
    *   `GET /api/environment`, `POST /api/environment/{mode}`
    *   `GET /api/settings`, `PUT /api/settings`
    *   `GET /api/risk/status`
*   **Market & Execution**
    *   `GET /api/market/snapshots`, `GET /api/market/candles`, `GET /api/levels/{base}`
    *   `GET /api/portfolio`, `POST /api/positions/{base}/close`
    *   `GET /api/trades`, `GET /api/pending_orders`
    *   `POST /api/cycle/run/{symbol_base}`
*   **Strategy & Architect (New)**
    *   `GET /api/strategy/registry`, `PUT /api/strategy/{key}/state`
    *   `POST /api/strategy/architect/chat`
    *   `GET /api/strategy/configs`, `POST /api/strategy/configs`
*   **Research & Lab (New)**
    *   `POST /api/lab/runs`, `GET /api/lab/runs/{run_id}`
    *   `POST /api/lab/monte_carlo`
    *   `GET /api/research/summary`, `GET /api/research/funnel`
    *   `POST /api/analytics/ai_query`

## 4. Data Models & Integrations
*   **Database:** MongoDB via Motor (async). Core collections: `users`, `trades`, `reasoning`, `research_log`, `strategy_configs`, `lab_runs`. IDs are string-based UUIDs.
*   **Authentication:** Pure first-party email/password. **No 3rd-party auth integrations to port.**
*   **Platform Specific Flags:**
    *   *Storage:* Web uses `localStorage`. Mobile MUST use `@react-native-async-storage/async-storage` or `expo-secure-store`.
    *   *Environment Variables:* Web uses `REACT_APP_BACKEND_URL`. Mobile MUST use `EXPO_PUBLIC_BACKEND_URL`.

## 5. Port Requirements (Target: Mobile)
**Architecture Update:**
*   The current `/app/mobile/app/(tabs)/_layout.tsx` MUST be rewritten to reflect the new 5-tab structure: `index` (Cockpit), `trade` (Trade), `strategy` (Strategy), `research` (Research), and `workspace` (Workspace).

**Screen-by-Screen Breakdown:**
1.  **Dashboard (Cockpit - `index`):** Needs a `ScrollView` with `RefreshControl`. Render market tiles and environment status.
2.  **Trade (`trade`):** Implement a `FlatList` mapping active and pending positions. Use a native Action Sheet or React Native Modal to confirm "Manual Close" requests to `/api/positions/{base}/close`.
3.  **Strategy (`strategy`):** Convert the dense Web registry into stacked cards. The AI Architect Chat requires a `KeyboardAvoidingView` wrapping a chat `FlatList` and a bottom text input.
4.  **Research (`research`):** Condense Monte Carlo outputs and AI Analyst Terminals into collapsible accordions or sub-screens (`router.push`) to save vertical space.
5.  **Workspace (`workspace`):** Standard settings list using React Native `Switch` for booleans (e.g., enable live trading) and `TextInput` with `keyboardType="numeric"` for risk overrides. Add a distinct "Logout" button.

**Framework Translation Guidelines:**
*   **Styling:** Since `NativeWind` is missing, translate Tailwind classes to standard React Native `StyleSheet.create`.
*   **Interaction:** Map `onClick` to `onPress`. Wrap primary screens in `SafeAreaView`.
*   **Icons:** Replace `lucide-react` with `@expo/vector-icons`.

## 6. Open Questions / Risks
*   **Data Density on Strategy/Research Tabs:** The web Lab and Monte Carlo modals are extremely data-heavy. Should the mobile app omit detailed charting/matrices and only display high-level AI summaries to preserve UX?
*   **Chart Implementation:** Web uses `lightweight-charts` (DOM-based). Should we wrap it in `react-native-webview` or rewrite the charts using a native library (e.g. `react-native-wagmi-charts`)?
*   **Scope:** Should the mobile MVP include the full Strategy Architect LLM chat, or strictly focus on active trade monitoring (Cockpit & Trade)?