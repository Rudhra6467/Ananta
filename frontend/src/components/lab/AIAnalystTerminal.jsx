import { useState, useRef, useEffect } from "react";
import { Brain, Send, Loader2, Sparkles, User } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";

const SUGGESTIONS = [
    "What's my win rate and which strategy performed best?",
    "Why did my trades hit trailing stops recently?",
    "What were the main reasons trades were blocked?",
    "Which market regime has been most profitable?",
];

// AI Quant Analyst terminal — plain-English interrogation of the reasoning log &
// trade ledger. Grounded server-side; owner-only. Multi-turn via a session id.
export default function AIAnalystTerminal({ isOwner, strategy }) {
    const [messages, setMessages] = useState([]); // {role, content}
    const [q, setQ] = useState("");
    const [busy, setBusy] = useState(false);
    const [showAllSug, setShowAllSug] = useState(false);
    const sessionRef = useRef(null);
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, [messages, busy]);

    const ask = async (question) => {
        const text = (question ?? q).trim();
        if (!text || busy) return;
        if (!isOwner) { toast.error("Owner login required"); return; }
        setMessages((m) => [...m, { role: "user", content: text }]);
        setQ("");
        setBusy(true);
        try {
            const res = await api.analyticsAiQuery(text, sessionRef.current, strategy);
            sessionRef.current = res.session_id;
            setMessages((m) => [...m, { role: "assistant", content: res.answer }]);
        } catch (e) {
            const detail = e?.response?.data?.detail || e?.message || "request failed";
            setMessages((m) => [...m, { role: "assistant", content: `⚠︎ ${detail}` }]);
            toast.error("AI ANALYST ERROR", { description: String(detail) });
        } finally { setBusy(false); }
    };

    return (
        <div className="panel border-atlas-border rounded-xl overflow-hidden" data-testid="ai-analyst-terminal">
            <div className="px-4 py-3 border-b border-atlas-border flex items-center gap-2">
                <Brain className="w-4 h-4 text-atlas-positive" strokeWidth={2} />
                <span className="font-heading font-medium text-atlas-text">AI Quant Analyst</span>
                <span className="font-mono text-[9px] uppercase tracking-widest text-atlas-textTertiary ml-1">{strategy ? `scoped: ${strategy}` : "Claude Sonnet · grounded on your data"}</span>
            </div>

            <div ref={scrollRef} className="max-h-[42vh] min-h-[160px] overflow-y-auto atlas-scroll p-4 space-y-3" data-testid="ai-analyst-messages">
                {messages.length === 0 && (
                    <div className="py-4">
                        <div className="flex items-center gap-2 font-mono text-[11px] text-atlas-textSecondary mb-3">
                            <Sparkles className="w-3.5 h-3.5 text-atlas-positive" /> Ask about your trades, exits, blocks or regimes:
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {(showAllSug ? SUGGESTIONS : SUGGESTIONS.slice(0, 1)).map((sug) => (
                                <button key={sug} data-testid="ai-suggestion" onClick={() => ask(sug)} disabled={busy || !isOwner}
                                    className="text-left px-3 py-2 rounded-lg border border-atlas-border font-mono text-[11px] text-atlas-textSecondary hover:border-atlas-positive/50 hover:text-atlas-text transition-colors disabled:opacity-40">
                                    {sug}
                                </button>
                            ))}
                        </div>
                        {SUGGESTIONS.length > 1 && (
                            <button data-testid="ai-suggestion-load-more" onClick={() => setShowAllSug((v) => !v)}
                                className="mt-2 font-mono text-[10px] tracking-widest text-atlas-textTertiary hover:text-atlas-text transition-colors">
                                {showAllSug ? "SHOW LESS" : `LOAD MORE (${SUGGESTIONS.length - 1})`}
                            </button>
                        )}
                    </div>
                )}
                {messages.map((m, i) => (
                    <div key={i} data-testid={`ai-msg-${m.role}`} className={`flex gap-2.5 ${m.role === "user" ? "justify-end" : ""}`}>
                        {m.role === "assistant" && <Brain className="w-4 h-4 text-atlas-positive shrink-0 mt-1" />}
                        <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap ${
                            m.role === "user" ? "bg-atlas-cyan/10 border border-atlas-cyan/30 text-atlas-text" : "bg-atlas-panel border border-atlas-border text-atlas-textSecondary"
                        }`}>{m.content}</div>
                        {m.role === "user" && <User className="w-4 h-4 text-atlas-cyan shrink-0 mt-1" />}
                    </div>
                ))}
                {busy && (
                    <div className="flex gap-2.5 items-center" data-testid="ai-thinking">
                        <Brain className="w-4 h-4 text-atlas-positive shrink-0" />
                        <div className="bg-atlas-panel border border-atlas-border rounded-xl px-3.5 py-2.5 font-mono text-[11px] text-atlas-textTertiary flex items-center gap-2">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" /> analysing your ledger…
                        </div>
                    </div>
                )}
            </div>

            <div className="border-t border-atlas-border p-3 flex items-center gap-2">
                <input
                    data-testid="ai-analyst-input"
                    value={q} onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
                    placeholder={isOwner ? "Ask the analyst a question…" : "Owner login required"}
                    disabled={busy || !isOwner}
                    className="atlas-input flex-1 rounded-lg font-mono text-sm px-3 py-2 disabled:opacity-50"
                />
                <Button data-testid="ai-analyst-send-btn" onClick={() => ask()} disabled={busy || !isOwner || !q.trim()} className="gap-1.5">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </Button>
            </div>
        </div>
    );
}
