# Cross-Platform Port Blueprint: Web to Mobile (Parity Update)

## 1. Detection & Setup
*   **Source Platform:** Web (`/app/frontend` - React, Tailwind, shadcn/ui)
*   **Target Platform:** Mobile (`/app/mobile` - Expo React Native)
*   **Evidence:** Both platforms exist and are fully populated with 5 core tabs. However, recent changelogs (Iteration 62-65) indicate major feature additions to the Web platform (Strategy Health, Research Lab Analytics, Strategy Center redesign, Clone/Rename/Delete user strategies, Server-backed Lab Runs History) that explicitly deferred "Mobile parity" to this cross-platform job.

## 2. Existing App Map (Web Frontend)
Recent Web additions driving this parity port:
*   **Dashboard (Cockpit):** Now includes a "Strategy Health Today" card highlighting the top 2 recommended strategies for paper trading, complete with a numeric health-count badge in the title and a link to the full Health Dashboard. The 4-box `BotBrainStrip` was removed to declutter.
*   **Strategy Center (`StrategyCenter.jsx` & Detail View):** Replaced the Deployed/Edit segmented tabs and leaderboard with a single, unified grid. Add Strategy modal now features a "Copy Existing" (Clone) option. Detail views for user-added strategies feature "Rename" and "Delete" actions. All detail views feature a "Test in Research Lab" quick-action button.
*   **Research (`Research.jsx`):** Features a new "HEALTH" sub-tab displaying the `StrategyHealthPanel` (per-strategy recommendations, Best TF/Exit, recent form). Deep analytics results surface in the UI rather than just via PDF.
*   **AI Analysis / Reports History:** "My Reports History" component consumes a server-backed list of past lab runs (Status, Assets, Timeframes), replacing local storage. Allows deleting and downloading PDFs.

## 3. Shared Backend API Surface (Reusable Endpoints)
The new Web features rely on the following existing shared endpoints, which the Mobile app MUST now consume:

*   **Strategy Health**
    *   `GET /api/lab/health` - Returns the latest daily health sweep results.
    *   `GET /api/lab/health/status` - Returns status of a running health sweep.
    *   `POST /api/lab/health/run` - Triggers a manual health analysis (owner-only).
*   **Library Management (Clone/Rename/Delete)**
    *   `POST /api/library/{id}/clone` - Clones an existing declarative strategy.
    *   `PATCH /api/library/{id}` - Renames a user-added strategy.
    *   `DELETE /api/library/{id}` - Deletes a user-added strategy (if disabled).
*   **Lab Runs History**
    *   `GET /api/lab/runs` - Returns history of Research Lab runs.
    *   `GET /api/lab/runs/{id}/pdf` - Serves the PDF report.
    *   `DELETE /api/lab/runs/{id}` - Deletes a run history record.

## 4. Data Models & Integrations
*   **Data Models:** 
    *   `strategy_health`: Aggregated health data and recommendations per strategy.
    *   `lab_runs`: Represents execution status (DONE/RUNNING/FAILED/QUEUED) and metadata for backtests.
*   **Integrations:** No new third-party integrations. Everything remains pure REST to the existing Python backend using standard JWT Bearer auth.
*   **Platform Specific Flags:** Mobile will use `expo-file-system` and `expo-sharing` (or `Linking`) to handle PDF downloads from the lab run endpoints.

## 5. Port Requirements (Target: Mobile)
**Screen-by-Screen Breakdown:**
1.  **Dashboard (Cockpit - `app/(tabs)/index.tsx`):** 
    *   Remove the old 4-box analysis strip if present.
    *   Add a "Strategy Health Today" card below the primary header. Fetch `GET /api/lab/health` and display the top 2 recommended strategies. 
    *   Add a numeric badge to the section header and a "View Health Dashboard" link routing to the Research tab.
2.  **Strategy Center (`app/(tabs)/strategy.tsx` & `app/library/[id].tsx`):** 
    *   Flatten the UI: Remove DEPLOYED/EDIT segmented controls and the leaderboard. Render a single flat grid of strategy cards.
    *   In the Add Strategy modal, introduce a "Copy Existing" option hitting `POST /api/library/{id}/clone`.
    *   In the Catalog Detail view (`[id].tsx`), add "Rename" (via Alert.prompt or Modal) and "Delete" (ActionSheet/Alert) actions for user-added strategies.
    *   Add a "Test in Research Lab" button that redirects to the Research tab using router params (e.g., `router.push('/research?strat=key')`).
3.  **Research (`app/(tabs)/research.tsx`):**
    *   Introduce a new segmented control or sub-tab for "HEALTH". 
    *   Render a mobile-optimized equivalent of `StrategyHealthPanel` listing the cards fetched from `/api/lab/health` (Best TF/Exit, MFE capture, Recommendation badge).
    *   Expose deeper lab analytics within the Validate results view rather than relying strictly on PDF viewing.
4.  **AI Analysis / Reports History:**
    *   Implement "My Reports History" using a `FlatList` fetching from `GET /api/lab/runs`.
    *   Render status badges (DONE/RUNNING/FAILED) and provide a swipeable or long-press action to `DELETE /api/lab/runs/{id}`.
    *   Provide a button to open the PDF report via the device's native browser or document viewer (`Linking.openURL`).

## 6. Open Questions / Risks
*   **UI Density in Health Panel:** The Web `StrategyHealthPanel` contains dense tables (e.g., Regime Breakdown). The mobile implementation may need to condense these into simple summary rows or expandable accordions to prevent horizontal overflow.
*   **PDF Handling:** Expo's Web view (`Linking.openURL`) vs saving the PDF directly. Standard native `Linking` to the API endpoint (with JWT in headers if required) is typically safest for MVP. 
*   **Refresh Strategy:** Should "My Reports History" and "Strategy Health" use pull-to-refresh (`RefreshControl`), or a background polling mechanism (`setInterval`) to sync RUNNING statuses? Web uses SWR/polling.