// Shared Academy lessons — used by the Workspace Academy list and deep-linked
// from a strategy ("Learn how this works"). Keeps web/mobile content in parity.

export type Lesson = { key: string; title: string; body: string };

export const LESSONS: Lesson[] = [
  { key: "start", title: "Getting Started", body: "Ananta is an operating system for algorithmic trading. Flow: Cockpit → Strategy → Research → Trade → Workspace. Pick a strategy, validate it, paper-trade, review with AI, then go live." },
  { key: "basics", title: "Trading Basics", body: "A strategy decides WHEN to enter and exit. Ananta trades spot crypto only — no leverage. Each closed trade has a P&L, return %, and an exit reason." },
  { key: "risk", title: "Risk Management", body: "Capital preservation first: a daily loss cap, max open positions, a min-confidence floor and a hard drawdown ruin line. The Emergency Stop blocks all new entries instantly." },
  { key: "hunter", title: "How Hunter Works", body: "Hunter hunts high-conviction setups: price tests support after a momentum reset, with a volatility-contraction base and confirming higher-timeframe trend. Exits via ATR trailing stop + profit floors." },
  { key: "squeeze", title: "How Squeeze Works", body: "Volatility Squeeze finds tight, coiled ranges; when volume expands and price breaks out, it enters in the breakout direction. Best in compression→expansion regimes." },
  { key: "continuation", title: "How Continuation Works", body: "Continuation rides an established trend: it waits for a shallow pullback within a confirmed uptrend, then enters as momentum resumes in the trend direction. It cuts quickly if the trend structure breaks." },
  { key: "ai", title: "How AI Thinks", body: "Ananta's AI (Architect, Analyst, Coach) is grounded — it reasons only over the real data snapshot, citing actual numbers. AI never trades on its own; it suggests, you decide." },
  { key: "wfa", title: "Walk-Forward", body: "Optimize on one slice of history, test on the next unseen slice, roll forward. A 'robust' verdict means the edge held out-of-sample — strong evidence it isn't curve-fit." },
  { key: "mc", title: "Monte Carlo", body: "Reshuffles your trade order thousands of times to estimate the RANGE of outcomes including worst-case drawdown and risk-of-ruin. Good strategies stay survivable in unlucky orderings." },
  { key: "paperlive", title: "Paper vs Live", body: "Paper trades run the full engine on live prices with fake money — zero risk, real behavior. Live places real orders. Always graduate through paper first." },
  { key: "faq", title: "FAQ & Best Practices", body: "Start small, validate rigorously, and let the AI Coach guide small incremental tweaks. Chase a validated edge, not more indicators. Review weekly; only go live when paper + validation agree." },
];

// Map a strategy key to its "how it works" lesson.
export const STRATEGY_LESSON: Record<string, string> = {
  hunter: "hunter",
  squeeze: "squeeze",
  continuation: "continuation",
};

export const lessonByKey = (key?: string): Lesson | undefined =>
  LESSONS.find((l) => l.key === key);

// Per-strategy plain-English guide powering the Strategy Detail page ("How it Works" + "Best Used In").
export type StrategyGuide = { how: string; purpose: string; worksBest: string; avoid: string };

export const STRATEGY_GUIDE: Record<string, StrategyGuide> = {
  hunter: { how: "Hunts high-conviction reversals: price tests structural support after a momentum reset, with a volatility-contraction base and a confirming higher-timeframe trend. Exits via ATR trailing stop + profit floors.", purpose: "Buy fear at support with confirmation", worksBest: "Reversals & strong uptrends", avoid: "Falling knives with no base" },
  squeeze: { how: "Finds tight, coiled ranges; when volume expands and price breaks the range, it enters in the breakout direction.", purpose: "Trade the expansion out of a squeeze", worksBest: "Compression → expansion", avoid: "Choppy, low-volume ranges" },
  continuation: { how: "Rides an established trend: waits for a shallow pullback inside a confirmed uptrend, then enters as momentum resumes. Cuts quickly if trend structure breaks.", purpose: "Buy dips inside a confirmed uptrend", worksBest: "Strong, orderly trends", avoid: "Deep pullbacks / trend breaks (falling knives)" },
  "ema-cross": { how: "Enters when a fast EMA crosses a slower EMA in the trade direction, filtered to its edge regimes. Fixed take-profit / stop-loss.", purpose: "Momentum shift via moving-average cross", worksBest: "Compression & range breakouts", avoid: "Whipsaw trends (chop)" },
  "time-series-momentum": { how: "Buys when recent returns are positive and persistent; exits on a fixed target/stop once momentum fades.", purpose: "Follow persistent short-term momentum", worksBest: "Compression", avoid: "Trend-down & noisy ranges" },
  "stochastic-momentum": { how: "Times entries with a stochastic momentum oscillator inside its allowed regimes; fixed TP/SL.", purpose: "Momentum timing with oscillator", worksBest: "Compression & range", avoid: "Strong trend-down" },
  supertrend: { how: "Follows the Supertrend line; flips direction with the band. Best kept to compression here.", purpose: "Trend rider via ATR band", worksBest: "Compression", avoid: "Noisy trend flips" },
  "donchian-breakout": { how: "Enters on a breakout of the N-period high/low channel.", purpose: "Channel breakout", worksBest: "Compression", avoid: "Trend-up chop (false breaks)" },
  "keltner-breakout": { how: "Breakout of the Keltner (ATR) channel around an EMA.", purpose: "Volatility-band breakout", worksBest: "Range", avoid: "Trending markets" },
  "atr-breakout": { how: "Enters when price expands beyond an ATR-scaled threshold.", purpose: "Volatility-expansion breakout", worksBest: "Trend-down", avoid: "Quiet, low-ATR conditions" },
  "rsi-momentum": { how: "Momentum entries from RSI thresholds. No proven edge in the last validation — off by default.", purpose: "RSI momentum", worksBest: "Under redesign", avoid: "All regimes (no edge yet)" },
  "macd-trend": { how: "Trend entries confirmed by MACD. No proven edge in the last validation — off by default.", purpose: "MACD trend confirmation", worksBest: "Under redesign", avoid: "All regimes (no edge yet)" },
  "bollinger-mr": { how: "Mean-reversion at Bollinger band extremes. Off by default.", purpose: "Band mean-reversion", worksBest: "Under redesign", avoid: "All regimes (no edge yet)" },
  "vwap-mr": { how: "Mean-reversion toward VWAP. Off by default.", purpose: "VWAP mean-reversion", worksBest: "Under redesign", avoid: "All regimes (no edge yet)" },
  turtle: { how: "Classic Donchian trend-following breakout system. Off by default pending re-validation.", purpose: "Trend-following breakout", worksBest: "Under redesign", avoid: "All regimes (no edge yet)" },
};

export const guideByKey = (key?: string): StrategyGuide => {
  return (key && STRATEGY_GUIDE[key]) || {
    how: "A rules-based strategy that decides when to enter and exit based on its indicators and regime filter.",
    purpose: "Rules-based entries & exits",
    worksBest: "Its configured regimes",
    avoid: "Regimes outside its edge",
  };
};
