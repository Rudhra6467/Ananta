import { Link } from "react-router-dom";
import { ShieldCheck, ArrowLeft, Mail } from "lucide-react";
import AnantaLogo from "@/components/AnantaLogo";

const SUPPORT_EMAIL = "vamsimadhavyakasiri@gmail.com";
const UPDATED = "July 15, 2026";

/** Public Privacy Policy page (Privacy Policy URL for the App Store). No auth required. */
export default function Privacy() {
    return (
        <div className="min-h-screen bg-atlas-bg text-atlas-text" data-testid="privacy-page">
            <div className="max-w-3xl mx-auto px-5 py-10 md:py-16">
                <Link to="/" data-testid="privacy-back" className="inline-flex items-center gap-2 font-mono text-[11px] tracking-widest text-atlas-textSecondary hover:text-atlas-text transition-colors mb-8">
                    <ArrowLeft className="w-3.5 h-3.5" /> BACK TO APP
                </Link>

                <div className="flex items-center gap-3 mb-6">
                    <AnantaLogo className="h-8 w-8" />
                    <span className="font-heading font-semibold tracking-tight text-lg">Ananta</span>
                </div>

                <div className="flex items-center gap-2.5 mb-1">
                    <span className="w-10 h-10 rounded-xl grid place-items-center border border-atlas-cyan/40 bg-atlas-cyan/10"><ShieldCheck className="w-5 h-5 text-atlas-cyan" /></span>
                    <h1 className="font-heading font-light text-3xl md:text-4xl tracking-tight">Privacy Policy</h1>
                </div>
                <p className="font-mono text-[11px] text-atlas-textTertiary mb-8">Last updated: {UPDATED}</p>

                <div className="space-y-7 text-atlas-textSecondary leading-relaxed text-[14px]">
                    <Section title="Overview">
                        Ananta (&ldquo;Ananta&rdquo;, &ldquo;we&rdquo;, &ldquo;us&rdquo;) is a research and paper-trading platform that helps you test, validate, and simulate trading strategies before committing real capital. This policy explains what data we collect, how we use it, and your choices. By using the Ananta app or website, you agree to this policy.
                    </Section>

                    <Section title="Not Financial Advice">
                        Ananta is a research and educational tool. Paper trading uses simulated capital and live market data — it does not execute real trades unless you explicitly connect and authorize a live exchange. Nothing in the app constitutes investment, financial, or tax advice.
                    </Section>

                    <Section title="Information We Collect">
                        <B>Account information.</B> When you create an account or request access, we collect your email address (and name if provided) to authenticate you and manage your account.<br /><br />
                        <B>Content you create.</B> Strategies you build or import, watchlists, paper-trading configuration, and the questions you ask our in-app AI assistant.
                        <br /><br />
                        <B>Usage &amp; device data.</B> Basic technical data needed to operate the service (e.g. session identifiers, app interactions, and log data for reliability and security).
                        <br /><br />
                        We do <B>not</B> collect precise location, contacts, photos, or health data, and we do <B>not</B> use third-party advertising or cross-app tracking SDKs.
                    </Section>

                    <Section title="How We Use Your Information">
                        <List items={[
                            "Provide and operate the app (authentication, running strategy research, simulated/paper trading, and analytics).",
                            "Generate AI responses to questions you submit to the in-app assistant.",
                            "Maintain security, prevent abuse, and debug/improve reliability.",
                            "Communicate with you about your account, support requests, and service updates.",
                        ]} />
                    </Section>

                    <Section title="AI Processing & Third Parties">
                        When you use AI features (e.g. &ldquo;Ask Ananta&rdquo; or the Weekly Review), the content of your request and relevant account context is sent to our AI model provider solely to generate a response for you. We use reputable providers (such as Anthropic / OpenAI / Google via our managed integration) and market-data providers to deliver core functionality. These providers process data on our behalf and are not permitted to use it for their own advertising. We do not sell your personal information.
                    </Section>

                    <Section title="Exchange Credentials">
                        If you choose to connect a live exchange (optional), any API keys you provide are stored to operate the service and are never displayed back in full or shared. You can remove them at any time. If you only use paper trading, no exchange credentials are required.
                    </Section>

                    <Section title="Data Retention & Security">
                        We retain your data for as long as your account is active or as needed to provide the service and meet legal obligations. We apply reasonable technical and organizational safeguards (encrypted transport, hashed passwords, access controls). No method of transmission or storage is 100% secure.
                    </Section>

                    <Section title="Your Choices & Rights">
                        You may request access to, correction of, or deletion of your personal data, and you may close your account at any time. To exercise these rights, contact us at the email below and we will respond within a reasonable timeframe.
                    </Section>

                    <Section title="Children's Privacy">
                        Ananta is not directed to children under 13 (or the minimum age required in your jurisdiction), and we do not knowingly collect data from them.
                    </Section>

                    <Section title="International Users">
                        Your data may be processed in countries other than your own. Where required, we take steps to ensure appropriate safeguards for such transfers.
                    </Section>

                    <Section title="Changes to This Policy">
                        We may update this policy from time to time. Material changes will be reflected by updating the &ldquo;Last updated&rdquo; date on this page.
                    </Section>

                    <Section title="Contact Us">
                        Questions about this policy or your data? Email us:
                        <a href={`mailto:${SUPPORT_EMAIL}`} data-testid="privacy-email" className="mt-3 inline-flex items-center gap-2 font-heading text-atlas-cyan hover:underline">
                            <Mail className="w-4 h-4" /> {SUPPORT_EMAIL}
                        </a>
                    </Section>
                </div>

                <div className="font-mono text-[10px] text-atlas-textTertiary text-center pt-10">Ananta.AI · Privacy Policy · {UPDATED}</div>
            </div>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <section>
            <h2 className="font-heading text-lg text-atlas-text mb-2">{title}</h2>
            <div className="font-body">{children}</div>
        </section>
    );
}
function B({ children }) { return <span className="text-atlas-text font-semibold">{children}</span>; }
function List({ items }) {
    return (
        <ul className="list-disc pl-5 space-y-1.5 marker:text-atlas-cyan">
            {items.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
    );
}
