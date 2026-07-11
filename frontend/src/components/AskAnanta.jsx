import { useEffect, useRef, useState } from "react";
import { Sparkles, X, ArrowUp, Zap } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useAccessGate } from "@/context/AccessGateContext";

const SUGGESTIONS = {
    cockpit: ["Today's performance", "Why were setups rejected?", "What's the market regime?", "Start paper trading"],
    trade: ["Explain this position", "Pause Hunter", "Add a strategy", "Why is a trade open?"],
    strategy: ["What's my best strategy?", "Explain Hunter", "Import or build a strategy"],
    research: ["How do I validate a strategy?", "Explain the AI score", "Why did this fail?"],
    workspace: ["Explain this page", "What does the exit engine do?", "Paper vs Live?", "Configure risk"],
};

// AppShell tab ids → canonical backend tab names.
const TAB_MAP = { dashboard: "cockpit", trade: "trade", strategies: "strategy", research: "research", workspace: "workspace" };

const Switch = ({ testid, on, onToggle, track }) => (
    <button data-testid={testid} role="switch" aria-checked={on} onClick={onToggle}
        title={on ? "Turn Ask Ananta off" : "Turn Ask Ananta on"}
        className={`relative w-8 h-[18px] rounded-full transition-colors shrink-0 ${on ? track : "bg-atlas-border"}`}>
        <span className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-all ${on ? "left-[16px]" : "left-[2px]"}`} />
    </button>
);

export default function AskAnanta({ tab }) {
    const canonicalTab = TAB_MAP[tab] || tab;
    const { isOwner } = useAuth();
    const { gate } = useAccessGate();
    const [enabled, setEnabled] = useState(false);
    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");
    const [busy, setBusy] = useState(false);
    const [msgs, setMsgs] = useState([]);
    const session = useRef(undefined);
    const scrollRef = useRef(null);

    useEffect(() => {
        const load = () => api.settings().then((s) => setEnabled(!!s.ask_ananta_enabled)).catch(() => {});
        load();
        const t = setInterval(load, 20000);
        return () => clearInterval(t);
    }, []);
    useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [msgs, busy]);

    // Public visitors see the copilot chip but opening it is gated to the waitlist.
    if (!isOwner) {
        return (
            <button data-testid="ask-ananta-chip" onClick={() => gate("Ask Ananta AI Copilot")}
                className="fixed bottom-24 left-4 z-40 flex items-center gap-2 rounded-full bg-atlas-cyan text-black font-mono text-xs font-bold px-4 py-2 shadow-lg hover:brightness-110 active:scale-95 transition-all">
                <Sparkles className="w-4 h-4" /> Ask Ananta
            </button>
        );
    }

    const toggleEnabled = async (e) => {
        e?.stopPropagation?.();
        try {
            const s = await api.updateSettings({ ask_ananta_enabled: !enabled });
            const next = !!s.ask_ananta_enabled;
            setEnabled(next);
            if (!next) setOpen(false);
            toast.success(`Ask Ananta ${next ? "on" : "off"}`);
        } catch (err) { toast.error("Toggle failed", { description: String(err?.message || err) }); }
    };

    const send = async (text) => {
        const question = (text || "").trim();
        if (!question) return;
        setMsgs((m) => [...m, { role: "user", text: question }]);
        setQ(""); setBusy(true);
        try {
            const r = await api.anantaAsk(question, session.current, canonicalTab);
            session.current = r.session_id;
            setMsgs((m) => [...m, { role: "assistant", text: r.answer, actions: r.actions || [] }]);
        } catch (e) {
            setMsgs((m) => [...m, { role: "assistant", text: e?.response?.data?.detail || e?.message || "Ask Ananta unavailable." }]);
        } finally { setBusy(false); }
    };

    const runAction = async (a) => {
        if (!window.confirm(`${a.label}?`)) return;
        try {
            if (a.type === "strategy_disable") { await api.strategySetState(a.params.key, { status: "DISABLED" }); toast.success(`${a.params.key} paused`); }
            else if (a.type === "strategy_enable") { await api.strategySetState(a.params.key, { enabled: true }); toast.success(`${a.params.key} enabled`); }
            else if (a.type === "open_research") { setOpen(false); window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "research" } })); }
            else if (a.type === "open_wizard") { setOpen(false); window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "dashboard" } })); window.dispatchEvent(new Event("ananta:wizard")); }
            else if (a.type === "open_strategy_add") { setOpen(false); window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "strategies" } })); }
            else if (a.type === "open_workspace_setting") { setOpen(false); window.dispatchEvent(new CustomEvent("ananta:navigate", { detail: { tabId: "workspace" } })); }
        } catch (e) { toast.error("Action failed", { description: String(e?.message || e) }); }
    };

    return (
        <>
            {!open && (
                <div data-testid="ask-ananta-chip"
                    className={`fixed bottom-24 left-4 z-40 flex items-center gap-2.5 rounded-full font-mono text-xs font-bold pl-4 pr-2.5 py-2 shadow-lg transition-all ${enabled ? "bg-atlas-cyan text-black" : "bg-atlas-panelHover text-atlas-textSecondary border border-atlas-border"}`}>
                    <button data-testid="ask-ananta-open" onClick={() => enabled && setOpen(true)} disabled={!enabled}
                        className={`flex items-center gap-2 transition-transform ${enabled ? "hover:brightness-110 active:scale-95" : "cursor-default"}`}>
                        <Sparkles className="w-4 h-4" /> Ask Ananta
                    </button>
                    <Switch testid="ask-ananta-switch" on={enabled} onToggle={toggleEnabled} track="bg-black/75" />
                </div>
            )}
            {open && (
                <div data-testid="ask-ananta-panel" className="fixed bottom-24 left-4 z-40 w-[min(400px,calc(100vw-2rem))] panel border-atlas-border rounded-2xl overflow-hidden flex flex-col shadow-2xl" style={{ maxHeight: "70vh" }}>
                    <div className="flex items-center justify-between px-4 py-3 border-b border-atlas-border">
                        <div className="flex items-center gap-2 font-heading text-base text-atlas-text"><Sparkles className="w-4 h-4 text-atlas-cyan" /> Ask Ananta</div>
                        <div className="flex items-center gap-3">
                            <Switch testid="ask-ananta-switch-panel" on={enabled} onToggle={toggleEnabled} track="bg-atlas-cyan" />
                            <button data-testid="ask-ananta-close" onClick={() => setOpen(false)} className="text-atlas-textSecondary hover:text-white"><X className="w-5 h-5" /></button>
                        </div>
                    </div>
                    <div ref={scrollRef} className="flex-1 overflow-y-auto atlas-scroll p-4 space-y-3">
                        {msgs.length === 0 ? (
                            <div className="space-y-2">
                                <div className="font-mono text-[11px] text-atlas-textTertiary">Suggested for this tab:</div>
                                {(SUGGESTIONS[canonicalTab] || SUGGESTIONS.cockpit).map((s) => (
                                    <button key={s} onClick={() => send(s)} className="w-full text-left rounded-lg border border-atlas-cyan/40 text-atlas-cyan hover:bg-atlas-cyan/10 font-mono text-[12px] px-3 py-2 transition-colors">{s}</button>
                                ))}
                            </div>
                        ) : msgs.map((m, i) => (
                            <div key={i} className={`rounded-xl p-3 text-[13px] leading-relaxed max-w-[92%] ${m.role === "user" ? "bg-atlas-cyan text-black ml-auto" : "bg-atlas-panelHover text-atlas-text border border-atlas-border"}`}>
                                <div className="whitespace-pre-wrap">{m.text}</div>
                                {(m.actions || []).length > 0 && (
                                    <div className="mt-2 space-y-1.5">
                                        {m.actions.map((a, j) => (
                                            <button key={j} data-testid={`ananta-action-${a.type}`} onClick={() => runAction(a)}
                                                className="w-full flex items-center gap-1.5 rounded-lg border border-atlas-cyan/40 bg-atlas-cyan/10 text-atlas-cyan font-mono text-[12px] px-3 py-1.5 hover:bg-atlas-cyan/20 transition-colors">
                                                <Zap className="w-3.5 h-3.5" /> {a.label}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                        {busy && <div className="font-mono text-[11px] text-atlas-textTertiary">Ananta is thinking…</div>}
                    </div>
                    <div className="flex items-center gap-2 p-3 border-t border-atlas-border">
                        <input data-testid="ask-ananta-input" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(q)}
                            placeholder="Ask about your trading system…" className="flex-1 bg-atlas-bg border border-atlas-border rounded-full px-4 py-2 font-mono text-[13px] text-white focus:border-atlas-cyan outline-none" />
                        <button data-testid="ask-ananta-send" onClick={() => send(q)} disabled={busy} className="w-10 h-10 rounded-full bg-atlas-cyan text-black grid place-items-center disabled:opacity-50"><ArrowUp className="w-5 h-5" /></button>
                    </div>
                </div>
            )}
        </>
    );
}
