# Cross-Platform Port Blueprint: Web to Mobile

## 1. Detection & Setup
*   **Source Platform:** Web (`/app/frontend` - React, Tailwind, shadcn/ui)
*   **Target Platform:** Mobile (`/app/mobile` - Expo React Native)
*   **Evidence:** The `/app/frontend` folder contains a populated React Create-React-App project with robust components, routing, and styling. The `/app/mobile` folder contains a fresh Expo router skeleton (`app.json`, `app/`, `package.json`).

## 2. Existing App Map (Web Frontend)
*   **Screens / Routes** (`react-router-dom` in `App.js`):
    *   `/judge`: Standalone route rendering `JudgeView.jsx` (Human-in-the-loop overrides/approvals).
    *   `/`: Main layout wrapper (`AppShell.jsx`) using tabs for navigation.
*   **Primary Navigation (Tabs)**:
    1.  **Cockpit (Dashboard)** (`Dashboard.jsx`): Real-time market status, active environment mode (Paper vs Live), AI reasoning timelines, killswitch controls.
    2.  **Portfolio** (`Portfolio.jsx`): Active positions list, unrealized PnL, manual exit execution.
    3.  **Reports / Datalogs** (`Reports.jsx`): Heavy data-tables for trade history, research logs, strategy sandboxes, and PDF export dialogs.
    4.  **Settings** (`Settings.jsx`): Configures risk parameters, system behavior, and displays engine state.
*   **Key Components & State**:
    *   **Context:** `AuthContext.js` governs `isOwner`, providing readonly mode by default vs. read-write access when authenticated.
    *   **Components:** `CandleChart.jsx` (using `lightweight-charts`), `TradeHistoryPdfDialog.jsx` (for generating PDF reports via `window.open`), `EnvironmentToggle.jsx`, `AnantaTrident.jsx`.
*   **Primary User Flows**:
    *   **Auth Flow:** Standard email/password login saving a JWT-style token to `localStorage` (`ananta_owner_token`).
    *   **Data Fetching:** SWR-like custom client map in `lib/api.js` pooling cacheable `GET` requests (e.g. `/market/snapshots`) vs live requests.
    *   **Trading Lifecycle:** Trigger cycles manually -> AI Reasonings appear -> Orders created -> Positions viewed in Portfolio -> Manual close or automatic hold.

## 3. Shared Backend API Surface (Reusable Endpoints)
All API endpoints live under the `/api` prefix on the shared FastAPI backend (`/app/backend/server.py`). The mobile app will use the exact same endpoints via Axios intercepting the bearer token.
*   **Global & Market**
    *   `GET /api/` - System health check.
    *   `GET /api/market/snapshots` - Returns market pricing and status.
    *   `GET /api/market/candles?symbol=...` - OHLCV data for charts.
    *   `GET /api/news/current` - Live crypto news snippet.
    *   `GET /api/levels/{base}` - S/R technical levels.
*   **Portfolio & Orders**
    *   `GET /api/portfolio` - Current holdings & balances.
    *   `POST /api/portfolio/reset` - *(Requires Auth)* Purge portfolio.
    *   `POST /api/positions/{base}/close` - *(Requires Auth)* Liquidate position.
    *   `GET /api/pending_orders` - View unexecuted limit/stop orders.
    *   `GET /api/trades` - Chronological trade history.
*   **AI & Risk Engine**
    *   `GET /api/reasoning` - LLM analysis per asset.
    *   `GET /api/risk/status` - Exposure limits and active restrictions.
    *   `POST /api/cycle/run/{symbol}` - *(Requires Auth)* Force manual AI cycle.
*   **System & Auth**
    *   `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` - Bearer token logic.
    *   `GET /api/environment` / `POST /api/environment/{mode}` - Fetch/Set PAPER vs LIVE modes.
    *   `GET /api/settings` / `PUT /api/settings` - Engine configuration.
    *   `GET /api/report/*.pdf` - Direct URL downloads for PDFs (Trades, Reasoning, Full).
    *   `POST /api/admin/fresh-start` - *(Requires Auth)* Factory reset everything.

## 4. Data Models & Integrations
*   **Database:** MongoDB. Uses string-based UUIDs instead of ObjectIDs (meaning frontend IDs are pure strings). Core collections mapped: `users`, `login_attempts`, `trades`, `reasoning`, `cooldowns`, `pending_orders`, `research_log`.
*   **Authentication:** Pure first-party email/password auth issuing a token. **No 3rd-party integrations to port (no Google/Apple auth).**
*   **Platform Specific Flags:**
    *   *Storage:* The web uses `localStorage` for the auth token. Mobile MUST use `@react-native-async-storage/async-storage` or `expo-secure-store`.
    *   *Environment Variables:* Web uses `REACT_APP_BACKEND_URL`. Mobile MUST use `EXPO_PUBLIC_BACKEND_URL` in `api.js`.

## 5. Port Requirements (Target: Mobile)
**Framework Translation Guidelines:**
*   **Navigation:** Use `expo-router` instead of `react-router-dom`. Map the primary AppShell tabs to `app/(tabs)/_layout.tsx` (Cockpit, Portfolio, Reports, Settings).
*   **Styling:** Since `NativeWind` is not present in the mobile `package.json`, translate Tailwind classes to standard React Native `StyleSheet.create`. Replace shadcn UI with native primitives (`View`, `Text`, `Pressable`, `ScrollView`).
*   **Interaction:** Map `onClick` to `onPress`. Wrap primary screens in `SafeAreaView` from `react-native-safe-area-context`. Use `KeyboardAvoidingView` for auth and settings forms.
*   **Charts (`CandleChart.jsx`):** Lightweight Charts relies on the DOM. You must either render it inside `react-native-webview` or replace it with a native charting library (e.g. `react-native-wagmi-charts` or `react-native-gifted-charts`).
*   **Icons:** Replace `lucide-react` with `@expo/vector-icons` (e.g. `Feather` or `Ionicons`).
*   **PDF Generation:** Replace `window.open` calls with `Linking.openURL()` to safely trigger the system browser to view/download PDF documents from the backend API.

**Screen-by-Screen Breakdown:**
1.  **Auth / Readonly Banner:** Must globally track token in `AsyncStorage`. If unauthorized, render a persistent `View` (like the cyan readonly banner in the web AppShell) reminding users to log in.
2.  **Cockpit (Dashboard):** Needs a `ScrollView` wrapped in a `RefreshControl` to manually pull fresh market snapshots, alongside the SWR auto-refresh.
3.  **Portfolio:** Implement a `FlatList` mapping active positions. Use a native Action Sheet or Modal to confirm "Manual Close" requests.
4.  **Reports / Datalogs:** Standardizing dense web tables on mobile is difficult. Convert table rows to Stacked Cards in a `FlatList`.
5.  **Settings:** Use standard React Native `Switch` components for booleans, and `TextInput` with `keyboardType="numeric"` for numerical risk overrides.

## 6. Open Questions / Risks
*   **Data Density on Reports Tab:** The web `Reports.jsx` has extensive data tables (Shadow Sim, Strategy Labs, Funnel). Should the MVP port all these heavy analytics tabs, or focus strictly on Cockpit + Portfolio execution?
*   **Chart Implementation:** Is it preferred to inject `lightweight-charts` into a WebView (matches web aesthetics precisely) or adopt a native alternative (better performance/gestures)?
*   **PDF Handling:** Should PDFs just launch the phone's browser via `Linking.openURL`, or should we leverage `expo-file-system` to download and open the file natively inside the app?