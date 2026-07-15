import { useCallback, useEffect, useState } from "react";
import { Sparkles, FlaskConical, ArrowLeft, Check, Plus, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import AnantaLogo from "@/components/AnantaLogo";

const CAPITAL_PRESETS = [10000, 25000, 50000, 100000];
const FIXED_PRESETS = [500, 1000, 2500];
const PCT_PRESETS = [5, 10];
const money = (n) => `$${Number(n).toLocaleString()}`;

/**
 * First-login Paper Trading wizard for the WEB app — mirrors the mobile onboarding
 * flow (Welcome → Research First → Capital → Allocation → Strategies → Summary).
 * Shown once per browser (localStorage `ananta_onboarded`). On finish it drives the
 * shared `/api/onboarding/paper-setup` endpoint, exactly like mobile.
 */
export default function WebOnboarding({ onDone }) {
    const [step, setStep] = useState("welcome");
    const [capital, setCapital] = useState(25000);
    const [customCap, setCustomCap] = useState("");
    const [allocType, setAllocType] = useState("fixed");
    const [allocValue, setAllocValue] = useState(1000);
    const [customAlloc, setCustomAlloc] = useState("");
    const [builtIn, setBuiltIn] = useState([]);
    const [mine, setMine] = useState([]);
    const [selected, setSelected] = useState([]);
    const [loadingStrats, setLoadingStrats] = useState(false);
    const [starting, setStarting] = useState(false);

    const loadStrategies = useCallback(async () => {
        setLoadingStrats(true);
        try {
            const reg = await api.strategyRegistry();
            setBuiltIn((reg.strategies || []).filter((s) => s.internal !== false));
            try {
                const d = await api.libraryList({});
                setMine((d.strategies || []).filter((s) => !s.internal && s.engine_key));
            } catch { /* noop */ }
        } finally { setLoadingStrats(false); }
    }, []);

    useEffect(() => { if (step === "strategies") loadStrategies(); }, [step, loadStrategies]);

    const finish = () => { localStorage.setItem("ananta_onboarded", "1"); onDone?.(); };
    const toggle = (key) => setSelected((p) => (p.includes(key) ? p.filter((x) => x !== key) : [...p, key]));

    const startPaper = async () => {
        setStarting(true);
        try {
            await api.onboardingPaperSetup({ capital, allocation_type: allocType, allocation_value: allocValue, strategies: selected });
            localStorage.setItem("ananta_onboarded", "1");
            toast.success("Paper trading is live — welcome to Ananta.");
            onDone?.();
        } catch (e) {
            setStarting(false);
            toast.error(e?.response?.data?.detail || "Could not start paper trading.");
        }
    };

    return (
        <div className="fixed inset-0 z-[70] bg-atlas-bg/97 backdrop-blur-xl overflow-y-auto grid-bg" data-testid="web-onboarding">
            <div className="max-w-lg mx-auto px-5 py-8 min-h-full flex flex-col">
                <div className="flex items-center gap-2 mb-6">
                    <AnantaLogo className="h-7 w-7 text-atlas-text" />
                    <span className="font-heading font-semibold tracking-tight text-atlas-text">Ananta</span>
                </div>

                {step === "welcome" && (
                    <Hero
                        Icon={Sparkles} kicker="WELCOME" title="Welcome to Ananta"
                        body="Trade with evidence, not assumptions. Research every strategy before risking real capital — build confidence through testing, validation, and paper trading."
                        cta="Start Exploring" ctaTestId="onboarding-start-exploring" onCta={() => setStep("research")}
                    />
                )}

                {step === "research" && (
                    <Hero
                        Icon={FlaskConical} kicker="RESEARCH FIRST" title="Start with Paper Trading"
                        body="The safest way to begin is by testing strategies in a simulated environment. Paper Trading lets you run strategies against live market conditions without risking real money — configure your virtual capital, choose strategies, and build confidence before going live."
                        cta="Start Paper Trading" ctaTestId="onboarding-start-paper" onCta={() => setStep("capital")}
                        secondary="Skip for Now" secondaryTestId="onboarding-skip" onSecondary={finish}
                    />
                )}

                {step === "capital" && (
                    <StepShell num={1} of={3} title="Allocate Virtual Capital" hint="How much virtual capital would you like to start with? You can change this anytime.">
                        <div className="grid grid-cols-2 gap-2.5">
                            {CAPITAL_PRESETS.map((v) => (
                                <Choice key={v} testId={`cap-${v}`} label={money(v)} active={!customCap && capital === v} onClick={() => { setCustomCap(""); setCapital(v); }} />
                            ))}
                        </div>
                        <FieldLabel>Custom amount</FieldLabel>
                        <input data-testid="cap-custom" value={customCap} inputMode="numeric"
                            onChange={(e) => { const c = e.target.value.replace(/[^0-9]/g, ""); setCustomCap(c); const n = parseInt(c, 10); if (n) setCapital(n); }}
                            placeholder="e.g. 30000" className={inputCls} />
                        <PrimaryBtn testId="onboarding-continue" label="Continue" disabled={capital < 100} onClick={() => setStep("alloc")} />
                    </StepShell>
                )}

                {step === "alloc" && (
                    <StepShell num={2} of={3} title="Per Trade Allocation" hint="How much capital should be allocated to each trade? This caps the maximum size of any single position.">
                        <div className="grid grid-cols-2 gap-2.5 mb-4">
                            <Seg testId="alloc-type-fixed" label="Fixed $" active={allocType === "fixed"} onClick={() => { setAllocType("fixed"); setAllocValue(1000); setCustomAlloc(""); }} />
                            <Seg testId="alloc-type-percent" label="% of Portfolio" active={allocType === "percent"} onClick={() => { setAllocType("percent"); setAllocValue(5); setCustomAlloc(""); }} />
                        </div>
                        <div className="grid grid-cols-2 gap-2.5">
                            {(allocType === "fixed" ? FIXED_PRESETS : PCT_PRESETS).map((v) => (
                                <Choice key={v} testId={`alloc-${v}`} label={allocType === "fixed" ? money(v) : `${v}%`} active={!customAlloc && allocValue === v} onClick={() => { setCustomAlloc(""); setAllocValue(v); }} />
                            ))}
                        </div>
                        <FieldLabel>Custom {allocType === "fixed" ? "amount ($)" : "percent (%)"}</FieldLabel>
                        <input data-testid="alloc-custom" value={customAlloc} inputMode="decimal"
                            onChange={(e) => { const c = e.target.value.replace(/[^0-9.]/g, ""); setCustomAlloc(c); const n = parseFloat(c); if (n) setAllocValue(n); }}
                            placeholder={allocType === "fixed" ? "e.g. 750" : "e.g. 7.5"} className={inputCls} />
                        <PrimaryBtn testId="onboarding-continue" label="Continue" disabled={allocValue <= 0} onClick={() => setStep("strategies")} />
                    </StepShell>
                )}

                {step === "strategies" && (
                    <StepShell num={3} of={3} title="Select Trading Strategies" hint="Choose the strategies Ananta should run in your paper session.">
                        {loadingStrats && builtIn.length === 0 ? (
                            <div className="flex justify-center py-8"><Loader2 className="w-6 h-6 text-atlas-cyan animate-spin" /></div>
                        ) : (
                            <>
                                <SectionLabel>BUILT-IN STRATEGIES</SectionLabel>
                                {builtIn.map((s) => (
                                    <StratRow key={s.key} testId={`strat-${s.key}`} name={s.name} on={selected.includes(s.key)} onClick={() => toggle(s.key)} />
                                ))}
                                <SectionLabel className="mt-4">MY STRATEGIES</SectionLabel>
                                {mine.length === 0 ? (
                                    <p className="text-atlas-textTertiary text-sm mb-2">You haven&apos;t created any custom strategies yet.</p>
                                ) : mine.map((s) => (
                                    <StratRow key={s.engine_key} testId={`strat-${s.engine_key}`} name={s.name} on={selected.includes(s.engine_key)} onClick={() => toggle(s.engine_key)} />
                                ))}
                                <button type="button" data-testid="onboarding-create-strategy"
                                    onClick={() => { finish(); window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "strategies" } })); }}
                                    className="w-full flex items-center justify-center gap-2 border border-dashed border-atlas-cyan/40 rounded-lg py-3 mt-1 text-atlas-cyan font-mono text-xs tracking-wide hover:bg-atlas-cyan/5 transition-colors">
                                    <Plus className="w-4 h-4" /> Create Strategy
                                </button>
                            </>
                        )}
                        <PrimaryBtn testId="onboarding-continue" label="Continue" disabled={selected.length === 0} onClick={() => setStep("summary")} />
                    </StepShell>
                )}

                {step === "summary" && (
                    <StepShell title="Review & Start" hint="Confirm your paper trading setup. You can change any of this later in Workspace.">
                        <div className="panel rounded-xl p-4 space-y-1">
                            <SummaryRow label="Virtual Capital" value={money(capital)} />
                            <SummaryRow label="Per Trade Allocation" value={allocType === "fixed" ? money(allocValue) : `${allocValue}%`} />
                            <div className="pt-2">
                                <div className="text-atlas-textTertiary text-xs mb-1">Strategies</div>
                                {selected.map((k) => {
                                    const s = [...builtIn, ...mine].find((x) => (x.key || x.engine_key) === k);
                                    return <div key={k} className="text-atlas-cyan text-sm">• {s?.name || k}</div>;
                                })}
                            </div>
                        </div>
                        <PrimaryBtn testId="onboarding-finish" label={starting ? "STARTING…" : "Start Paper Trading"} disabled={starting} loading={starting} onClick={startPaper} />
                        <button type="button" data-testid="onboarding-back" onClick={() => setStep("strategies")}
                            className="w-full flex items-center justify-center gap-1.5 py-2.5 text-atlas-textTertiary text-sm hover:text-atlas-text transition-colors">
                            <ArrowLeft className="w-4 h-4" /> Back
                        </button>
                    </StepShell>
                )}
            </div>
        </div>
    );
}

const inputCls = "w-full bg-atlas-panel border border-atlas-border rounded-lg px-4 py-3 text-atlas-text text-[15px] outline-none focus:border-atlas-cyan/60 transition-colors";

function Hero({ Icon, kicker, title, body, cta, ctaTestId, onCta, secondary, secondaryTestId, onSecondary }) {
    return (
        <div className="flex-1 flex flex-col justify-center py-8">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center bg-atlas-cyan/10 border border-atlas-cyan/30 mb-5">
                <Icon className="w-6 h-6 text-atlas-cyan" />
            </div>
            <div className="font-mono text-atlas-cyan text-xs tracking-[0.2em] font-extrabold mb-2">{kicker}</div>
            <h1 className="font-heading font-light text-3xl text-atlas-text tracking-tight mb-3">{title}</h1>
            <p className="text-atlas-textSecondary text-[15px] leading-relaxed mb-6">{body}</p>
            <PrimaryBtn testId={ctaTestId} label={cta} onClick={onCta} />
            {secondary && (
                <button type="button" data-testid={secondaryTestId} onClick={onSecondary}
                    className="w-full py-2.5 text-atlas-textTertiary text-sm hover:text-atlas-text transition-colors">{secondary}</button>
            )}
        </div>
    );
}

function StepShell({ num, of, title, hint, children }) {
    return (
        <div className="mt-3">
            {num ? <div className="font-mono text-atlas-cyan text-xs tracking-[0.2em] font-extrabold mb-2">STEP {num} OF {of}</div> : null}
            <h1 className="font-heading font-light text-3xl text-atlas-text tracking-tight mb-2">{title}</h1>
            <p className="text-atlas-textSecondary text-[15px] leading-relaxed mb-5">{hint}</p>
            {children}
        </div>
    );
}

function FieldLabel({ children }) {
    return <div className="text-atlas-textTertiary text-xs mt-4 mb-1.5">{children}</div>;
}
function SectionLabel({ children, className = "" }) {
    return <div className={`font-mono text-atlas-textTertiary text-xs tracking-[0.15em] font-bold mb-2 ${className}`}>{children}</div>;
}

function Choice({ testId, label, active, onClick }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick}
            className={`rounded-lg py-3 font-mono font-bold text-sm border transition-all active:scale-95 ${active ? "border-atlas-cyan bg-atlas-cyan/10 text-atlas-cyan" : "border-atlas-border text-atlas-text hover:border-atlas-textTertiary"}`}>
            {label}
        </button>
    );
}
function Seg({ testId, label, active, onClick }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick}
            className={`rounded-lg py-3 font-mono font-bold text-sm border transition-all active:scale-95 ${active ? "bg-atlas-cyan border-atlas-cyan text-atlas-bg" : "border-atlas-border text-atlas-textSecondary hover:border-atlas-textTertiary"}`}>
            {label}
        </button>
    );
}
function StratRow({ testId, name, on, onClick }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick}
            className={`w-full flex items-center gap-3 border rounded-lg p-3.5 mb-2 text-left transition-all active:scale-[0.99] ${on ? "border-atlas-cyan bg-atlas-cyan/10" : "border-atlas-border hover:border-atlas-textTertiary"}`}>
            <span className={`w-5 h-5 rounded flex items-center justify-center border ${on ? "bg-atlas-cyan border-atlas-cyan" : "border-atlas-textTertiary"}`}>
                {on && <Check className="w-3.5 h-3.5 text-atlas-bg" strokeWidth={3} />}
            </span>
            <span className="flex-1 text-atlas-text truncate">{name}</span>
        </button>
    );
}
function PrimaryBtn({ testId, label, onClick, disabled, loading }) {
    return (
        <button type="button" data-testid={testId} onClick={onClick} disabled={disabled}
            className={`w-full flex items-center justify-center gap-2 bg-atlas-cyan text-atlas-bg font-mono font-extrabold text-sm tracking-wide rounded-lg py-3.5 mt-4 transition-all active:scale-[0.98] ${disabled ? "opacity-40 cursor-not-allowed" : "hover:brightness-110"}`}>
            {loading && <Loader2 className="w-4 h-4 animate-spin" />} {label}
        </button>
    );
}
function SummaryRow({ label, value }) {
    return (
        <div className="flex items-center justify-between py-1">
            <span className="text-atlas-textTertiary text-xs">{label}</span>
            <span className="text-atlas-text font-bold">{value}</span>
        </div>
    );
}
