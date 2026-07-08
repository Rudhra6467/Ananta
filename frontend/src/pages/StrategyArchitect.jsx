import { useState, useRef, useEffect } from "react";
import {
    Sparkles, Send, Loader2, Plus, ArrowLeft, Copy, FileJson, Boxes, Store, GitBranch, Code,
    Zap, ShieldCheck, TrendingUp, Save, AlertTriangle, Bot, User, RefreshCw, CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import LabModal from "@/components/lab/LabModal";

const AI_PREF_KEY = "ananta_architect_ai";

// The Strategy Architect — the "+" experience. With the AI switch ON it interviews the user
// and designs a deployable strategy (burns LLM credits). With it OFF it falls back to the
// zero-credit manual flow (copy an existing strategy / import a config JSON).
export default function StrategyArchitect({ open, onOpenChange, registry, isOwner, onCreated }) {
    const [aiOn, setAiOn] = useState(() => localStorage.getItem(AI_PREF_KEY) === "1");
    const setAi = (v) => { setAiOn(v); localStorage.setItem(AI_PREF_KEY, v ? "1" : "0"); };

    return (
        <LabModal open={open} onOpenChange={onOpenChange} testid="strategy-architect"
            icon={aiOn ? Sparkles : Plus} accent="cyan"
            title="Strategy Architect" subtitle={aiOn ? "AI-designed · describe your goal" : "Manual · copy or import"}>
            {/* AI credits switch */}
            <div className="flex items-center justify-between gap-3 rounded-xl border border-atlas-border bg-atlas-panel/60 px-4 py-3" data-testid="architect-ai-toggle-row">
                <div className="flex items-center gap-2.5">
                    <Sparkles className={`w-4 h-4 ${aiOn ? "text-atlas-cyan" : "text-atlas-textTertiary"}`} />
                    <div>
                        <div className="font-mono text-xs font-bold text-atlas-text">AI Architect Mode</div>
                        <div className="font-mono text-[10px] text-atlas-textTertiary">Interviews you & designs the strategy automatically.</div>
                    </div>
                </div>
                <Switch data-testid="architect-ai-switch" checked={aiOn} onCheckedChange={setAi}
                    className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border" />
            </div>
            {aiOn && (
                <div className="flex items-center gap-2 rounded-lg border border-atlas-warning/40 bg-atlas-warning/10 px-3 py-2" data-testid="architect-credits-warning">
                    <AlertTriangle className="w-3.5 h-3.5 text-atlas-warning shrink-0" />
                    <span className="font-mono text-[10px] text-atlas-warning">AI mode burns LLM credits per message. Turn it off when you&apos;re low on credits.</span>
                </div>
            )}

            {aiOn
                ? <ArchitectChat registry={registry} isOwner={isOwner} onCreated={onCreated} />
                : <ManualAdd registry={registry} isOwner={isOwner} onCreated={onCreated} />}
        </LabModal>
    );
}

/* ---------------- AI conversational mode ---------------- */
function ArchitectChat({ registry, isOwner, onCreated }) {
    const [messages, setMessages] = useState([]); // {role, content}
    const [quickReplies, setQuickReplies] = useState([]);
    const [design, setDesign] = useState(null);
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [saving, setSaving] = useState(false);
    const sessionRef = useRef(null);
    const scrollRef = useRef(null);

    useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [messages, busy, design]);

    const send = async (textArg) => {
        const text = (textArg ?? input).trim();
        if (!text || busy) return;
        if (!isOwner) { toast.error("Owner login required"); return; }
        const nextHistory = [...messages, { role: "user", content: text }];
        setMessages(nextHistory);
        setInput(""); setQuickReplies([]); setBusy(true);
        try {
            const res = await api.strategyArchitectChat(text, sessionRef.current, messages);
            sessionRef.current = res.session_id;
            if (res.phase === "design") {
                setDesign(res);
                setMessages((m) => [...m, { role: "assistant", content: `Designed "${res.name}" — review the strategy card below.` }]);
            } else {
                setMessages((m) => [...m, { role: "assistant", content: res.message || "Tell me more." }]);
                setQuickReplies(res.quick_replies || []);
            }
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message;
            setMessages((m) => [...m, { role: "assistant", content: `⚠︎ ${detail}` }]);
            toast.error("Architect error", { description: String(detail) });
        } finally { setBusy(false); }
    };

    const saveDesign = async () => {
        if (!design || !isOwner) { if (!isOwner) toast.error("Owner login required"); return; }
        setSaving(true);
        try {
            const res = await api.strategyConfigCreate({
                strategy_key: design.strategy_key, params: design.params || {}, origin: "architect",
                name: design.name, meta: { card: design.card, architect: true, base: design.base_strategy_name },
            });
            toast.success("SAVED TO STRATEGY MANAGER", { description: `${res.config.name} · registered in Research Lab` });
            onCreated();
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.response?.data?.detail?.errors?.join?.(", ") || e?.response?.data?.detail || e?.message) });
        } finally { setSaving(false); }
    };

    const STARTERS = ["Steady passive income", "Trade Bitcoin breakouts", "Strategy for bear markets", "High win-rate swing trades"];

    return (
        <div className="space-y-3" data-testid="architect-chat">
            <div ref={scrollRef} className="max-h-[38vh] min-h-[140px] overflow-y-auto atlas-scroll rounded-xl border border-atlas-border bg-atlas-panel/40 p-3 space-y-3">
                {messages.length === 0 && (
                    <div className="py-2">
                        <div className="flex items-center gap-2 font-mono text-[11px] text-atlas-textSecondary mb-2"><Bot className="w-4 h-4 text-atlas-cyan" /> Describe what you want to achieve — I&apos;ll design a validated strategy.</div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {STARTERS.map((s) => (
                                <button key={s} data-testid="architect-starter" onClick={() => send(s)} disabled={!isOwner}
                                    className="text-left px-3 py-2 rounded-lg border border-atlas-border font-mono text-[11px] text-atlas-textSecondary hover:border-atlas-cyan/50 hover:text-atlas-text transition-colors disabled:opacity-40">{s}</button>
                            ))}
                        </div>
                    </div>
                )}
                {messages.map((m, i) => (
                    <div key={i} data-testid={`architect-msg-${m.role}`} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : ""}`}>
                        {m.role === "assistant" && <Bot className="w-4 h-4 text-atlas-cyan shrink-0 mt-1" />}
                        <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap ${m.role === "user" ? "bg-atlas-cyan/10 border border-atlas-cyan/30 text-atlas-text" : "bg-atlas-panel border border-atlas-border text-atlas-textSecondary"}`}>{m.content}</div>
                        {m.role === "user" && <User className="w-4 h-4 text-atlas-cyan shrink-0 mt-1" />}
                    </div>
                ))}
                {busy && <div className="flex gap-2.5 items-center" data-testid="architect-thinking"><Bot className="w-4 h-4 text-atlas-cyan" /><div className="bg-atlas-panel border border-atlas-border rounded-xl px-3.5 py-2.5 font-mono text-[11px] text-atlas-textTertiary flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> designing…</div></div>}
            </div>

            {quickReplies.length > 0 && !design && (
                <div className="flex flex-wrap gap-2" data-testid="architect-quick-replies">
                    {quickReplies.map((q) => (
                        <button key={q} data-testid="architect-quick" onClick={() => send(q)} disabled={busy}
                            className="px-3 py-1.5 rounded-full border border-atlas-cyan/40 text-atlas-cyan font-mono text-[10px] hover:bg-atlas-cyan/10 disabled:opacity-40">{q}</button>
                    ))}
                </div>
            )}

            {design && <StrategyCardView design={design} baseName={registry[design.strategy_key]?.name} onSave={saveDesign} saving={saving} onRefine={() => setDesign(null)} isOwner={isOwner} />}

            {!design && (
                <div className="flex items-center gap-2">
                    <input data-testid="architect-input" value={input} onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                        placeholder={isOwner ? "Describe your trading goal…" : "Owner login required"} disabled={busy || !isOwner}
                        className="atlas-input flex-1 rounded-lg font-mono text-sm px-3 py-2 disabled:opacity-50" />
                    <Button data-testid="architect-send" onClick={() => send()} disabled={busy || !isOwner || !input.trim()} className="gap-1.5">
                        {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </Button>
                </div>
            )}
        </div>
    );
}

function StrategyCardView({ design, baseName, onSave, saving, onRefine, isOwner }) {
    const c = design.card || {};
    const chips = (arr) => (arr || []).map((x) => <span key={x} className="font-mono text-[9px] px-2 py-0.5 rounded-full border border-atlas-border text-atlas-textSecondary">{x}</span>);
    return (
        <div className="rounded-xl border border-atlas-cyan/30 bg-atlas-cyan/5 p-4 space-y-4" data-testid="architect-strategy-card">
            <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                    <div className="font-heading font-medium text-lg text-atlas-text" data-testid="architect-card-name">{design.name}</div>
                    <div className="font-mono text-[10px] text-atlas-textTertiary mt-0.5">{c.category} · base: {baseName || design.strategy_key} · {c.market}</div>
                </div>
                <div className="text-right">
                    <div className="font-heading font-bold text-2xl text-atlas-cyan">{c.confidence ?? "—"}%</div>
                    <div className="font-mono text-[8px] text-atlas-textTertiary uppercase">Confidence</div>
                </div>
            </div>

            <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{c.logic_summary}</p>

            <div className="grid grid-cols-3 gap-2 font-mono text-center">
                <MiniStat label="Win Rate" value={c.expected_win_rate} />
                <MiniStat label="Profit Factor" value={c.expected_profit_factor} />
                <MiniStat label="Max DD" value={c.expected_drawdown} />
            </div>

            <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5"><span className="font-mono text-[9px] text-atlas-textTertiary mr-1">Risk:</span><span className={`font-mono text-[9px] px-2 py-0.5 rounded-full border ${c.risk === "Low" ? "border-atlas-positive/40 text-atlas-positive" : c.risk === "High" ? "border-atlas-negative/40 text-atlas-negative" : "border-atlas-warning/40 text-atlas-warning"}`}>{c.risk}</span></div>
                {c.suitable_for?.length > 0 && <div className="flex flex-wrap gap-1.5 items-center"><span className="font-mono text-[9px] text-atlas-textTertiary mr-1">Assets:</span>{chips(c.suitable_for)}</div>}
                {c.timeframes?.length > 0 && <div className="flex flex-wrap gap-1.5 items-center"><span className="font-mono text-[9px] text-atlas-textTertiary mr-1">Timeframes:</span>{chips(c.timeframes)}</div>}
            </div>

            {(c.strengths?.length || c.weaknesses?.length) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {c.strengths?.length > 0 && <ListBlock title="Strengths" items={c.strengths} good />}
                    {c.weaknesses?.length > 0 && <ListBlock title="Weaknesses" items={c.weaknesses} />}
                </div>
            )}

            {/* parameter summary with reasons */}
            <div>
                <div className="label-tag mb-1.5">PARAMETER SUMMARY</div>
                <div className="rounded-lg border border-atlas-border divide-y divide-atlas-border/50 max-h-40 overflow-y-auto atlas-scroll" data-testid="architect-params">
                    {Object.entries(design.params || {}).map(([k, v]) => (
                        <div key={k} className="px-3 py-1.5">
                            <div className="flex items-center justify-between gap-2 font-mono text-[10px]"><span className="text-atlas-textSecondary">{k}</span><span className="text-atlas-text font-bold">{String(v)}</span></div>
                            {c.param_reasons?.[k] && <div className="font-mono text-[9px] text-atlas-textTertiary mt-0.5">{c.param_reasons[k]}</div>}
                        </div>
                    ))}
                </div>
            </div>

            {/* research readiness */}
            <div className="flex flex-wrap gap-2">
                {["Walk-Forward", "Monte Carlo", "Sensitivity"].map((r) => (
                    <span key={r} className="flex items-center gap-1 font-mono text-[9px] text-atlas-positive"><CheckCircle2 className="w-3 h-3" /> {r} Ready</span>
                ))}
            </div>

            <div className="flex items-center gap-2">
                <Button data-testid="architect-save-btn" onClick={onSave} disabled={saving || !isOwner} className="flex-1 gap-2">
                    {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} SAVE TO STRATEGY MANAGER
                </Button>
                <Button data-testid="architect-refine-btn" onClick={onRefine} variant="outline" className="gap-2 border-atlas-border">
                    <RefreshCw className="w-4 h-4" /> REFINE
                </Button>
            </div>
        </div>
    );
}

function MiniStat({ label, value }) {
    return <div className="rounded-lg border border-atlas-border py-2"><div className="text-[8px] text-atlas-textTertiary uppercase">{label}</div><div className="text-sm font-bold text-atlas-text">{value ?? "—"}</div></div>;
}
function ListBlock({ title, items, good }) {
    return (
        <div>
            <div className="label-tag mb-1">{title}</div>
            <ul className="space-y-0.5">
                {items.slice(0, 4).map((it, i) => <li key={i} className={`font-mono text-[10px] ${good ? "text-atlas-positive" : "text-atlas-textSecondary"}`}>• {it}</li>)}
            </ul>
        </div>
    );
}

/* ---------------- Manual (no-credit) mode ---------------- */
const SOURCES = [
    { id: "duplicate", label: "Copy Existing Strategy", icon: Copy, ready: true, desc: "Clone a built-in as a tunable config variant." },
    { id: "json", label: "Import JSON Configuration", icon: FileJson, ready: true, desc: "Paste a validated config JSON." },
    { id: "builtin", label: "Built-in Strategies", icon: Boxes, ready: false, desc: "All built-ins are already active." },
    { id: "marketplace", label: "Community Marketplace", icon: Store, ready: false, desc: "Coming soon." },
    { id: "git", label: "Git Repository", icon: GitBranch, ready: false, desc: "Coming soon." },
    { id: "python", label: "Upload Python Strategy", icon: Code, ready: false, desc: "Sandboxed execution — coming soon." },
];

function ManualAdd({ registry, isOwner, onCreated }) {
    const [source, setSource] = useState(null);
    const [strat, setStrat] = useState("hunter");
    const [name, setName] = useState("");
    const [json, setJson] = useState("");
    const [busy, setBusy] = useState(false);
    const keys = Object.keys(registry);

    const submit = async () => {
        if (!isOwner) { toast.error("Owner login required"); return; }
        setBusy(true);
        try {
            let payload;
            if (source === "duplicate") {
                payload = { strategy_key: strat, params: {}, origin: "user", name: name.trim() || `${registry[strat]?.name || strat} · variant` };
            } else {
                let parsed;
                try { parsed = JSON.parse(json); } catch { toast.error("Invalid JSON", { description: "Check the syntax." }); setBusy(false); return; }
                if (!parsed.strategy_key) { toast.error("Missing strategy_key"); setBusy(false); return; }
                payload = { strategy_key: parsed.strategy_key, params: parsed.params || {}, origin: "user", name: parsed.name || name.trim() || "Imported config" };
            }
            const res = await api.strategyConfigCreate(payload);
            toast.success("STRATEGY VARIANT ADDED", { description: res.config.name });
            onCreated();
        } catch (e) {
            toast.error("ADD FAILED", { description: String(e?.response?.data?.detail?.errors?.join?.(", ") || e?.response?.data?.detail || e?.message) });
        } finally { setBusy(false); }
    };

    if (!source) {
        return (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="manual-sources">
                {SOURCES.map((src) => {
                    const SIcon = src.icon;
                    return (
                        <button key={src.id} data-testid={`source-${src.id}`} disabled={!src.ready} onClick={() => src.ready && setSource(src.id)}
                            className={`text-left p-4 rounded-xl border transition-all ${src.ready ? "border-atlas-border hover:border-atlas-cyan/50 hover:bg-atlas-panelHover" : "border-atlas-border/50 opacity-50 cursor-not-allowed"}`}>
                            <SIcon className={`w-5 h-5 mb-2 ${src.ready ? "text-atlas-cyan" : "text-atlas-textTertiary"}`} />
                            <div className="font-mono text-sm font-bold text-atlas-text flex items-center gap-2">{src.label}{!src.ready && <span className="text-[8px] text-atlas-textTertiary border border-atlas-border rounded px-1 py-0.5">SOON</span>}</div>
                            <div className="font-mono text-[10px] text-atlas-textTertiary mt-1">{src.desc}</div>
                        </button>
                    );
                })}
            </div>
        );
    }

    return (
        <div className="space-y-4" data-testid={`manual-form-${source}`}>
            <button onClick={() => setSource(null)} className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textTertiary hover:text-atlas-text"><ArrowLeft className="w-3.5 h-3.5" /> CHANGE SOURCE</button>
            {source === "duplicate" && (
                <div><div className="label-tag mb-2">BASE STRATEGY</div>
                    <select data-testid="manual-strat" value={strat} onChange={(e) => setStrat(e.target.value)} className="w-full bg-atlas-panel border border-atlas-border rounded px-3 py-2 font-mono text-sm text-atlas-text">
                        {keys.map((k) => <option key={k} value={k}>{registry[k]?.name || k}</option>)}
                    </select></div>
            )}
            {source === "json" && (
                <div><div className="label-tag mb-2">CONFIG JSON</div>
                    <textarea data-testid="manual-json" value={json} onChange={(e) => setJson(e.target.value)} rows={7} placeholder='{"strategy_key":"hunter","name":"My variant","params":{"rsi_reset_min":28}}' className="w-full atlas-input rounded-lg font-mono text-[11px] p-3" /></div>
            )}
            <div><div className="label-tag mb-2">NAME (optional)</div><Input data-testid="manual-name" value={name} onChange={(e) => setName(e.target.value)} className="atlas-input rounded-lg font-mono text-sm" placeholder="Auto-generated if blank" /></div>
            <Button data-testid="manual-submit" onClick={submit} disabled={busy || !isOwner} className="w-full gap-2">{busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} ADD STRATEGY</Button>
        </div>
    );
}
