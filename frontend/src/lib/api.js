import axios from "axios";

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

export const api = {
    health: () => client.get("/").then((r) => r.data),
    marketSnapshots: () => cget("/market/snapshots", 4000),
    portfolio: () => cget("/portfolio", 4000),
    resetPortfolio: () => client.post("/portfolio/reset").then((r) => r.data),
    closePosition: (base) => client.post(`/positions/${base}/close`).then((r) => r.data),
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
        client
            .post(`/history/clear?also_reset_portfolio=${alsoResetPortfolio}`)
            .then((r) => r.data),
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
    pendingOrders: () => client.get("/pending_orders").then((r) => r.data),
    getEnvironment: () => client.get("/environment").then((r) => r.data),
    setEnvironment: (mode) => client.post(`/environment/${mode}`).then((r) => r.data),
    // --- auth (Phase 3.5) ---
    login: (email, password) => client.post("/auth/login", { email, password }).then((r) => r.data),
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
    freshStart: () => client.post("/admin/fresh-start").then((r) => r.data),
    researchStagedExit: () => cget("/research/staged_exit"),
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
};

export default api;
