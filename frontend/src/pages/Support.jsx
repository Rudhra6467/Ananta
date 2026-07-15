import { useState } from "react";
import { Link } from "react-router-dom";
import { LifeBuoy, Mail, Copy, Check, ArrowLeft, Send, MessageSquare } from "lucide-react";
import AnantaLogo from "@/components/AnantaLogo";

const SUPPORT_EMAIL = "vamsimadhavyakasiri@gmail.com";

/** Public support / contact page (Support URL). No auth required. */
export default function Support() {
    const [name, setName] = useState("");
    const [from, setFrom] = useState("");
    const [subject, setSubject] = useState("");
    const [message, setMessage] = useState("");
    const [copied, setCopied] = useState(false);

    const copyEmail = async () => {
        try { await navigator.clipboard.writeText(SUPPORT_EMAIL); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* noop */ }
    };

    const sendMail = () => {
        const subj = encodeURIComponent(subject || "Ananta Support request");
        const body = encodeURIComponent(`${message}\n\n— ${name || "Ananta user"}${from ? ` (${from})` : ""}`);
        window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${subj}&body=${body}`;
    };

    return (
        <div className="min-h-screen bg-atlas-bg text-atlas-text" data-testid="support-page">
            <div className="max-w-2xl mx-auto px-5 py-10 md:py-16">
                <Link to="/" data-testid="support-back" className="inline-flex items-center gap-2 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text transition-colors mb-8">
                    <ArrowLeft className="w-3.5 h-3.5" /> BACK TO APP
                </Link>

                <div className="flex items-center gap-3 mb-2">
                    <AnantaLogo className="h-8 w-8" />
                    <span className="font-heading font-semibold tracking-tight text-lg">Ananta</span>
                </div>

                <div className="flex items-center gap-2.5 mt-6 mb-1">
                    <span className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10"><LifeBuoy className="w-5 h-5 text-atlas-cyan" /></span>
                    <h1 className="font-heading font-light text-3xl md:text-4xl tracking-tight">Support & Contact</h1>
                </div>
                <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed mb-8 max-w-xl">
                    Questions, bugs, billing or account help — reach the Ananta team. We typically reply within 1–2 business days.
                </p>

                {/* direct email */}
                <div className="panel border border-atlas-border rounded-2xl p-5 mb-6" data-testid="support-email-card">
                    <div className="label-tag mb-2 flex items-center gap-1.5"><Mail className="w-3.5 h-3.5 text-atlas-cyan" /> EMAIL US</div>
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                        <a href={`mailto:${SUPPORT_EMAIL}`} data-testid="support-email-link" className="font-heading text-base md:text-lg text-atlas-cyan hover:underline break-all">{SUPPORT_EMAIL}</a>
                        <button data-testid="support-copy-email" onClick={copyEmail}
                            className="flex items-center gap-1.5 rounded-lg border border-atlas-border px-3 py-1.5 font-mono text-[10px] tracking-widest text-atlas-textSecondary hover:text-atlas-text hover:border-atlas-textTertiary transition-colors">
                            {copied ? <Check className="w-3.5 h-3.5 text-atlas-positive" /> : <Copy className="w-3.5 h-3.5" />} {copied ? "COPIED" : "COPY"}
                        </button>
                    </div>
                </div>

                {/* message form (opens mail client, addressed to support) */}
                <div className="panel border border-atlas-border rounded-2xl p-5" data-testid="support-form-card">
                    <div className="label-tag mb-3 flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5 text-atlas-cyan" /> SEND A MESSAGE</div>
                    <div className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input data-testid="support-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name"
                                className="atlas-input rounded-lg font-mono text-sm px-3 py-2.5" />
                            <input data-testid="support-from-email" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="Your email" type="email"
                                className="atlas-input rounded-lg font-mono text-sm px-3 py-2.5" />
                        </div>
                        <input data-testid="support-subject" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Subject"
                            className="atlas-input w-full rounded-lg font-mono text-sm px-3 py-2.5" />
                        <textarea data-testid="support-message" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="How can we help?" rows={5}
                            className="atlas-input w-full rounded-lg font-mono text-sm px-3 py-2.5 resize-y" />
                        <button data-testid="support-send" onClick={sendMail} disabled={!message.trim()}
                            className="w-full flex items-center justify-center gap-2 rounded-xl bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-[11px] tracking-widest font-bold px-5 py-3 transition-colors disabled:opacity-40">
                            <Send className="w-4 h-4" /> SEND MESSAGE
                        </button>
                        <p className="font-mono text-[9px] text-atlas-textTertiary text-center">Opens your email app with the message pre-filled to {SUPPORT_EMAIL}.</p>
                    </div>
                </div>

                <div className="font-mono text-[10px] text-atlas-textTertiary text-center pt-8">Ananta.AI · Support & Contact</div>
            </div>
        </div>
    );
}
