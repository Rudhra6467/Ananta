// Ananta.AI mobile API client. Reuses the shared FastAPI /api backend.
import { getItem } from "./storage";

export const TOKEN_KEY = "ananta_owner_token";

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const token = await getItem(TOKEN_KEY);
  const h: Record<string, string> = { "Content-Type": "application/json", ...extra };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers = await authHeaders((opts.headers as Record<string, string>) || {});
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    const msg = typeof detail === "string" ? detail : `Request failed (${res.status})`;
    const err: any = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data as T;
}

const get = <T,>(p: string) => request<T>(p, { method: "GET" });
const post = <T,>(p: string, body?: any) =>
  request<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const put = <T,>(p: string, body?: any) =>
  request<T>(p, { method: "PUT", body: body ? JSON.stringify(body) : undefined });

export const api = {
  // auth
  login: (email: string, password: string) =>
    post<{ token: string; email: string; role: string }>("/auth/login", { email, password }),
  me: () => get<{ email: string; role: string }>("/auth/me"),

  // market + portfolio
  marketSnapshots: () => get<any>("/market/snapshots"),
  portfolio: () => get<any>("/portfolio"),
  closePosition: (base: string) => post<any>(`/positions/${base}/close`),
  manualOrder: (payload: Record<string, any>) => post<any>("/orders/manual", payload),
  anantaAsk: (question: string, sessionId?: string, tab?: string, strategy?: string) =>
    post<any>("/ananta/ask", { question, session_id: sessionId, tab, strategy }),
  backtestRun: (payload: Record<string, any>) => post<any>("/backtest/run", payload),
  candles: (symbol: string, timeframe = "1h", limit = 48) =>
    get<any>(`/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`),
  levels: (base: string) => get<any>(`/levels/${base}`),

  // engine / risk / env
  reasoning: (limit = 30, symbol?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (symbol) params.set("symbol", symbol);
    return get<any>(`/reasoning?${params.toString()}`);
  },
  riskStatus: () => get<any>("/risk/status"),
  getEnvironment: () => get<any>("/environment"),
  trades: (limit = 50) => get<any>(`/trades?limit=${limit}`),
  pendingOrders: () => get<any>("/pending_orders"),
  currentNews: () => get<any>("/news/current"),

  // analytics + research
  analyticsPerformance: (excludeSynthetic = false) =>
    get<any>(`/analytics/performance?exclude_synthetic=${excludeSynthetic ? "true" : "false"}`),
  researchStrategyLab: () => get<any>("/research/strategy_lab"),
  researchEntryQuality: () => get<any>("/research/entry_quality"),
  researchFunnel: (sinceHours?: number) =>
    get<any>(`/research/funnel${sinceHours ? `?since_hours=${sinceHours}` : ""}`),

  // settings
  settings: () => get<any>("/settings"),
  updateSettings: (patch: Record<string, any>) => put<any>("/settings", patch),
  setEnvironment: (mode: string) => post<any>(`/environment/${mode}`),

  // watchlist
  watchlistValidate: () => get<any>("/watchlist/validate"),

  // --- Strategy Center ---
  strategyMetrics: () => get<any>("/strategy/metrics"),
  strategyRegistry: () => get<any>("/strategy/registry"),
  strategySetState: (key: string, status: string) => put<any>(`/strategy/${key}/state`, { status }),
  strategyDeploy: (key: string) => put<any>(`/strategy/${key}/state`, { enabled: true }),
  strategyDisable: (key: string) => put<any>(`/strategy/${key}/state`, { status: "DISABLED" }),
  strategyConfigs: (strategyKey?: string) =>
    get<any>(`/strategy/configs${strategyKey ? `?strategy_key=${strategyKey}` : ""}`),
  strategyConfigActivate: (id: string) => post<any>(`/strategy/configs/${id}/activate`, {}),
  strategyDeactivate: (key: string) => post<any>(`/strategy/${key}/deactivate`, {}),
  strategyConfigImport: (payload: any) => post<any>("/strategy/configs/import", payload),
  strategyConfigExport: (id: string) => get<any>(`/strategy/configs/${id}/export`),
  // Strategy Library (P1)
  libraryList: (params: Record<string, any> = {}) => {
    const qs = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return get<any>(`/library${qs ? `?${qs}` : ""}`);
  },
  libraryGet: (id: string) => get<any>(`/library/${id}`),
  libraryBacktest: (id: string, symbol = "BTC/USD", days = 30) =>
    post<any>(`/library/${id}/backtest?symbol=${encodeURIComponent(symbol)}&days=${days}`, {}),
  libraryFacets: () => get<any>("/library/facets"),
  libraryFavorite: (id: string) => post<any>(`/library/${id}/favorite`, {}),
  libraryAiGrade: (id: string) => post<any>(`/library/${id}/ai-grade`, {}),
  // Strategy Import Pipeline (P2)
  importFormats: () => get<any>("/library/import/formats"),
  importDetect: (raw_content: string) => post<any>("/library/import/detect", { raw_content }),
  importAnalyze: (payload: any) => post<any>("/library/import/analyze", payload),
  importList: () => get<any>("/library/imports"),
  importUpdate: (id: string, patch: any) => put<any>(`/library/imports/${id}`, { patch }),
  importApprove: (id: string) => post<any>(`/library/imports/${id}/approve`, {}),
  importBacktestPreview: (id: string, symbol = "BTC/USD", days = 30) =>
    post<any>(`/library/imports/${id}/backtest-preview?symbol=${encodeURIComponent(symbol)}&days=${days}`, {}),
  analyticsLeaderboard: (sort = "health", source = "all") => get<any>(`/analytics/leaderboard?sort=${sort}&source=${source}`),
  watchlistSearch: (q = "") => get<any>(`/watchlist/search?q=${encodeURIComponent(q)}`),
  watchlistAdd: (symbol: string) => post<any>("/watchlist/add", { symbol }),
  watchlistRemove: (symbol: string) => post<any>("/watchlist/remove", { symbol }),

  // --- Research Lab ---
  labCoverage: () => get<any>("/lab/data/coverage"),
  labCreateRun: (spec: any) => post<any>("/lab/runs", spec),
  labRun: (id: string) => get<any>(`/lab/runs/${id}`),
  labMonteCarlo: (payload: any) => post<any>("/lab/monte_carlo", payload),

  // --- AI (owner, credits) ---
  aiQuery: (question: string, sessionId: string, strategy?: string) =>
    post<any>("/analytics/ai_query", { question, session_id: sessionId, strategy }),
  coachReview: () => post<any>("/coach/weekly-review"),
  coachHeadline: () => get<any>("/coach/headline"),
  coachApply: (setting_key: string, value: number) => post<any>("/coach/apply", { setting_key, value }),
  coachTradesReview: (mode: string) => post<any>("/coach/trades-review", { mode }),

  // --- Competition Demo (owner) ---
  demoStatus: () => get<any>("/admin/demo/status"),
  demoLoad: () => post<any>("/admin/demo/load"),
  demoReset: () => post<any>("/admin/demo/reset"),

  // Trade-history PDF url (open in browser via Linking)
  tradesPdfUrl: (mode: string) => `${API}/report/trades.pdf?mode=${mode}&inline=true`,

  // push
  registerPushToken: (push_token: string, platform: string, prefs?: Record<string, boolean>) =>
    post<any>("/notifications/register", { push_token, platform, prefs }),
};

export default api;
