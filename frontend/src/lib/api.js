import axios from "axios";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({
    baseURL: API,
    timeout: 30000,
});

// Attach the owner Bearer token (if logged in) to every request.
export const TOKEN_KEY = "ananta_owner_token";
client.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

// Global API-failure recovery: surface a single (deduped) toast for network drops
// and 5xx server errors so a silent failure never leaves the operator guessing.
// Expected 4xx (401/403/404/422) are left to the calling component — it renders
// contextual messaging. A 401 additionally clears the stale token.
let _lastToastAt = 0;
function _softToast(msg) {
    const now = Date.now();
    if (now - _lastToastAt < 4000) return; // dedupe bursts (Reports fires ~8 reads)
    _lastToastAt = now;
    toast.error(msg);
}
client.interceptors.response.use(
    (r) => r,
    (error) => {
        const status = error?.response?.status;
        if (status === 401) {
            localStorage.removeItem(TOKEN_KEY);
            // Notify AuthContext so React state flips to logged-out immediately
            // (no stale isOwner until a manual reload).
            if (typeof window !== "undefined") window.dispatchEvent(new Event("ananta:session-expired"));
        } else if (!error?.response) {
            if (error?.code !== "ERR_CANCELED" && !error?.config?.silent) _softToast("Network issue — retrying shortly. Check your connection.");
        } else if (status >= 500) {
            if (!error?.config?.silent) _softToast("The server hit a temporary error. Please try again.");
        }
        return Promise.reject(error);
    },
);

// Stale-while-revalidate GET cache: instant data on quick tab revisits + in-flight
// dedup (the Reports tab fires ~8 reads at once). Credit-free, purely client-side.
const _swrCache = new Map();
const _inflight = new Map();
function cget(url, ttl = 8000) {
    const hit = _swrCache.get(url);
    if (hit && Date.now() - hit.ts < ttl) return Promise.resolve(hit.data);
    if (_inflight.has(url)) return _inflight.get(url);
    const p = client
        .get(url)
        .then((r) => {
            _swrCache.set(url, { data: r.data, ts: Date.now() });
            _inflight.delete(url);
            return r.data;
        })
        .catch((e) => {
            _inflight.delete(url);
            if (hit) return hit.data; // serve stale on error rather than blanking the UI
            throw e;
        });
    _inflight.set(url, p);
    return p;
}

// Double-submit guard: coalesce identical, non-idempotent mutations that are still
// in flight (a double-click fires ONE request; both callers get the same promise —
// no duplicate order / close / approve / reset). Sequential calls after completion
// still work normally.
const _mutInflight = new Map();
function cmut(method, url, data) {
    const key = `${method}:${url}:${data !== undefined ? JSON.stringify(data) : ""}`;
    if (_mutInflight.has(key)) return _mutInflight.get(key);
    const req = data !== undefined ? client[method](url, data) : client[method](url);
    const p = req.then((r) => r.data).finally(() => _mutInflight.delete(key));
    _mutInflight.set(key, p);
    return p;
}

export const api = {
    health: () => client.get("/").then((r) => r.data),
    healthSelfcheck: () => client.get("/health/selfcheck").then((r) => r.data),
    accessRequest: (payload) => client.post("/access/request", payload).then((r) => r.data),
    accessRequests: (status) => cget(`/access/requests${status ? `?status=${status}` : ""}`, 5000),
    accessRequestAction: (id, action) => cmut("post", `/access/requests/${id}/${action}`),
    marketSnapshots: () => cget("/market/snapshots", 4000),
    portfolio: () => cget("/portfolio", 4000),
    resetPortfolio: () => cmut("post", "/portfolio/reset"),
    closePosition: (base) => cmut("post", `/positions/${base}/close`),
    trades: (limit = 50) => client.get(`/trades?limit=${limit}`).then((r) => r.data),
    reasoning: (limit = 50, symbol, executedOnly = false) => {
        const params = new URLSearchParams({ limit: String(limit) });
        if (symbol) params.set("symbol", symbol);
        if (executedOnly) params.set("executed_only", "true");
        return client.get(`/reasoning?${params}`).then((r) => r.data);
    },
    riskStatus: () => client.get("/risk/status").then((r) => r.data),
    settings: () => client.get("/settings").then((r) => r.data),
    updateSettings: (patch) => client.put("/settings", patch).then((r) => r.data),
    runCycle: () => client.post("/cycle/run").then((r) => r.data),
    candles: (symbol, timeframe = "1h", limit = 48) =>
        cget(`/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`, 60000),
    clearHistory: (alsoResetPortfolio = false) =>
        cmut("post", `/history/clear?also_reset_portfolio=${alsoResetPortfolio}`),
    runCycleSymbol: (symbol) => {
        // backend accepts base symbol like BTC -> BTC/USD, or BTC/USD encoded
        const base = symbol.split("/")[0];
        return client.post(`/cycle/run/${base}`).then((r) => r.data);
    },
    currentNews: () => client.get("/news/current").then((r) => r.data),
    analyticsPerformance: (excludeSynthetic = false) =>
        client
            .get(`/analytics/performance?exclude_synthetic=${excludeSynthetic ? "true" : "false"}`)
            .then((r) => r.data),
    analyticsGraduation: () => client.get("/analytics/graduation").then((r) => r.data),
    analyticsAiQuery: (question, sessionId, strategy) =>
        client.post("/analytics/ai_query", { question, session_id: sessionId, strategy }).then((r) => r.data),
    pendingOrders: () => client.get("/pending_orders").then((r) => r.data),
    getEnvironment: () => client.get("/environment").then((r) => r.data),
    setEnvironment: (mode) => client.post(`/environment/${mode}`).then((r) => r.data),
    manualOrder: (payload) => cmut("post", "/orders/manual", payload),
    anantaAsk: (question, sessionId, tab, strategy) => client.post("/ananta/ask", { question, session_id: sessionId, tab, strategy }).then((r) => r.data),
    backtestRun: (payload) => client.post("/backtest/run", payload).then((r) => r.data),
    // --- Competition Demo Workspace ---
    demoStatus: () => client.get("/admin/demo/status").then((r) => r.data),
    demoLoad: () => client.post("/admin/demo/load").then((r) => r.data),
    demoReset: () => client.post("/admin/demo/reset").then((r) => r.data),
    // --- AI Trading Coach ---
    coachReview: () => client.post("/coach/weekly-review").then((r) => r.data),
    coachHeadline: () => client.get("/coach/headline").then((r) => r.data),
    coachApply: (setting_key, value) => client.post("/coach/apply", { setting_key, value }).then((r) => r.data),
    coachTradesReview: (mode) => client.post("/coach/trades-review", { mode }).then((r) => r.data),
    // --- auth (Phase 3.5) ---
    login: (email, password) => client.post("/auth/login", { email, password }).then((r) => r.data),
    onboardingPaperSetup: (cfg) => client.post("/onboarding/paper-setup", cfg).then((r) => r.data),
    logout: () => client.post("/auth/logout").then((r) => r.data),
    me: () => client.get("/auth/me").then((r) => r.data),
    researchShadow: () => client.get("/research/shadow").then((r) => r.data),
    researchSummary: () => client.get("/research/summary").then((r) => r.data),
    researchRejections: (sinceHours) =>
        cget(`/research/rejections${sinceHours ? `?since_hours=${sinceHours}` : ""}`),
    researchFunnel: (sinceHours) =>
        cget(`/research/funnel${sinceHours ? `?since_hours=${sinceHours}` : ""}`),
    researchWinnerProfile: () => cget("/research/winner_profile"),
    researchMissedOpportunities: () => cget("/research/missed_opportunities"),
    researchRsiDistribution: () => cget("/research/rsi_distribution"),
    researchZoneEffectiveness: () => cget("/research/zone_effectiveness"),
    researchStrategySandbox: () => cget("/research/strategy_sandbox"),
    researchStrategyLab: () => cget("/research/strategy_lab"),
    freshStart: () => cmut("post", "/admin/fresh-start"),
    researchStagedExit: () => cget("/research/staged_exit"),
    // --- Research Lab (offline strategy validation) ---
    labCoverage: () => client.get("/lab/data/coverage").then((r) => r.data),
    labPresets: () => client.get("/lab/presets").then((r) => r.data),
    labCreateRun: (spec) => client.post("/lab/runs", spec).then((r) => r.data),
    labRuns: (limit = 20) => client.get(`/lab/runs?limit=${limit}`).then((r) => r.data),
    labRun: (id) => client.get(`/lab/runs/${id}`, { silent: true }).then((r) => r.data),
    labRunPdf: (id) => client.get(`/lab/runs/${id}/pdf`, { responseType: "blob" }).then((r) => r.data),
    labPropose: (runId) => client.post(`/lab/runs/${runId}/propose`).then((r) => r.data),
    deleteLabRun: (id) => client.delete(`/lab/runs/${id}`).then((r) => r.data),
    labApplyProposal: (pid) => client.post(`/lab/proposals/${pid}/apply`).then((r) => r.data),
    labRejectProposal: (pid) => client.post(`/lab/proposals/${pid}/reject`).then((r) => r.data),
    labMonteCarlo: (payload) => client.post("/lab/monte_carlo", payload).then((r) => r.data),
    // --- Strategy Config Engine (schemas + configs) ---
    strategyRegistry: () => client.get("/strategy/registry").then((r) => r.data),
    strategyMetrics: () => client.get("/strategy/metrics").then((r) => r.data),
    strategySetState: (key, payload) => client.put(`/strategy/${key}/state`, payload).then((r) => r.data),
    strategySchema: (key) => client.get(`/strategy/${key}/schema`).then((r) => r.data),
    strategyArchitectChat: (message, sessionId, history) =>
        client.post("/strategy/architect/chat", { message, session_id: sessionId, history }).then((r) => r.data),
    strategyConfigs: (key) => client.get(`/strategy/configs${key ? `?strategy_key=${key}` : ""}`).then((r) => r.data),
    strategyConfigGet: (id) => client.get(`/strategy/configs/${id}`).then((r) => r.data),
    strategyConfigCreate: (payload) => client.post("/strategy/configs", payload).then((r) => r.data),
    strategyConfigUpdate: (id, payload) => client.put(`/strategy/configs/${id}`, payload).then((r) => r.data),
    strategyConfigDelete: (id) => client.delete(`/strategy/configs/${id}`).then((r) => r.data),
    strategyConfigFromLabRun: (payload) => client.post("/strategy/configs/from-lab-run", payload).then((r) => r.data),
    strategyConfigActivate: (id) => client.post(`/strategy/configs/${id}/activate`).then((r) => r.data),
    strategyDeactivate: (key) => client.post(`/strategy/${key}/deactivate`).then((r) => r.data),
    strategyEffective: (key) => client.get(`/strategy/${key}/effective`).then((r) => r.data),
    strategyConfigImport: (payload) => client.post("/strategy/configs/import", payload).then((r) => r.data),
    strategyConfigExport: (id) => client.get(`/strategy/configs/${id}/export`).then((r) => r.data),
    analyticsLeaderboard: (sort = "health", source = "all") => client.get(`/analytics/leaderboard?sort=${sort}&source=${source}`).then((r) => r.data),
    // Strategy Library (P1)
    libraryList: (params = {}) => client.get("/library", { params }).then((r) => r.data),
    libraryGet: (id) => client.get(`/library/${id}`).then((r) => r.data),
    libraryBacktest: (id, symbol = "BTC/USD", days = 30) =>
        client.post(`/library/${id}/backtest`, null, { params: { symbol, days } }).then((r) => r.data),
    libraryFacets: () => client.get("/library/facets").then((r) => r.data),
    libraryFavorite: (id) => client.post(`/library/${id}/favorite`).then((r) => r.data),
    libraryAiGrade: (id) => client.post(`/library/${id}/ai-grade`).then((r) => r.data),
    // Strategy Import Pipeline (P2)
    importFormats: () => client.get("/library/import/formats").then((r) => r.data),
    importDetect: (raw_content) => client.post("/library/import/detect", { raw_content }).then((r) => r.data),
    importAnalyze: (payload) => client.post("/library/import/analyze", payload, { timeout: 120000 }).then((r) => r.data),
    importList: () => client.get("/library/imports").then((r) => r.data),
    importGet: (id) => client.get(`/library/imports/${id}`).then((r) => r.data),
    importUpdate: (id, patch) => client.put(`/library/imports/${id}`, { patch }).then((r) => r.data),
    importDelete: (id) => client.delete(`/library/imports/${id}`).then((r) => r.data),
    importApprove: (id) => cmut("post", `/library/imports/${id}/approve`),
    importBacktestPreview: (id, symbol = "BTC/USD", days = 30) =>
        client.post(`/library/imports/${id}/backtest-preview?symbol=${encodeURIComponent(symbol)}&days=${days}`).then((r) => r.data),
    // Active Watchlist
    watchlistSearch: (q = "") => client.get(`/watchlist/search?q=${encodeURIComponent(q)}`).then((r) => r.data),
    watchlistAdd: (symbol) => client.post("/watchlist/add", { symbol }).then((r) => r.data),
    watchlistRemove: (symbol) => client.post("/watchlist/remove", { symbol }).then((r) => r.data),
    watchlistValidate: () => cget("/watchlist/validate", 10000),
    watchlistSync: () =>
        client.post("/watchlist/sync").then((r) => {
            _swrCache.delete("/watchlist/validate");
            return r.data;
        }),
    researchLog: (symbol, limit = 1) => {
        const params = new URLSearchParams({ limit: String(limit) });
        if (symbol) params.set("symbol", symbol);
        return client.get(`/research/log?${params}`).then((r) => r.data);
    },
    levels: (base) => cget(`/levels/${base}`, 60000),
    // Promo — "Coming Soon to Ananta" banner
    promoStatus: () => client.get("/promo/coming-soon").then((r) => r.data),
    promoJoinWaitlist: (email) => client.post("/promo/coming-soon/waitlist", { email }).then((r) => r.data),
};

export default api;
