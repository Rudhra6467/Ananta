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
