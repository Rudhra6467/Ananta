// Lightweight formatting helpers shared across mobile screens.

export const usd = (n: number | null | undefined, dp = 2): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
};

export const pct = (n: number | null | undefined, dp = 2): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const s = n.toFixed(dp);
  return `${n > 0 ? "+" : ""}${s}%`;
};

export const signedUsd = (n: number | null | undefined, dp = 2): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${usd(n, dp)}`;
};

// Price formatting that scales decimal places to magnitude.
export const price = (n: number | null | undefined): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (n >= 1) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return n.toLocaleString("en-US", { maximumFractionDigits: 5 });
};

export const base = (symbol: string): string => (symbol || "").split("/")[0];

export const timeAgo = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
};

export const clockTime = (iso: string | null | undefined): string => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
};

export const duration = (seconds: number | null | undefined): string => {
  if (!seconds || seconds <= 0) return "—";
  const h = Math.floor(seconds / 3600);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  const rem = h % 24;
  return rem ? `${d}d ${rem}h` : `${d}d`;
};
