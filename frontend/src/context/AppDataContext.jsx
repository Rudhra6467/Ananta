import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import api from "@/lib/api";

/**
 * Single shared poller for the whole app. Pages read live state from here instead of
 * each mounting their own duplicate fetch loops — so the UI template paints instantly
 * (cached values are served synchronously) while fresh data streams in behind it.
 */
const AppDataContext = createContext(null);

export function AppDataProvider({ children }) {
    const [portfolio, setPortfolio] = useState(null);
    const [snapshots, setSnapshots] = useState([]);
    const [enabledSymbols, setEnabledSymbols] = useState([]);
    const [trades, setTrades] = useState([]);
    const [brain, setBrain] = useState(null);
    const [summary, setSummary] = useState(null);
    const [regime, setRegime] = useState("—");
    const [reasoning, setReasoning] = useState([]);
    const mounted = useRef(true);

    const refreshFast = useCallback(() => {
        api.marketSnapshots().then((s) => mounted.current && setSnapshots(s.snapshots || [])).catch(() => {});
        api.portfolio().then((p) => mounted.current && setPortfolio(p)).catch(() => {});
    }, []);

    const refreshSlow = useCallback(() => {
        api.settings().then((st) => st?.enabled_symbols && mounted.current && setEnabledSymbols(st.enabled_symbols)).catch(() => {});
        api.trades(300).then((t) => mounted.current && setTrades(t.items || [])).catch(() => {});
        api.researchRejections(24).then((b) => mounted.current && setBrain(b)).catch(() => {});
        api.researchSummary().then((s) => mounted.current && setSummary(s)).catch(() => {});
        api.reasoning(10).then((d) => {
            if (!mounted.current) return;
            setReasoning(d.items || []);
            if (d.items?.[0]) setRegime(d.items[0].bias || "NEUTRAL");
        }).catch(() => {});
    }, []);

    const refresh = useCallback(() => { refreshFast(); refreshSlow(); }, [refreshFast, refreshSlow]);

    useEffect(() => {
        mounted.current = true;
        refresh();
        const tFast = setInterval(refreshFast, 8000);
        const tSlow = setInterval(refreshSlow, 15000);
        return () => { mounted.current = false; clearInterval(tFast); clearInterval(tSlow); };
    }, [refresh, refreshFast, refreshSlow]);

    return (
        <AppDataContext.Provider value={{ portfolio, snapshots, enabledSymbols, trades, brain, summary, regime, reasoning, refresh }}>
            {children}
        </AppDataContext.Provider>
    );
}

export function useAppData() {
    const ctx = useContext(AppDataContext);
    if (!ctx) throw new Error("useAppData must be used within AppDataProvider");
    return ctx;
}
