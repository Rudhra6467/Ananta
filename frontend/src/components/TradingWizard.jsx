import { useEffect, useState } from "react";
import { X, Rocket, CheckCircle2, Circle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

function Seg({ options, value, onChange, testid }) {
    return (
        <div className="flex bg-atlas-panelHover rounded-lg p-1 border border-atlas-border">
            {options.map(([k, l]) => (
                <button key={k} data-testid={`${testid}-${k}`} onClick={() => onChange(k)}
                    className={`flex-1 text-[11px] font-mono font-bold tracking-wider py-2 rounded-md transition-colors ${value === k ? "bg-atlas-cyan text-black" : "text-atlas-textSecondary hover:text-white"}`}>{l}</button>
            ))}
        </div>
    );
}

export default function TradingWizard({ open, onClose, onLaunched }) {
    const [step, setStep] = useState(0);
    const [mode, setMode] = useState("PAPER");
    const [strategies, setStrategies] = useState([]);
    const [selected, setSelected] = useState([]);
    const [method, setMethod] = useState("paper");
    const [split, setSplit] = useState("7030");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    useEffect(() => {
        if (!open) return;
        setStep(0); setSelected([]); setResult(null);
        api.strategyMetrics().then((d) => setStrategies(Object.values(d?.metrics || {}))).catch(() => {});
    }, [open]);

    if (!open) return null;

    const toggle = (k) => setSelected((s) => s.includes(k) ? s.filter((x) => x !== k) : (s.length >= 3 ? s : [...s, k]));

    const runBacktest = async () => {
        setBusy(true); setResult(null);
        try {
            const days = split === "100" ? 60 : 30;
            const r = await api.backtestRun({ symbols: ["BTC/USD", "ETH/USD", "SOL/USD"], days, starting_balance: 1200 });
            setResult(r);
        } catch (e) { toast.error("Backtest failed", { description: String(e?.message || e) }); }
        finally { setBusy(false); }
    };

    const launch = async () => {
        if (selected.length === 0) { toast.error("Pick at least one strategy"); return; }
        setBusy(true);
        try {
            await api.setEnvironment(mode);
            for (const k of selected) await api.strategySetState(k, { enabled: true });
            toast.success(`Launched ${selected.length} strategy(ies) in ${mode} mode`);
            onLaunched && onLaunched();
            onClose();
        } catch (e) { toast.error("Launch failed", { description: String(e?.message || e) }); }
        finally { setBusy(false); }
    };

    const next = () => {
        if (step === 1 && selected.length === 0) { toast.error("Pick 1-3 strategies"); return; }
        setStep((s) => Math.min(2, s + 1));
    };

    return (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" data-testid="trading-wizard" onClick={onClose}>
            <div className="panel border-atlas-border rounded-2xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between mb-1">
                    <div className="font-heading text-lg text-atlas-text">Trading Wizard</div>
                    <button data-testid="wizard-close" onClick={onClose} className="text-atlas-textSecondary hover:text-white"><X className="w-5 h-5" /></button>
                </div>
                <div className="flex gap-1.5 mb-5">{[0, 1, 2].map((i) => <div key={i} className={`h-1 w-8 rounded-full ${step >= i ? "bg-atlas-cyan" : "bg-atlas-border"}`} />)}</div>

                <div className="space-y-4 max-h-[50vh] overflow-y-auto atlas-scroll">
                    {step === 0 && (
                        <div className="space-y-2">
                            <div className="label-tag">EXECUTION MODE</div>
                            <Seg options={[["PAPER", "PAPER"], ["LIVE", "LIVE"]]} value={mode} onChange={setMode} testid="wizard-mode" />
                            <p className="font-mono text-[11px] text-atlas-textSecondary">Paper simulates fills. Live routes real orders once the exchange gate is armed.</p>
                        </div>
                    )}
                    {step === 1 && (
                        <div className="space-y-2">
                            <div className="label-tag">PICK 1-3 STRATEGIES ({selected.length}/3)</div>
                            {strategies.map((s) => {
                                const on = selected.includes(s.key);
                                return (
                                    <button key={s.key} data-testid={`wizard-strategy-${s.key}`} onClick={() => toggle(s.key)}
                                        className={`w-full flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition-colors ${on ? "border-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border hover:border-atlas-textTertiary"}`}>
                                        {on ? <CheckCircle2 className="w-5 h-5 text-atlas-cyan shrink-0" /> : <Circle className="w-5 h-5 text-atlas-textTertiary shrink-0" />}
                                        <div className="min-w-0">
                                            <div className="font-mono text-sm text-white font-bold truncate">{s.name}</div>
                                            <div className="font-mono text-[10px] text-atlas-textTertiary">{s.trades} trades · WR {s.win_rate}% · health {s.health}</div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                    {step === 2 && (
                        <div className="space-y-3">
                            <div className="label-tag">VALIDATION METHOD</div>
                            <Seg options={[["paper", "PAPER FORWARD"], ["backtest", "BACKTEST"]]} value={method} onChange={setMethod} testid="wizard-method" />
                            {method === "backtest" && (
                                <>
                                    <Seg options={[["7030", "70/30 SPLIT"], ["100", "100% HIST"]]} value={split} onChange={setSplit} testid="wizard-split" />
                                    <button data-testid="wizard-run-backtest" onClick={runBacktest} disabled={busy}
                                        className="w-full flex items-center justify-center gap-2 rounded-lg border border-atlas-cyan/40 text-atlas-cyan py-2.5 font-mono text-xs hover:bg-atlas-cyan/10 disabled:opacity-50">
                                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Run backtest preview"}
                                    </button>
                                    {result && (
                                        <div className="rounded-lg border border-atlas-border p-3 font-mono text-[12px] text-atlas-textSecondary space-y-1">
                                            <div>Net P&L: <span className="text-atlas-cyan font-bold">${(result?.total_pnl ?? result?.net_pnl ?? 0).toFixed?.(2) ?? "—"}</span></div>
                                            <div>Trades: {result?.total_trades ?? result?.trades ?? "—"} · Win rate: {result?.win_rate ?? "—"}%</div>
                                        </div>
                                    )}
                                </>
                            )}
                            {method === "paper" && <p className="font-mono text-[11px] text-atlas-textSecondary">Arms your selected strategies in a live paper simulation immediately.</p>}
                        </div>
                    )}
                </div>

                <div className="flex gap-2 mt-5">
                    {step > 0 && <button data-testid="wizard-back" onClick={() => setStep((s) => s - 1)} className="flex-1 rounded-lg border border-atlas-border text-atlas-textSecondary py-2.5 font-mono text-xs font-bold hover:text-white">Back</button>}
                    {step < 2 ? (
                        <button data-testid="wizard-next" onClick={next} className="flex-1 rounded-lg bg-atlas-cyan text-black py-2.5 font-mono text-xs font-bold">Next</button>
                    ) : (
                        <button data-testid="wizard-launch" onClick={launch} disabled={busy} className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-atlas-cyan text-black py-2.5 font-mono text-xs font-bold disabled:opacity-50">
                            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Rocket className="w-4 h-4" /> Launch</>}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
