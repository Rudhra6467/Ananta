import { create } from "zustand";
import { toast } from "sonner";
import api, { API } from "@/lib/api";
import { registerPdf } from "@/lib/pdfRegistry";

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
    phase: "idle", // idle | running | done | error
    progress: 0,
    result: null,
    mc: null,
    metrics: {},
    loaded: false,

    // one-time reference data load
    init: () => {
        if (get().loaded) return;
        set({ loaded: true });
        api.strategyRegistry().then((d) => {
            const l = d.strategies || [];
            set({ strategies: l });
            if (l[0] && get().strat.length === 0) set({ strat: [l[0].key] });
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

    setStep: (step) => set({ step }),
    setShowAllStrat: (v) => set({ showAllStrat: v }),
    setPeriod: (period) => set({ period }),
    setTimeframe: (timeframe) => set({ timeframe }),
    setRunMC: (v) => set({ runMC: v }),
    toggleAsset: (s) => set((st) => ({ picked: st.picked.includes(s) ? st.picked.filter((x) => x !== s) : [...st.picked, s] })),
    toggleStrat: (k) => set((st) => ({ strat: st.strat.includes(k) ? st.strat.filter((x) => x !== k) : [...st.strat, k] })),

    run: async () => {
        const { picked, period, timeframe, strat, runMC } = get();
        set({ phase: "running", progress: 5, result: null, mc: null, step: 5 });
        try {
            const { id } = await api.labCreateRun({ kind: "backtest", symbols: picked, period, timeframe, strategies: strat, exit_method: "fixed" });
            let done = false;
            for (let i = 0; i < 60 && !done; i++) {
                await new Promise((r) => setTimeout(r, 1500));
                if (get().phase !== "running") return; // aborted via New Run / reset
                const d = await api.labRun(id);
                set({ progress: Math.max(10, Math.min(95, d.progress_pct || 0)) });
                if (d.status === "DONE") { set({ result: d.result }); done = true; }
                else if (d.status === "ERROR") { throw new Error(d.error || "run failed"); }
            }
            if (!done) throw new Error("timed out");
            if (get().phase !== "running") return;
            if (runMC) {
                try { const m = await api.labMonteCarlo({ source: "run", run_id: id, iterations: 1500, ruin_threshold_pct: 25 }); if (m?.ok) set({ mc: m }); } catch { /* noop */ }
            }
            set({ progress: 100, phase: "done" });
            registerPdf({ title: `Research · ${strat.join(" + ")} · ${timeframe}`, type: "lab", url: `${API}/lab/runs/${id}/pdf` });
            toast.success("Research PDF ready", { description: "Check Workspace › AI Analytics · Ananta PDFs" });
        } catch (e) {
            if (get().phase !== "running") return;
            set({ phase: "error" });
            toast.error("Backtest failed", { description: String(e?.response?.data?.detail || e?.message) });
        }
    },

    reset: () => set({ phase: "idle", step: 0, result: null, mc: null, progress: 0 }),
}));
