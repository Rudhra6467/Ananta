import { useEffect, useState } from "react";
import { Check, Download, RefreshCw, X, Layers, Stethoscope, HelpCircle, Brain, Activity, Target, Gauge, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import api, { API, TOKEN_KEY } from "@/lib/api";
import ReasoningTimeline from "@/components/ReasoningTimeline";
import QuadrantCard from "@/components/lab/QuadrantCard";
import LabModal from "@/components/lab/LabModal";

const GATES = [
    { code: "REJECTED_NO_SUPPORT_ZONE", label: "Support Zone" },
    { code: "REJECTED_CHASING_GREEN_CANDLE", label: "Pullback Confirmed" },
    { code: "REJECTED_VOLUME_NOT_EXHAUSTED", label: "Volume Exhaustion" },
    { code: "REJECTED_RSI_NOT_RESET", label: "RSI Reset (≤35)" },
    { code: "REJECTED_SECONDARY_VETO_CATASTROPHE", label: "No Catastrophe Veto" },
];

const CODE_LABELS = {
    GREENLIT: "Greenlit (Qualified)",
    REJECTED_NO_SUPPORT_ZONE: "No Support Zone",
    REJECTED_CHASING_GREEN_CANDLE: "Chasing Green Candle",
    REJECTED_VOLUME_NOT_EXHAUSTED: "Volume Not Exhausted",
    REJECTED_RSI_NOT_RESET: "RSI Not Reset",
    REJECTED_SECONDARY_VETO_CATASTROPHE: "Catastrophe Veto",
    REJECTED_INSUFFICIENT_DATA: "Insufficient Data",
    REJECTED_HARD_KILL: "Hard Kill-Switch",
    REJECTED_MAX_POSITIONS: "Max Positions",
    REJECTED_COOLDOWN: "Cooldown Active",
    REJECTED_LOW_LIQUIDITY: "Low Liquidity",
    HOLD_NO_SIGNAL: "No Signal",
};

// Module-level cache so re-opening the Datalogs tab renders INSTANTLY from the last
// fetched data instead of showing empty/loading while 10 endpoints re-fetch. Data still
// refreshes silently in the background (and on the 20s interval).
const _reportsCache = {
    rejections: null, funnel: null, winners: null, missed: null, rsiDist: null,
    zones: null, sandbox: null, staged: null, summary: null, items: [], symbols: [], selected: null,
};

export default function Reports() {
    const [symbols, setSymbols] = useState(_reportsCache.symbols);
    const [selected, setSelected] = useState(_reportsCache.selected);
    const [whyRow, setWhyRow] = useState(null);
    const [rejections, setRejections] = useState(_reportsCache.rejections);
    const [funnel, setFunnel] = useState(_reportsCache.funnel);
    const [winners, setWinners] = useState(_reportsCache.winners);
    const [missed, setMissed] = useState(_reportsCache.missed);
    const [rsiDist, setRsiDist] = useState(_reportsCache.rsiDist);
    const [zones, setZones] = useState(_reportsCache.zones);
    const [sandbox, setSandbox] = useState(_reportsCache.sandbox);
    const [staged, setStaged] = useState(_reportsCache.staged);
    const [summary, setSummary] = useState(_reportsCache.summary);
    const [items, setItems] = useState(_reportsCache.items);

    const refresh = () => {
        api.researchRejections().then((d) => { _reportsCache.rejections = d; setRejections(d); }).catch(() => {});
        api.researchFunnel().then((d) => { _reportsCache.funnel = d; setFunnel(d); }).catch(() => {});
        api.researchWinnerProfile().then((d) => { _reportsCache.winners = d; setWinners(d); }).catch(() => {});
        api.researchMissedOpportunities().then((d) => { _reportsCache.missed = d; setMissed(d); }).catch(() => {});
        api.researchRsiDistribution().then((d) => { _reportsCache.rsiDist = d; setRsiDist(d); }).catch(() => {});
        api.researchZoneEffectiveness().then((d) => { _reportsCache.zones = d; setZones(d); }).catch(() => {});
        api.researchStrategyLab().then((d) => { _reportsCache.sandbox = d; setSandbox(d); }).catch(() => {});
        api.researchStagedExit().then((d) => { _reportsCache.staged = d; setStaged(d); }).catch(() => {});
        api.researchSummary().then((d) => { _reportsCache.summary = d; setSummary(d); }).catch(() => {});
        api.reasoning(15, undefined, false).then((d) => { _reportsCache.items = d.items || []; setItems(d.items || []); }).catch(() => setItems([]));
    };

    useEffect(() => {
        api.settings().then((st) => {
            const syms = st?.enabled_symbols || [];
            _reportsCache.symbols = syms;
            setSymbols(syms);
            if (!_reportsCache.selected && syms.length) { _reportsCache.selected = syms[0]; setSelected(syms[0]); }
        }).catch(() => {});
        refresh();
        const t = setInterval(refresh, 20000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        if (!selected) return;
        _reportsCache.selected = selected;
        api.researchLog(selected, 1).then((d) => setWhyRow(d.items?.[0] || null)).catch(() => setWhyRow(null));
    }, [selected]);

    const downloadPdf = () => {
        window.open(`${API}/report/reasoning.pdf?limit=200`, "_blank");
        toast.success("PDF DOWNLOAD STARTED");
    };

    const isOwner = typeof window !== "undefined" && !!localStorage.getItem(TOKEN_KEY);
    const freshStart = async () => {
        if (!window.confirm("FRESH START: wipe ALL trade & strategy history and reset the paper book to $1200 ($75/trade). This cannot be undone. Continue?")) return;
        try {
            const r = await api.freshStart();
            toast.success(`Fresh start done — $${r.starting_balance} book, $${r.lot_usd}/trade`);
            setTimeout(refresh, 600);
        } catch (e) {
            toast.error("Fresh start failed (owner login required)");
        }
    };

    const [openModal, setOpenModal] = useState(null); // 'dist' | 'diag' | 'why' | 'ai'

    // ---- face metrics (localized) ----
    const strategies = sandbox?.strategies || [];
    const topStrat = strategies[0]?.label || strategies[0]?.name || strategies[0]?.strategy || "—";
    const breaker = funnel?.breaker_accuracy;
    const breakerRows = breaker ? Object.keys(breaker).length : 0;
    const rejCount = rejections?.rejection_leaderboard?.length ?? (Array.isArray(rejections) ? rejections.length : 0);
    const latest = (items && items[0]) || null;
    const latestDecision = latest ? (latest.absolute_decision || latest.decision || "—") : "—";
    const whyDecision = whyRow ? (whyRow.absolute_decision || whyRow.decision || "—") : "—";
    const whyConf = whyRow?.macro_confidence != null ? Number(whyRow.macro_confidence).toFixed(2) : "—";
    const decCls = (d) => /BUY|EXECUTE/i.test(d) ? "text-atlas-positive" : /SELL|REJECT/i.test(d) ? "text-atlas-negative" : "text-atlas-text";

    return (
        <div className="space-y-5 pb-24" data-testid="reports-page">
            {/* header controls */}
            <div className="flex items-center justify-end flex-wrap gap-2">
                {isOwner && (
                    <button data-testid="reports-fresh-start" onClick={freshStart}
                        className="font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative/10 transition-colors rounded-lg">
                        FRESH START
                    </button>
                )}
                <button data-testid="reports-download-pdf" onClick={downloadPdf}
                    className="flex items-center gap-2 font-mono text-[10px] tracking-widest font-bold px-3 py-2 border border-atlas-border hover:border-atlas-cyan hover:text-atlas-text transition-colors text-atlas-textSecondary rounded-lg">
                    <Download className="w-3 h-3" /> PDF
                </button>
                <button data-testid="reports-refresh" onClick={refresh}
                    className="font-mono text-[10px] text-atlas-textSecondary hover:text-atlas-text flex items-center gap-2 transition-colors px-3 py-2 border border-atlas-border rounded-lg">
                    <RefreshCw className="w-3 h-3" /> REFRESH
                </button>
            </div>

            {/* 2×2 cockpit grid */}
            <div className="grid grid-cols-2 gap-3 md:gap-5" data-testid="logs-grid">
                {/* Q1 — Strategy Distributions */}
                <QuadrantCard
                    testid="quad-distributions" icon={Layers} accent="violet"
                    title="Strategy Distributions" subtitle="Sandbox · Attrition · RSI"
                    stats={[{ testid: "face-strat-count", label: "Strategies Tracked", value: strategies.length || "—", valueCls: "text-violet-400" }]}
                    rows={[
                        { testid: "face-top-strat", icon: TrendingUp, label: "Top by EV", value: typeof topStrat === "string" ? topStrat.slice(0, 16) : "—" },
                        { testid: "face-funnel", icon: Activity, label: "Attrition Funnel", value: strategies.length ? "Live" : "—", valueCls: strategies.length ? "text-atlas-positive" : "text-atlas-textTertiary" },
                        { testid: "face-conf-dist", icon: Gauge, label: "Confidence Study", value: summary ? "Ready" : "—", valueCls: summary ? "text-atlas-positive" : "text-atlas-textTertiary" },
                    ]}
                    cta="Open Distributions" onOpen={() => setOpenModal("dist")}
                />

                {/* Q2 — Diagnosis */}
                <QuadrantCard
                    testid="quad-diagnosis" icon={Stethoscope} accent="amber"
                    title="Diagnosis" subtitle="Winners · Breakers · Zones"
                    stats={[{ testid: "face-breaker", label: "Breaker Accuracy", value: breakerRows ? `${breakerRows} states` : "—", valueCls: "text-atlas-warning" }]}
                    rows={[
                        { testid: "face-rejections", icon: X, label: "Rejections Logged", value: rejCount || "—" },
                        { testid: "face-winner", icon: Target, label: "Winner Profile", value: winners?.sample ? "Ready" : "—", valueCls: winners?.sample ? "text-atlas-positive" : "text-atlas-textTertiary" },
                        { testid: "face-staged", icon: Layers, label: "33/66/99 Stops", value: staged?.sample ? "Ready" : "—", valueCls: staged?.sample ? "text-atlas-positive" : "text-atlas-textTertiary" },
                    ]}
                    cta="Open Diagnosis" onOpen={() => setOpenModal("diag")}
                />

                {/* Q3 — Why No Trade */}
                <QuadrantCard
                    testid="quad-why" icon={HelpCircle} accent="cyan"
                    title="Why No Trade?" subtitle="Per-Symbol Decision Trace"
                    stats={[{ testid: "face-why-symbol", label: "Symbol", value: selected ? selected.split("/")[0] : "—", valueCls: "text-atlas-cyan" }]}
                    rows={[
                        { testid: "face-why-decision", icon: Activity, label: "Last Decision", value: whyDecision, valueCls: decCls(whyDecision) },
                        { testid: "face-why-conf", icon: Gauge, label: "Macro Confidence", value: whyConf },
                    ]}
                    cta="Open Why-No-Trade" onOpen={() => setOpenModal("why")}
                />

                {/* Q4 — AI Log */}
                <QuadrantCard
                    testid="quad-ai" icon={Brain} accent="green"
                    title="AI Log" subtitle="Reasoning Timeline"
                    stats={[{ testid: "face-ai-count", label: "Recent Evaluations", value: (items || []).length || "—", valueCls: "text-atlas-positive" }]}
                    rows={[
                        { testid: "face-ai-latest", icon: TrendingUp, label: "Latest", value: latest ? `${(latest.symbol || "—").split("/")[0]} · ${latestDecision}` : "—", valueCls: decCls(latestDecision) },
                    ]}
                    cta="Open AI Log" onOpen={() => setOpenModal("ai")}
                />
            </div>

            {/* Q1 modal */}
            <LabModal open={openModal === "dist"} onOpenChange={(o) => setOpenModal(o ? "dist" : null)}
                testid="dist-modal" icon={Layers} accent="violet" title="Strategy Distributions" subtitle="Sandbox · Attrition · RSI · Confidence">
                <Block title="Strategy Research Laboratory"><StrategyLab data={sandbox} /></Block>
                <Block title="Signal Attrition Funnel"><StrategyFunnel data={sandbox} /></Block>
                <Block title="RSI Distribution Study"><RsiDistribution data={rsiDist} /></Block>
                <Block title="Confidence Distribution"><ConfidenceDistribution summary={summary} /></Block>
            </LabModal>

            {/* Q2 modal */}
            <LabModal open={openModal === "diag"} onOpenChange={(o) => setOpenModal(o ? "diag" : null)}
                testid="diag-modal" icon={Stethoscope} accent="amber" title="Diagnosis" subtitle="Winners · Breakers · Zones · Rejections">
                <Block title="Winning Trade Profile"><WinnerProfile data={winners} /></Block>
                <Block title="Circuit Breaker Accuracy"><BreakerAccuracy breaker={funnel?.breaker_accuracy} /></Block>
                <Block title="33 / 66 / 99 Stop Simulation"><StagedExitCard data={staged} /></Block>
                <Block title="Missed-Opportunity Analysis"><MissedOpportunities data={missed} /></Block>
                <Block title="Support-Zone Effectiveness"><ZoneEffectiveness data={zones} /></Block>
                <Block title="Rejection Leaderboard"><RejectionLeaderboard rejections={rejections} /></Block>
            </LabModal>

            {/* Q3 modal */}
            <LabModal open={openModal === "why"} onOpenChange={(o) => setOpenModal(o ? "why" : null)}
                testid="why-modal" icon={HelpCircle} accent="cyan" title="Why No Trade?" subtitle="Per-Symbol Decision Trace">
                <WhyNoTrade symbols={symbols} selected={selected} onSelect={setSelected} row={whyRow} />
            </LabModal>

            {/* Q4 modal */}
            <LabModal open={openModal === "ai"} onOpenChange={(o) => setOpenModal(o ? "ai" : null)}
                testid="ai-modal" icon={Brain} accent="green" title="AI Log" subtitle="Reasoning Timeline · Latest 15">
                <div className="max-h-full overflow-y-auto atlas-scroll" data-testid="reasoning-scroll-container">
                    <ReasoningTimeline items={items} />
                </div>
            </LabModal>
        </div>
    );
}

// Thin titled wrapper so modal sub-sections stay visually separated (replaces the accordions).
function Block({ title, children }) {
    return (
        <div className="panel border-atlas-border rounded-xl overflow-hidden" data-testid={`block-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`}>
            <div className="px-4 py-2.5 border-b border-atlas-border label-tag">{title}</div>
            <div>{children}</div>
        </div>
    );
}

/* ---------------- Confidence Distribution (relocated from Cockpit) ---------------- */
function ConfidenceDistribution({ summary }) {
    const buckets = summary?.confidence_buckets || [];
    const max = Math.max(1, ...buckets.map((b) => b.count || 0));
    const empty = buckets.length === 0 || buckets.every((b) => !b.count);
    return (
        <div className="p-6" data-testid="confidence-distribution">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-0.5 mb-4">Setups logged per LLM confidence bucket</div>
            {empty ? (
                <div className="py-10 text-center font-mono text-xs text-atlas-textSecondary">No setups logged yet for this sprint.</div>
            ) : (
                <div className="space-y-3">
                    {buckets.map((b) => (
                        <div key={b.bucket} data-testid={`conf-bucket-${b.bucket}`}>
                            <div className="flex items-center justify-between font-mono text-[11px] mb-1">
                                <span className="text-atlas-textSecondary">{b.bucket}</span>
                                <span className="text-atlas-text tabular-nums">{b.count || 0}</span>
                            </div>
                            <div className="h-2.5 bg-atlas-bg rounded overflow-hidden">
                                <div className="h-full bg-atlas-cyan/70 rounded transition-all" style={{ width: `${((b.count || 0) / max) * 100}%` }} />
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

/* ---------------- Why No Trade? ---------------- */
function WhyNoTrade({ symbols, selected, onSelect, row }) {
    const codes = row?.reason_codes || [];
    const greenlit = codes.includes("GREENLIT");
    const insufficient = codes.includes("REJECTED_INSUFFICIENT_DATA");

    return (
        <div className="p-6" data-testid="why-no-trade">
            <div className="flex items-center justify-end mb-4">
                <div className="flex gap-1 flex-wrap justify-end">
                    {symbols.map((s) => {
                        const base = s.split("/")[0];
                        return (
                            <button key={s} data-testid={`why-asset-${base}`} onClick={() => onSelect(s)}
                                className={`font-mono text-[10px] font-bold px-2 py-1 rounded border transition-colors ${
                                    selected === s ? "border-atlas-cyan text-atlas-text bg-atlas-panelHover" : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text"
                                }`}>{base}</button>
                        );
                    })}
                </div>
            </div>

            {!row && <div className="font-mono text-xs text-atlas-textSecondary py-6 text-center">No evaluation logged yet for {selected}.</div>}

            {row && insufficient && <div className="font-mono text-xs text-atlas-textSecondary py-6 text-center">Insufficient 4H data to evaluate {selected}.</div>}

            {row && !insufficient && (
                <>
                    <div className="space-y-0 border border-atlas-border rounded-md overflow-hidden">
                        {GATES.map((g) => {
                            const passed = !codes.includes(g.code);
                            return (
                                <div key={g.code} className="flex items-center justify-between px-4 py-3 border-b border-atlas-border last:border-b-0 font-mono text-sm" data-testid={`gate-${g.code}`}>
                                    <span className="text-atlas-textSecondary">{g.label}</span>
                                    {passed
                                        ? <span className="flex items-center gap-1.5 text-atlas-positive font-bold"><Check className="w-4 h-4" /> PASS</span>
                                        : <span className="flex items-center gap-1.5 text-atlas-negative font-bold"><X className="w-4 h-4" /> FAIL</span>}
                                </div>
                            );
                        })}
                    </div>
                    <div className="mt-4 flex items-center justify-between font-mono text-sm">
                        <span className="label-tag">RESULT</span>
                        <span className={`font-bold tracking-wider ${greenlit ? "text-atlas-positive" : "text-atlas-negative"}`} data-testid="why-result">
                            {greenlit ? "QUALIFIED · TRADE" : "NO TRADE"}
                        </span>
                    </div>
                </>
            )}
        </div>
    );
}

/* ---------------- Strategy Research Laboratory ---------------- */
function Delta({ v, suffix = "", invert = false }) {
    if (v == null) return <span className="text-atlas-textTertiary text-[9px]"> </span>;
    const good = invert ? v < 0 : v > 0;
    const neutral = v === 0;
    const cls = neutral ? "text-atlas-textTertiary" : good ? "text-atlas-positive" : "text-atlas-negative";
    return <span className={`text-[9px] ${cls}`}> ({v >= 0 ? "+" : ""}{v}{suffix})</span>;
}

function StrategyLab({ data }) {
    const strategies = data?.strategies || [];
    const promote = data?.promote_threshold ?? 20;
    return (
        <div className="p-6" data-testid="strategy-lab">
            <div className="flex items-baseline justify-end flex-wrap gap-2">
                <div className="font-mono text-[10px] text-atlas-textTertiary">Sorted by Expected Value · Hunter = benchmark · {data?.window_days ?? 30}d window</div>
            </div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Evidence-based promotion: a strategy must BEAT Hunter on Win% · AvgRet · EV · PF</div>
            {strategies.length === 0 ? <ResearchEmpty testid="strategy-lab-empty" label="pipelines warming up — data accumulates as signals resolve (7d)." /> : (
                <div className="overflow-x-auto atlas-scroll">
                    <table className="w-full font-mono text-sm whitespace-nowrap">
                        <thead><tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left py-2">Strategy</th>
                            <th className="text-right py-2">Det.</th>
                            <th className="text-right py-2">Qual.</th>
                            <th className="text-right py-2">Qual%</th>
                            <th className="text-right py-2">Resolved</th>
                            <th className="text-right py-2">Win%</th>
                            <th className="text-right py-2">AvgRet</th>
                            <th className="text-right py-2">EV</th>
                            <th className="text-right py-2">PF</th>
                            <th className="text-left py-2 pl-4">Verdict</th>
                        </tr></thead>
                        <tbody>
                            {strategies.map((x) => (
                                <tr key={x.id} className="border-t border-atlas-border" data-testid={`lab-row-${x.id}`}>
                                    <td className="py-2.5 text-atlas-text">
                                        <div className="font-bold flex items-center gap-2">
                                            {x.name.split(" / ")[0]}
                                            <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded ${x.mode === "EXECUTE" ? "bg-atlas-positive/15 text-atlas-positive" : "bg-atlas-border text-atlas-textSecondary"}`}>{x.mode}</span>
                                        </div>
                                        <div className="text-[9px] text-atlas-textTertiary uppercase">{x.scenario}</div>
                                    </td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-textSecondary">{x.detected}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-text">{x.qualified}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-textSecondary">{x.qualification_rate_pct == null ? "—" : `${x.qualification_rate_pct}%`}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-textSecondary">{x.resolved}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-text">
                                        {x.win_rate_pct == null ? "—" : `${x.win_rate_pct}%`}
                                        {x.id !== "hunter" && <Delta v={x.vs_hunter?.win_rate} suffix="" />}
                                    </td>
                                    <td className={`py-2.5 text-right tabular-nums ${x.avg_return_pct == null ? "text-atlas-textTertiary" : x.avg_return_pct >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        {x.avg_return_pct == null ? "—" : `${x.avg_return_pct >= 0 ? "+" : ""}${x.avg_return_pct}%`}
                                    </td>
                                    <td className={`py-2.5 text-right tabular-nums ${x.expected_value_pct == null ? "text-atlas-textTertiary" : x.expected_value_pct >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        {x.expected_value_pct == null ? "—" : `${x.expected_value_pct >= 0 ? "+" : ""}${x.expected_value_pct}%`}
                                    </td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-text">{x.profit_factor == null ? "—" : x.profit_factor}</td>
                                    <td className="py-2.5 pl-4 text-[10px]">
                                        {x.verdict === "PROMOTION CANDIDATE"
                                            ? <span className="text-atlas-positive font-bold">{x.verdict}</span>
                                            : x.verdict === "Benchmark"
                                                ? <span className="text-atlas-cyan font-bold">{x.verdict}</span>
                                                : <span className="text-atlas-textSecondary">{x.verdict}</span>}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="text-[9px] text-atlas-textTertiary font-mono mt-3">Need ≥{promote} resolved signals before a promotion verdict is issued.</div>
                </div>
            )}
        </div>
    );
}

/* ---------------- Signal Attrition Funnel (per strategy) ---------------- */
function StrategyFunnel({ data }) {
    const strategies = data?.strategies || [];
    const STAGES = [
        { key: "detected", label: "Detected", color: "bg-atlas-textTertiary/40" },
        { key: "qualified", label: "Qualified", color: "bg-atlas-cyan/50" },
        { key: "breaker_pass", label: "Breaker Pass", color: "bg-atlas-cyan/70" },
        { key: "resolved", label: "Resolved", color: "bg-atlas-cyan" },
        { key: "wins", label: "Wins", color: "bg-atlas-positive" },
    ];
    return (
        <div className="p-6" data-testid="strategy-funnel">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Where opportunities die: Detected → Qualified → Breaker → Resolved → Wins</div>
            {strategies.length === 0 ? <ResearchEmpty testid="strategy-funnel-empty" label="awaiting detections." /> : (
                <div className="space-y-4">
                    {strategies.map((x) => {
                        const max = Math.max(1, x.detected || 0);
                        return (
                            <div key={x.id} data-testid={`funnel-row-${x.id}`}>
                                <div className="flex items-center justify-between mb-1">
                                    <span className="font-mono text-[11px] text-atlas-text font-bold">{x.name.split(" / ")[0]}</span>
                                    <span className="font-mono text-[9px] text-atlas-textTertiary">{x.detected} detected</span>
                                </div>
                                <div className="flex gap-1 items-end h-10">
                                    {STAGES.map((st) => {
                                        const val = x[st.key] || 0;
                                        const pct = Math.round((val / max) * 100);
                                        return (
                                            <div key={st.key} className="flex-1 flex flex-col items-center justify-end h-full" title={`${st.label}: ${val}`}>
                                                <span className="font-mono text-[9px] text-atlas-textSecondary tabular-nums">{val}</span>
                                                <div className={`w-full rounded-sm ${st.color}`} style={{ height: `${Math.max(4, pct)}%` }} />
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className="flex gap-1 mt-1">
                                    {STAGES.map((st) => (
                                        <div key={st.key} className="flex-1 text-center font-mono text-[8px] text-atlas-textTertiary uppercase truncate">{st.label}</div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

/* ---------------- Staged-Exit (33/66/99) comparison card ---------------- */
function StagedExitCard({ data }) {
    const hasData = data && data.sample > 0;
    return (
        <div className="p-6 flex flex-col" data-testid="staged-exit-card">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Structure-staged exit vs current hard stop</div>
            {!hasData ? <ResearchEmpty testid="staged-exit-empty" label="needs closed positions." /> : (
                <div className="space-y-4 font-mono">
                    <div className="flex justify-between items-baseline">
                        <span className="text-[10px] uppercase tracking-wider text-atlas-textSecondary">Actual (current)</span>
                        <span className={`text-lg tabular-nums font-bold ${data.actual_pnl_total >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{data.actual_pnl_total >= 0 ? "+" : ""}${data.actual_pnl_total}</span>
                    </div>
                    <div className="flex justify-between items-baseline">
                        <span className="text-[10px] uppercase tracking-wider text-atlas-textSecondary">Staged (33/33/34)</span>
                        <span className={`text-lg tabular-nums font-bold ${data.staged_pnl_total >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{data.staged_pnl_total >= 0 ? "+" : ""}${data.staged_pnl_total}</span>
                    </div>
                    <div className="pt-3 border-t border-atlas-border flex justify-between items-baseline">
                        <span className="text-[10px] uppercase tracking-wider text-atlas-textTertiary">Delta</span>
                        <span className={`text-base tabular-nums font-bold ${data.delta_total >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{data.delta_total >= 0 ? "+" : ""}${data.delta_total}</span>
                    </div>
                    <div className="text-[10px] text-atlas-textSecondary">{data.verdict} · {data.sample} closed · staged better in {data.staged_better_count}</div>
                </div>
            )}
        </div>
    );
}

/* ---------------- Phase B research panels ---------------- */
const fmtNum = (v, suf = "") => (v == null ? "—" : `${v >= 0 && suf === "%" ? "+" : ""}${v}${suf}`);

function ResearchEmpty({ testid, label }) {
    return (
        <div className="font-mono text-[11px] text-atlas-textSecondary py-6 text-center" data-testid={testid}>
            Accumulating data… {label}
        </div>
    );
}

function WinnerProfile({ data }) {
    const rows = [
        ["RSI at entry", data?.winners?.avg_rsi, data?.losers?.avg_rsi],
        ["Dist. from 50% (%)", data?.winners?.avg_distance_from_midpoint_pct, data?.losers?.avg_distance_from_midpoint_pct],
        ["Rel. strength vs BTC", data?.winners?.avg_relative_strength, data?.losers?.avg_relative_strength],
        ["Support zone score", data?.winners?.avg_support_zone_score, data?.losers?.avg_support_zone_score],
        ["MFE (%)", data?.winners?.avg_mfe_pct, data?.losers?.avg_mfe_pct],
        ["MAE (%)", data?.winners?.avg_mae_pct, data?.losers?.avg_mae_pct],
    ];
    const hasData = data && data.sample > 0;
    return (
        <div className="p-6" data-testid="winner-profile">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">
                Measure, don&apos;t assume — what&apos;s actually present in winners vs losers{hasData ? ` · win rate ${data.win_rate_pct}% · N=${data.sample}` : ""}
            </div>
            {!hasData ? <ResearchEmpty testid="winner-profile-empty" label="needs closed trades to populate." /> : (
                <table className="w-full font-mono text-sm">
                    <thead><tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                        <th className="text-left py-2">Feature</th><th className="text-right py-2 text-atlas-positive">Winners</th><th className="text-right py-2 text-atlas-negative">Losers</th>
                    </tr></thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r[0]} className="border-t border-atlas-border">
                                <td className="py-2 text-atlas-textSecondary">{r[0]}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-text">{fmtNum(r[1])}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-text">{fmtNum(r[2])}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function RsiDistribution({ data }) {
    const buckets = data?.buckets || [];
    const hasData = buckets.some((b) => b.count > 0);
    return (
        <div className="p-6" data-testid="rsi-distribution">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Forward outcomes per RSI band — is RSI≤35 optimal? (no threshold change)</div>
            {!hasData ? <ResearchEmpty testid="rsi-distribution-empty" label="needs resolved counterfactuals." /> : (
                <table className="w-full font-mono text-sm">
                    <thead><tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                        <th className="text-left py-2">Band</th><th className="text-right py-2">N</th><th className="text-right py-2">Win%</th><th className="text-right py-2">Avg Ret</th><th className="text-right py-2">Avg DD</th>
                    </tr></thead>
                    <tbody>
                        {buckets.map((b) => (
                            <tr key={b.bucket} className="border-t border-atlas-border">
                                <td className="py-2 text-atlas-text">{b.bucket}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-textSecondary">{b.count}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-text">{b.win_rate_pct}%</td>
                                <td className={`py-2 text-right tabular-nums ${(b.avg_return_pct || 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{fmtNum(b.avg_return_pct, "%")}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-negative/80">{fmtNum(b.avg_drawdown_pct, "%")}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function MissedOpportunities({ data }) {
    const buckets = data?.buckets || [];
    const hasData = buckets.some((b) => b.rejected_resolved > 0);
    return (
        <div className="p-6" data-testid="missed-opportunities">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Which filters protect capital vs which are over-restrictive</div>
            {!hasData ? <ResearchEmpty testid="missed-opportunities-empty" label="needs resolved rejections." /> : (
                <table className="w-full font-mono text-sm">
                    <thead><tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                        <th className="text-left py-2">Filter</th><th className="text-right py-2">Resolved</th><th className="text-right py-2 text-atlas-positive">Later +</th><th className="text-right py-2 text-atlas-negative">Later −</th><th className="text-right py-2">Net CF</th>
                    </tr></thead>
                    <tbody>
                        {buckets.map((b) => (
                            <tr key={b.code} className="border-t border-atlas-border">
                                <td className="py-2 text-atlas-textSecondary">{b.filter}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-text">{b.rejected_resolved}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-positive">{b.later_profitable}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-negative">{b.later_unprofitable}</td>
                                <td className={`py-2 text-right tabular-nums ${(b.net_cf_pnl_pct || 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{fmtNum(b.net_cf_pnl_pct, "%")}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function ZoneEffectiveness({ data }) {
    const rows = data?.by_symbol || [];
    const o = data?.overall;
    const hasData = rows.length > 0;
    return (
        <div className="p-6" data-testid="zone-effectiveness">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Does the support engine have predictive value? Bounces vs failures{o?.touches ? ` · ${o.touches} touches` : ""}</div>
            {!hasData ? <ResearchEmpty testid="zone-effectiveness-empty" label="needs zone interactions with resolved returns." /> : (
                <table className="w-full font-mono text-sm">
                    <thead><tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                        <th className="text-left py-2">Symbol</th><th className="text-right py-2">Touches</th><th className="text-right py-2 text-atlas-positive">Bounces</th><th className="text-right py-2 text-atlas-negative">Fails</th><th className="text-right py-2">Avg Ret</th>
                    </tr></thead>
                    <tbody>
                        {rows.map((z) => (
                            <tr key={z.symbol} className="border-t border-atlas-border">
                                <td className="py-2 text-atlas-text font-bold">{z.symbol.split("/")[0]}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-textSecondary">{z.touches}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-positive">{z.successful_bounces}</td>
                                <td className="py-2 text-right tabular-nums text-atlas-negative">{z.failed_bounces}</td>
                                <td className={`py-2 text-right tabular-nums ${(z.avg_return_pct || 0) >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>{fmtNum(z.avg_return_pct, "%")}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

/* ---------------- Circuit Breaker Accuracy ---------------- */
function BreakerAccuracy({ breaker }) {
    const states = ["PASS", "CAUTION", "VETO"];
    const hasData = breaker && states.some((s) => (breaker[s]?.count || 0) > 0);
    return (
        <div className="p-6" data-testid="breaker-accuracy">
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Resolved 7d outcomes per state · was it protective or over-restrictive?</div>
            {!hasData ? (
                <div className="font-mono text-xs text-atlas-textSecondary py-6 text-center">No breaker evaluations logged yet.</div>
            ) : (
                <table className="w-full font-mono text-sm">
                    <thead>
                        <tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left py-2">State</th>
                            <th className="text-right py-2">Resolved</th>
                            <th className="text-right py-2 text-atlas-positive">Protected</th>
                            <th className="text-right py-2 text-atlas-negative">Over-Restr.</th>
                            <th className="text-right py-2">Avg 7d</th>
                        </tr>
                    </thead>
                    <tbody>
                        {states.map((st) => {
                            const b = breaker[st] || {};
                            const ret = b.avg_ret_7d;
                            return (
                                <tr key={st} className="border-t border-atlas-border" data-testid={`breaker-row-${st}`}>
                                    <td className={`py-2.5 font-bold ${st === "PASS" ? "text-atlas-positive" : st === "CAUTION" ? "text-atlas-text" : "text-atlas-negative"}`}>{st}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-textSecondary">{b.resolved ?? 0}/{b.count ?? 0}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-positive">{b.protected ?? 0}</td>
                                    <td className="py-2.5 text-right tabular-nums text-atlas-negative">{b.over_restrictive ?? 0}</td>
                                    <td className={`py-2.5 text-right tabular-nums ${ret == null ? "text-atlas-textTertiary" : ret >= 0 ? "text-atlas-positive" : "text-atlas-negative"}`}>
                                        {ret == null ? "—" : `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            )}
            <div className="mt-4 font-mono text-[10px] text-atlas-textTertiary leading-relaxed">
                For CAUTION/VETO rows: a DOWN forward move = breaker was right to hold back (Protected); an UP move = it blocked a winner (Over-Restrictive).
            </div>
        </div>
    );
}

/* ---------------- Filter Attribution (Strategy) ---------------- */
function FilterAttribution({ rejections }) {
    const board = rejections?.rejection_leaderboard || [];
    return (
        <div className="panel p-6" data-testid="filter-attribution">
            <div className="font-heading font-medium text-lg text-atlas-text">Filter Attribution</div>
            <div className="text-atlas-textTertiary font-mono text-[10px] uppercase tracking-wider mt-1 mb-4">Which layers gate capital · {rejections?.total_evaluations ?? 0} evals</div>
            {board.length === 0 ? (
                <div className="font-mono text-xs text-atlas-textSecondary py-6 text-center">No evaluations logged yet.</div>
            ) : (
                <table className="w-full font-mono text-sm">
                    <thead>
                        <tr className="text-atlas-textSecondary text-[10px] uppercase tracking-widest">
                            <th className="text-left py-2">Filter</th>
                            <th className="text-right py-2">Triggered</th>
                            <th className="text-right py-2">% of Evals</th>
                        </tr>
                    </thead>
                    <tbody>
                        {board.map((b) => (
                            <tr key={b.code} className="border-t border-atlas-border" data-testid={`attr-${b.code}`}>
                                <td className="py-2.5 text-atlas-text">{CODE_LABELS[b.code] || b.code}</td>
                                <td className="py-2.5 text-right tabular-nums text-atlas-textSecondary">{b.count}</td>
                                <td className="py-2.5 text-right tabular-nums text-atlas-text">{b.pct_of_evals}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

/* ---------------- Rejection Leaderboard ---------------- */
function RejectionLeaderboard({ rejections }) {
    const board = rejections?.rejection_leaderboard || [];
    const max = Math.max(1, ...board.map((b) => b.count));
    return (
        <div className="p-6" data-testid="rejection-leaderboard">
            <div className="flex items-baseline justify-end mb-4">
                <div className="font-mono text-[10px] text-atlas-textTertiary">
                    Greenlit rate: <span className="text-atlas-positive font-bold">{rejections?.greenlit_rate_pct ?? 0}%</span>
                </div>
            </div>
            {board.length === 0 ? (
                <div className="font-mono text-xs text-atlas-textSecondary py-6 text-center">No evaluations logged yet for this sprint.</div>
            ) : (
                <div className="space-y-3">
                    {board.map((b) => {
                        const isGreen = b.code === "GREENLIT";
                        return (
                            <div key={b.code} data-testid={`leaderboard-${b.code}`}>
                                <div className="flex items-center justify-between font-mono text-xs mb-1">
                                    <span className="text-atlas-textSecondary">{CODE_LABELS[b.code] || b.code}</span>
                                    <span className="text-atlas-text tabular-nums">{b.count} · {b.pct_of_evals}%</span>
                                </div>
                                <div className="h-2 bg-atlas-bg rounded overflow-hidden">
                                    <div className="h-full rounded" style={{ width: `${(b.count / max) * 100}%`, background: isGreen ? "#10B981" : "#C0C5CE" }} />
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
