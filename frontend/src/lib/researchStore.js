import { create } from "zustand";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import { registerPdf } from "@/lib/pdfRegistry";

// Poll long enough for multi-strategy runs (backend budget is minutes, not the old ~90s).
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ITERS = 240; // ~8 min per exit-method run

const EXIT_LABELS = { atr: "ATR Trailing", fixed: "Fixed Target" };

/**
 * Research Wizard store — lives outside React so an in-flight validation run
 * (and its results/step) survives tab navigation / component unmount.
 */
export const useResearchStore = create((set, get) => ({
    step: 0,
    strategies: [],
    assets: [],
    strat: [],
    showAllStrat: false,
    picked: [],
    period: "1m",
    timeframe: "1h",
    runMC: true,
    exitMethods: ["atr"], // default ATR; user can add "fixed" (run both)
    phase: "idle", // idle | running | done | error
    progress: 0,
    runs: [], // [{ method, label, result, mc, id }]
    metrics: {},
    loaded: false,

    // one-time reference data load
    init: () => {
        if (get().loaded) return;
        set({ loaded: true });
        api.strategyRegistry().then((d) => {
            set({ strategies: d.strategies || [] });
        }).catch(() => {});
        api.strategyMetrics().then((d) => set({ metrics: d?.metrics || {} })).catch(() => {});
        api.labCoverage().then((c) => {
            const avail = (c.symbols || []).filter((s) => s.bars_1h > 0).map((s) => s.symbol);
            set({ assets: avail });
            if (get().picked.length === 0) {
                const btc = avail.find((a) => a.startsWith("BTC"));
                set({ picked: btc ? [btc] : avail.slice(0, 1) });
            }
        }).catch(() => {});
    },

    setStep: (v) => set((st) => ({ step: typeof v === "function" ? v(st.step) : v })),
    setShowAllStrat: (v) => set((st) => ({ showAllStrat: typeof v === "function" ? v(st.showAllStrat) : v })),
    setPeriod: (period) => set({ period }),
    setTimeframe: (timeframe) => set({ timeframe }),
    setRunMC: (v) => set((st) => ({ runMC: typeof v === "function" ? v(st.runMC) : v })),
    toggleAsset: (s) => set((st) => ({ picked: st.picked.includes(s) ? st.picked.filter((x) => x !== s) : [...st.picked, s] })),
    toggleStrat: (k) => set((st) => ({ strat: st.strat.includes(k) ? st.strat.filter((x) => x !== k) : [...st.strat, k] })),
    // At least one exit method must stay selected; default falls back to ATR.
    toggleExitMethod: (m) => set((st) => {
        const has = st.exitMethods.includes(m);
        let next = has ? st.exitMethods.filter((x) => x !== m) : [...st.exitMethods, m];
        if (next.length === 0) next = ["atr"];
        return { exitMethods: next };
    }),

    _pollRun: async (id) => {
        let miss = 0;
        for (let i = 0; i < POLL_MAX_ITERS; i++) {
            await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
            if (get().phase !== "running") return null; // aborted
            let d;
            try {
                d = await api.labRun(id);
                miss = 0;
            } catch {
                // Transient network/5xx during a long run — keep polling silently.
                if (++miss >= 15) throw new Error("lost connection to run");
                continue;
            }
            const base = get()._progressBase || 0;
            const span = get()._progressSpan || 90;
            set({ progress: Math.max(base + 3, Math.min(base + span, base + (d.progress_pct || 0) / 100 * span)) });
            if (d.status === "DONE") return d.result;
            if (d.status === "ERROR" || d.status === "FAILED") throw new Error(d.error || "run failed");
        }
        throw new Error("timed out");
    },

    run: async () => {
        const { picked, period, timeframe, strat, runMC, exitMethods } = get();
        const methods = exitMethods.length ? exitMethods : ["atr"];
        set({ phase: "running", progress: 3, runs: [], step: 5 });
        const collected = [];
        try {
            for (let mi = 0; mi < methods.length; mi++) {
                const method = methods[mi];
                set({ _progressBase: (mi / methods.length) * 100, _progressSpan: (1 / methods.length) * 90 });
                const { id } = await api.labCreateRun({ kind: "backtest", symbols: picked, period, timeframe, strategies: strat, exit_method: method });
                const result = await get()._pollRun(id);
                if (get().phase !== "running") return;
                let mc = null;
                if (runMC) {
                    try { const m = await api.labMonteCarlo({ source: "run", run_id: id, iterations: 1500, ruin_threshold_pct: 25 }); if (m?.ok) mc = m; } catch { /* noop */ }
                }
                collected.push({ method, label: EXIT_LABELS[method] || method, result, mc, id, url: `${API}/lab/runs/${id}/pdf` });
                set({ runs: [...collected] });
                registerPdf({ title: `Research · ${strat.join(" + ")} · ${timeframe} · ${EXIT_LABELS[method] || method}`, type: "lab", url: `${API}/lab/runs/${id}/pdf` });
            }
            set({ progress: 100, phase: "done" });
            toast.success("Research PDF ready", { description: "Check Workspace › AI Analytics · Ananta PDFs" });
        } catch (e) {
            if (get().phase !== "running") return;
            set({ phase: "error" });
            toast.error("Backtest failed", { description: String(e?.response?.data?.detail || e?.message) });
        }
    },

    reset: () => set({ phase: "idle", step: 0, runs: [], progress: 0 }),
}));
