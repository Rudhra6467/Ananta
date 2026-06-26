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
  researchFunnel: (sinceHours?: number) =>
    get<any>(`/research/funnel${sinceHours ? `?since_hours=${sinceHours}` : ""}`),

  // settings
  settings: () => get<any>("/settings"),
  updateSettings: (patch: Record<string, any>) => put<any>("/settings", patch),
  setEnvironment: (mode: string) => post<any>(`/environment/${mode}`),

  // watchlist
  watchlistValidate: () => get<any>("/watchlist/validate"),

  // push
  registerPushToken: (push_token: string, platform: string) =>
    post<any>("/notifications/register", { push_token, platform }),
};

export default api;
