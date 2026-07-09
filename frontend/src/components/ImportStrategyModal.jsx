import { useEffect, useMemo, useRef, useState } from "react";
import {
    Loader2, Upload, Sparkles, AlertTriangle, CheckCircle2, Info, XCircle, ArrowLeft,
    FileCode2, Braces, GitBranch, Store, ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const FORMAT_ICON = { pine_script: FileCode2, freqtrade: GitBranch, jesse: Store, json: Braces, auto: Sparkles };
const SEV = {
    error: { Icon: XCircle, cls: "text-atlas-negative", bg: "bg-atlas-negative/10 border-atlas-negative/30" },
    warning: { Icon: AlertTriangle, cls: "text-atlas-warning", bg: "bg-atlas-warning/10 border-atlas-warning/30" },
    info: { Icon: Info, cls: "text-atlas-cyan", bg: "bg-atlas-cyan/10 border-atlas-cyan/25" },
};

const SAMPLE = `//@version=5
strategy("Golden Cross", overlay=true)
fast = ta.sma(close, input.int(50, "Fast"))
slow = ta.sma(close, input.int(200, "Slow"))
if ta.crossover(fast, slow)
    strategy.entry("Long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("Long")`;

/** Full Strategy Import Pipeline: paste -> AI extract -> review/edit -> approve to Library. */
export default function ImportStrategyModal({ open, onOpenChange, onImported }) {
    const [step, setStep] = useState("input");   // input | review
    const [formats, setFormats] = useState([]);
    const [fmt, setFmt] = useState("auto");
    const [name, setName] = useState("");
    const [raw, setRaw] = useState("");
    const [detected, setDetected] = useState(null);
    const [analyzing, setAnalyzing] = useState(false);
    const [draft, setDraft] = useState(null);
    const detectTimer = useRef(null);

    useEffect(() => {
        if (!open) return;
        api.importFormats().then((d) => setFormats(d.formats || [])).catch(() => {});
    }, [open]);

    useEffect(() => {
        if (!open) { setStep("input"); setRaw(""); setName(""); setFmt("auto"); setDraft(null); setDetected(null); }
    }, [open]);

    // live, credit-free format detection as the user pastes
    useEffect(() => {
        if (!raw.trim()) { setDetected(null); return; }
        clearTimeout(detectTimer.current);
        detectTimer.current = setTimeout(() => {
            api.importDetect(raw).then(setDetected).catch(() => {});
        }, 400);
        return () => clearTimeout(detectTimer.current);
    }, [raw]);

    const analyze = async () => {
        if (!raw.trim()) { toast.error("Paste your strategy code first"); return; }
        setAnalyzing(true);
        try {
            const d = await api.importAnalyze({ raw_content: raw, source_format: fmt, name: name || undefined });
            setDraft(d);
            setStep("review");
            toast.success("Strategy analyzed", { description: `${d.conversion_confidence}% conversion confidence` });
        } catch (e) {
            toast.error("Analysis failed", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setAnalyzing(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="atlas-panel border-atlas-border bg-atlas-bg max-w-3xl p-0 gap-0 max-h-[92vh] overflow-hidden flex flex-col"
                data-testid="import-modal">
                <DialogTitle className="sr-only">Strategy Import Pipeline</DialogTitle>
                <DialogDescription className="sr-only">Import a trading strategy from Pine Script, Freqtrade, Jesse or JSON, review the AI conversion, then save it to your library.</DialogDescription>
                <div className="flex items-center gap-2.5 px-5 py-4 border-b border-atlas-border">
                    <div className="w-9 h-9 rounded-lg grid place-items-center border border-atlas-border bg-atlas-cyan/10">
                        <Upload className="w-4.5 h-4.5 text-atlas-cyan" />
                    </div>
                    <div>
                        <div className="font-heading text-base text-atlas-text">Strategy Import Pipeline</div>
                        <div className="font-mono text-[10px] text-atlas-textTertiary">
                            {step === "input" ? "Import from Pine Script · Freqtrade · Jesse · JSON" : "Review the AI conversion, then save to your Library"}
                        </div>
                    </div>
                </div>

                <div className="overflow-y-auto p-5">
                    {step === "input" ? (
                        <InputStep {...{ formats, fmt, setFmt, name, setName, raw, setRaw, detected, analyzing, analyze }} />
                    ) : (
                        <ReviewStep draft={draft} setDraft={setDraft}
                            onBack={() => setStep("input")}
                            onImported={(lib) => { onImported?.(lib); onOpenChange(false); }} />
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

function InputStep({ formats, fmt, setFmt, name, setName, raw, setRaw, detected, analyzing, analyze }) {
    return (
        <div className="space-y-4">
            <div>
                <label className="label-tag block mb-2">Source Framework</label>
                <div className="flex flex-wrap gap-2">
                    {formats.map((f) => {
                        const Icon = FORMAT_ICON[f.key] || FileCode2;
                        const active = fmt === f.key;
                        const isDetected = detected && f.key === detected.best && fmt === "auto";
                        return (
                            <button key={f.key} data-testid={`import-fmt-${f.key}`} onClick={() => setFmt(f.key)}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full font-mono text-[10px] border transition-all ${
                                    active ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan"
                                        : "border-atlas-border text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary"}`}>
                                <Icon className="w-3 h-3" /> {f.label}
                                {isDetected && <span className="ml-1 text-[8px] text-atlas-positive">· detected</span>}
                            </button>
                        );
                    })}
                </div>
            </div>

            <div>
                <label className="label-tag block mb-2">Name <span className="text-atlas-textTertiary normal-case">(optional — AI infers one)</span></label>
                <Input data-testid="import-name" value={name} onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. My Golden Cross" className="atlas-input rounded-lg font-mono text-sm" />
            </div>

            <div>
                <div className="flex items-center justify-between mb-2">
                    <label className="label-tag">Strategy Code / Definition</label>
                    <button data-testid="import-sample" onClick={() => setRaw(SAMPLE)}
                        className="font-mono text-[10px] text-atlas-cyan hover:underline">Load sample</button>
                </div>
                <textarea data-testid="import-code" value={raw} onChange={(e) => setRaw(e.target.value)} rows={12}
                    spellCheck={false}
                    placeholder="Paste your Pine Script, Freqtrade IStrategy, Jesse Strategy, or JSON here…"
                    className="w-full rounded-lg bg-atlas-panel border border-atlas-border p-3 font-mono text-[11px] text-atlas-text leading-relaxed focus:outline-none focus:border-atlas-cyan/50 resize-y" />
                {detected && raw.trim() && (
                    <div className="mt-1.5 font-mono text-[9px] text-atlas-textTertiary">
                        Auto-detected: <span className="text-atlas-textSecondary">{detected.best}</span>
                        {" "}({Math.round((detected.scores?.[detected.best] || 0) * 100)}% match)
                    </div>
                )}
            </div>

            <div className="flex items-center justify-between pt-1">
                <div className="font-mono text-[9px] text-atlas-textTertiary max-w-[55%]">
                    The AI extracts entry/exit logic, risk, indicators &amp; parameters, then flags anything Ananta cannot replicate.
                </div>
                <Button data-testid="import-analyze-btn" onClick={analyze} disabled={analyzing || !raw.trim()}
                    className="bg-atlas-cyan text-atlas-bg hover:bg-cyan-300 font-mono text-xs">
                    {analyzing ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Analyzing…</>
                        : <><Sparkles className="w-3.5 h-3.5 mr-1.5" /> Analyze with AI</>}
                </Button>
            </div>
        </div>
    );
}

const listToText = (arr) => (arr || []).join("\n");
const textToList = (t) => (t || "").split("\n").map((s) => s.trim()).filter(Boolean);

function ReviewStep({ draft, setDraft, onBack, onImported }) {
    const [saving, setSaving] = useState(false);
    const v = draft.validation || { issues: [], status: "review", error_count: 0 };
    const blocked = (v.error_count || 0) > 0;

    const set = (k, val) => setDraft((d) => ({ ...d, [k]: val }));

    const save = async () => {
        setSaving(true);
        try {
            const patch = {
                name: draft.name, description: draft.description, category: draft.category,
                style: draft.style, risk: draft.risk, direction: draft.direction,
                timeframe: draft.timeframe, market_regimes: draft.market_regimes,
                entry_rules: draft.entry_rules, exit_rules: draft.exit_rules,
                ideal_conditions: draft.ideal_conditions, avoid_conditions: draft.avoid_conditions,
                strengths: draft.strengths, weaknesses: draft.weaknesses, tags: draft.tags,
                ai_summary: draft.ai_summary, recommended_market: draft.recommended_market,
            };
            await api.importUpdate(draft.id, patch);
            const r = await api.importApprove(draft.id);
            toast.success("Imported to Library", { description: draft.name });
            onImported(r.strategy);
        } catch (e) {
            toast.error("Could not save", { description: String(e?.response?.data?.detail || e?.message) });
        } finally { setSaving(false); }
    };

    return (
        <div className="space-y-4" data-testid="import-review">
            <button data-testid="import-back" onClick={onBack} className="flex items-center gap-1.5 font-mono text-[10px] text-atlas-textSecondary hover:text-atlas-text">
                <ArrowLeft className="w-3.5 h-3.5" /> Edit source
            </button>

            {/* conversion report header */}
            <div className="grid md:grid-cols-3 gap-3">
                <ConfidenceCard value={draft.conversion_confidence} />
                <MiniStat label="AI Health" value={`${draft.ai_health_score}/100`} sub={`Grade ${draft.ai_grade}`} />
                <MiniStat label="Direction" value={(draft.direction || "long").toUpperCase()}
                    sub={draft.long_short_support?.short ? "long + short" : "long only"} />
            </div>

            {/* validation issues */}
            <div className="panel p-4" data-testid="import-validation">
                <div className="label-tag mb-2 flex items-center gap-2">
                    <ShieldCheck className="w-3.5 h-3.5 text-atlas-cyan" /> Validation Report
                    <span className={`ml-auto font-mono text-[9px] px-2 py-0.5 rounded-full border ${
                        v.status === "ready" ? "text-atlas-positive border-atlas-positive/40 bg-atlas-positive/10"
                            : v.status === "blocked" ? "text-atlas-negative border-atlas-negative/40 bg-atlas-negative/10"
                                : "text-atlas-warning border-atlas-warning/40 bg-atlas-warning/10"}`}>{v.status}</span>
                </div>
                {(!v.issues || v.issues.length === 0) ? (
                    <div className="flex items-center gap-2 font-mono text-[11px] text-atlas-positive"><CheckCircle2 className="w-4 h-4" /> Clean conversion — no issues detected.</div>
                ) : (
                    <ul className="space-y-1.5">
                        {v.issues.map((it, i) => {
                            const s = SEV[it.severity] || SEV.info;
                            return (
                                <li key={i} className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 ${s.bg}`}>
                                    <s.Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${s.cls}`} />
                                    <span className="font-mono text-[10px] text-atlas-textSecondary leading-relaxed">{it.message}</span>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>

            {/* conversion notes */}
            {draft.conversion_report && (
                <div className="panel p-4">
                    <div className="label-tag mb-1.5 flex items-center gap-2"><Sparkles className="w-3.5 h-3.5 text-atlas-cyan" /> AI Conversion Report</div>
                    <p className="font-mono text-[11px] text-atlas-textSecondary leading-relaxed">{draft.conversion_report}</p>
                    {(draft.conversion_unsupported?.length > 0) && (
                        <div className="mt-2 font-mono text-[10px] text-atlas-warning">Unsupported: {draft.conversion_unsupported.join(", ")}</div>
                    )}
                </div>
            )}

            {/* editable metadata */}
            <div className="panel p-4 space-y-3">
                <div className="label-tag">Review &amp; Edit Metadata</div>
                <div className="grid md:grid-cols-2 gap-3">
                    <Field label="Name"><Input data-testid="edit-name" value={draft.name} onChange={(e) => set("name", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                    <Field label="Category"><Input value={draft.category} onChange={(e) => set("category", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                    <Field label="Style"><Input value={draft.style} onChange={(e) => set("style", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                    <Field label="Risk"><Input value={draft.risk} onChange={(e) => set("risk", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                    <Field label="Primary Timeframe"><Input value={draft.timeframe} onChange={(e) => set("timeframe", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                    <Field label="Recommended Market"><Input value={draft.recommended_market} onChange={(e) => set("recommended_market", e.target.value)} className="atlas-input rounded-lg font-mono text-xs" /></Field>
                </div>
                <Field label="Description">
                    <textarea value={draft.description} onChange={(e) => set("description", e.target.value)} rows={2}
                        className="w-full rounded-lg bg-atlas-panel border border-atlas-border p-2 font-mono text-[11px] text-atlas-text focus:outline-none focus:border-atlas-cyan/50 resize-y" />
                </Field>
                <div className="grid md:grid-cols-2 gap-3">
                    <ListField label="Entry Rules" value={draft.entry_rules} onChange={(l) => set("entry_rules", l)} testid="edit-entry" />
                    <ListField label="Exit Rules" value={draft.exit_rules} onChange={(l) => set("exit_rules", l)} testid="edit-exit" />
                    <ListField label="Strengths" value={draft.strengths} onChange={(l) => set("strengths", l)} />
                    <ListField label="Weaknesses" value={draft.weaknesses} onChange={(l) => set("weaknesses", l)} />
                </div>
                <Field label="Market Regimes (comma-separated)">
                    <Input value={(draft.market_regimes || []).join(", ")}
                        onChange={(e) => set("market_regimes", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        className="atlas-input rounded-lg font-mono text-xs" />
                </Field>
                <Field label="Tags (comma-separated)">
                    <Input value={(draft.tags || []).join(", ")}
                        onChange={(e) => set("tags", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                        className="atlas-input rounded-lg font-mono text-xs" />
                </Field>
                <Field label="AI Summary">
                    <textarea value={draft.ai_summary} onChange={(e) => set("ai_summary", e.target.value)} rows={2}
                        className="w-full rounded-lg bg-atlas-panel border border-atlas-border p-2 font-mono text-[11px] text-atlas-text focus:outline-none focus:border-atlas-cyan/50 resize-y" />
                </Field>
            </div>

            <div className="flex items-center justify-between pt-1 pb-1">
                <div className="font-mono text-[9px] text-atlas-textTertiary max-w-[50%]">
                    {blocked ? "Resolve the errors above before saving." : "Saved strategies join your Library — filterable, AI-gradeable &amp; backtest-ready."}
                </div>
                <Button data-testid="import-approve-btn" onClick={save} disabled={saving || blocked}
                    className="bg-atlas-positive text-atlas-bg hover:bg-emerald-400 font-mono text-xs disabled:opacity-40">
                    {saving ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Saving…</>
                        : <><CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Save to Library</>}
                </Button>
            </div>
        </div>
    );
}

function ConfidenceCard({ value = 0 }) {
    const pct = Math.max(0, Math.min(100, value));
    const color = pct >= 75 ? "text-atlas-positive" : pct >= 50 ? "text-atlas-warning" : "text-atlas-negative";
    const R = 26, C = 2 * Math.PI * R;
    return (
        <div className="panel p-3 flex items-center gap-3" data-testid="import-confidence">
            <svg width="66" height="66" viewBox="0 0 66 66" className="-rotate-90">
                <circle cx="33" cy="33" r={R} fill="none" stroke="currentColor" strokeWidth="6" className="text-atlas-border" />
                <circle cx="33" cy="33" r={R} fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round"
                    className={color} strokeDasharray={C} strokeDashoffset={C - (C * pct) / 100} />
            </svg>
            <div>
                <div className={`font-heading text-xl ${color}`}>{pct}%</div>
                <div className="font-mono text-[9px] text-atlas-textTertiary uppercase tracking-wide">Conversion<br />Confidence</div>
            </div>
        </div>
    );
}

function MiniStat({ label, value, sub }) {
    return (
        <div className="panel p-3">
            <div className="font-mono text-[9px] text-atlas-textTertiary uppercase tracking-wide">{label}</div>
            <div className="font-heading text-lg text-atlas-text mt-0.5">{value}</div>
            {sub && <div className="font-mono text-[9px] text-atlas-textSecondary">{sub}</div>}
        </div>
    );
}

function Field({ label, children }) {
    return (
        <div>
            <label className="font-mono text-[9px] text-atlas-textTertiary uppercase tracking-wide block mb-1">{label}</label>
            {children}
        </div>
    );
}

function ListField({ label, value, onChange, testid }) {
    const text = useMemo(() => listToText(value), [value]);
    return (
        <Field label={`${label} (one per line)`}>
            <textarea data-testid={testid} defaultValue={text} onBlur={(e) => onChange(textToList(e.target.value))} rows={3}
                className="w-full rounded-lg bg-atlas-panel border border-atlas-border p-2 font-mono text-[11px] text-atlas-text focus:outline-none focus:border-atlas-cyan/50 resize-y" />
        </Field>
    );
}
