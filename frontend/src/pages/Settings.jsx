import { useEffect, useState } from "react";
import { Save, ShieldOff, Key, AlertTriangle, Zap, Info } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import KillSwitchPanel from "@/components/KillSwitchPanel";
import AnalyticsPanel from "@/components/AnalyticsPanel";
import GraduationScorecard from "@/components/GraduationScorecard";
import { useAuth } from "@/context/AuthContext";

export default function SettingsPage() {
    const [s, setS] = useState(null);
    const [saving, setSaving] = useState(false);
    const [risk, setRisk] = useState(null);
    const [running, setRunning] = useState(false);
    const [lastRun, setLastRun] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [excludeSynthetic, setExcludeSynthetic] = useState(false);
    const { isOwner } = useAuth();

    useEffect(() => {
        api.settings().then(setS).catch(() => setS(null));
        api.riskStatus().then(setRisk).catch(() => {});
        const t = setInterval(() => {
            api.riskStatus().then(setRisk).catch(() => {});
        }, 12000);
        return () => clearInterval(t);
    }, []);

    useEffect(() => {
        api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {});
        const t = setInterval(() => {
            api.analyticsPerformance(excludeSynthetic).then(setAnalytics).catch(() => {});
        }, 15000);
        return () => clearInterval(t);
    }, [excludeSynthetic]);

    const upd = (patch) => setS((cur) => ({ ...cur, ...patch }));

    const runCycleNow = async () => {
        setRunning(true);
        try {
            const out = await api.runCycle();
            setLastRun(out.ran_at);
            toast.success("CYCLE COMPLETED", {
                description: `${(out.results || []).length} symbols evaluated`,
            });
            api.riskStatus().then(setRisk).catch(() => {});
        } catch (e) {
            toast.error("CYCLE FAILED", { description: String(e?.message || e) });
        } finally {
            setRunning(false);
        }
    };

    const save = async () => {
        if (!s) return;
        setSaving(true);
        try {
            // strip masked secrets
            const payload = { ...s };
            ["coinbase_api_secret", "kraken_api_secret"].forEach((k) => {
                if (payload[k] && /^•+$/.test(payload[k])) delete payload[k];
            });
            const next = await api.updateSettings(payload);
            setS(next);
            toast.success("SETTINGS SAVED", { description: "Risk engine and exchange config updated." });
        } catch (e) {
            toast.error("SAVE FAILED", { description: String(e?.message || e) });
        } finally {
            setSaving(false);
        }
    };

    const toggleKill = async (val) => {
        try {
            const next = await api.updateSettings({ manual_kill_switch: val });
            setS(next);
            toast[val ? "error" : "success"](val ? "MANUAL KILL ENGAGED" : "MANUAL KILL RELEASED", {
                description: val ? "All new trades blocked until released." : "Trading resumes on next cycle.",
            });
        } catch (e) {
            toast.error("UPDATE FAILED", { description: String(e?.message || e) });
        }
    };

    const clearHistory = async (alsoResetPortfolio) => {
        const msg = alsoResetPortfolio
            ? "Wipe ALL trades, reasoning logs AND reset portfolio cash to $300? This cannot be undone."
            : "Wipe ALL trades and reasoning logs? Portfolio cash & open positions stay untouched.";
        if (!window.confirm(msg)) return;
        try {
            const out = await api.clearHistory(alsoResetPortfolio);
            toast.success("HISTORY CLEARED", {
                description: `${out.trades_deleted} trades, ${out.reasoning_deleted} reasoning rows removed.`,
            });
        } catch (e) {
            toast.error("CLEAR FAILED", { description: String(e?.message || e) });
        }
    };

    if (!s) {
        return (
            <div className="panel p-8 font-mono text-[12px] text-atlas-textSecondary" data-testid="settings-loading">
                <span className="blink-cursor">LOADING SETTINGS</span>
            </div>
        );
    }

    return (
        <TooltipProvider delayDuration={120}>
        <div className="space-y-6" data-testid="settings-page">
            {/* MANUAL KILL HERO */}
            <section className="panel" data-testid="settings-manual-kill">
                <div className="px-5 pt-4 pb-3 border-b border-atlas-border flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ShieldOff className="w-4 h-4 text-atlas-negative" />
                        <div>
                            <div className="label-tag">EMERGENCY · MANUAL KILL-SWITCH</div>
                            <h3 className="font-heading text-xl font-bold mt-1">Operator Override</h3>
                        </div>
                    </div>
                    <Switch
                        data-testid="manual-kill-switch"
                        checked={s.manual_kill_switch}
                        onCheckedChange={toggleKill}
                        className="data-[state=checked]:bg-atlas-negative data-[state=unchecked]:bg-atlas-border"
                    />
                </div>
                <div className="px-5 py-4 flex items-start gap-3 text-[12px] text-atlas-textSecondary">
                    <AlertTriangle className={`w-4 h-4 mt-0.5 ${s.manual_kill_switch ? "text-atlas-negative" : "text-atlas-textTertiary"}`} />
                    <div>
                        {s.manual_kill_switch ? (
                            <span className="text-atlas-negative font-mono">
                                ENGAGED · all new orders blocked. Existing simulated positions remain. Release the switch to resume.
                            </span>
                        ) : (
                            <span className="font-mono">
                                Released. Engine will trade when conviction + microstructure align and kill-switches are clear.
                            </span>
                        )}
                    </div>
                </div>
            </section>

            {/* RISK MONITOR + RUN CYCLE (migrated from Dashboard) */}
            <section className="panel" data-testid="settings-risk-monitor">
                <SectionHeader label="EXECUTION CONTROLS" title="Risk Monitor & Manual Cycle" />
                <div className="p-5 grid grid-cols-1 lg:grid-cols-3 gap-4">
                    <div className="lg:col-span-2">
                        <KillSwitchPanel risk={risk} />
                    </div>
                    <div className="panel border-atlas-border h-full flex flex-col">
                        <div className="px-4 pt-3 pb-2 border-b border-atlas-border">
                            <div className="label-tag">MANUAL CYCLE</div>
                        </div>
                        <div className="p-4 flex-1 flex flex-col justify-between gap-3">
                            <div>
                                <div className="text-[10px] font-mono text-atlas-textSecondary mb-2">
                                    Loop runs every 90s automatically. Trigger an immediate evaluation cycle below.
                                </div>
                                {lastRun && (
                                    <div className="text-[10px] font-mono text-atlas-textTertiary">
                                        LAST: {new Date(lastRun).toLocaleTimeString()}
                                    </div>
                                )}
                            </div>
                            <Button
                                data-testid="settings-run-cycle-btn"
                                onClick={runCycleNow}
                                disabled={running || !isOwner}
                                title={isOwner ? "" : "Owner login required"}
                                className="rounded-none bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-xs tracking-widest font-bold transition-colors disabled:opacity-50"
                            >
                                {running ? (
                                    <span className="blink-cursor">RUNNING</span>
                                ) : (
                                    <>
                                        <Zap className="w-3.5 h-3.5 mr-2" strokeWidth={2.5} />
                                        RUN CYCLE NOW
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>
                </div>
            </section>

            {/* GRADUATION READINESS SCORECARD (paper -> live gate) */}
            <GraduationScorecard />

            {/* PERFORMANCE ANALYTICS (relocated from the home dashboard) */}
            <div data-testid="settings-analytics">
                <AnalyticsPanel
                    analytics={analytics}
                    excludeSynthetic={excludeSynthetic}
                    onToggleSynthetic={setExcludeSynthetic}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* RISK THRESHOLDS */}
                <section className="panel" data-testid="settings-risk-thresholds">
                    <SectionHeader label="RISK ENGINE · LAYER 6" title="Risk Thresholds" />
                    <div className="p-5 space-y-6">
                        <SliderField
                            id="spread"
                            label="MAX SPREAD"
                            description="Hard kill: trades blocked if bid/ask spread widens past this."
                            value={s.max_spread_pct}
                            min={0.05}
                            max={2}
                            step={0.05}
                            unit="%"
                            onChange={(v) => upd({ max_spread_pct: v })}
                        />
                        <SliderField
                            id="daily-loss"
                            label="MAX DAILY LOSS"
                            description="Hard kill: trades blocked if equity drops by this % from day start."
                            value={s.max_daily_loss_pct}
                            min={0.5}
                            max={10}
                            step={0.1}
                            unit="%"
                            onChange={(v) => upd({ max_daily_loss_pct: v })}
                        />
                        <SliderField
                            id="taker-fee"
                            label="TAKER FEE (PER LEG)"
                            description="Simulated exchange friction applied to every PAPER/DRY_RUN trade. Kraken Pro base = 0.40%."
                            value={s.taker_fee_pct}
                            min={0}
                            max={1}
                            step={0.01}
                            unit="%"
                            onChange={(v) => upd({ taker_fee_pct: v })}
                        />
                        <SliderField
                            id="min-confidence"
                            label="MIN LLM CONFIDENCE"
                            description="Soft block: don't open new positions below this LLM conviction."
                            value={s.min_confidence}
                            min={0}
                            max={1}
                            step={0.05}
                            unit=""
                            onChange={(v) => upd({ min_confidence: v })}
                        />
                        <div className="grid grid-cols-2 gap-4">
                            <SliderField
                                id="size-min"
                                label="MIN POSITION SIZE"
                                tooltip="Legacy %-of-equity sizing floor. Only used when Adaptive Lot Sizing is OFF; otherwise USD lots ($20/$30/$50) drive size."
                                value={s.position_size_pct_min}
                                min={0.1}
                                max={5}
                                step={0.1}
                                unit="%"
                                onChange={(v) => upd({ position_size_pct_min: v })}
                            />
                            <SliderField
                                id="size-max"
                                label="MAX POSITION SIZE"
                                tooltip="Legacy %-of-equity sizing ceiling. Only used when Adaptive Lot Sizing is OFF; the engine scales between min and max by AI confidence."
                                value={s.position_size_pct_max}
                                min={0.5}
                                max={10}
                                step={0.1}
                                unit="%"
                                onChange={(v) => upd({ position_size_pct_max: v })}
                            />
                        </div>
                    </div>
                </section>

                {/* ADAPTIVE SIZING */}
                <section className="panel" data-testid="settings-adaptive-sizing">
                    <SectionHeader label="ADAPTIVE LOT SIZING · LAYER 5b" title="USD-Lot per Setup Strength" />
                    <div className="p-5 space-y-5">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="label-tag">ADAPTIVE SIZING</div>
                                <div className="mt-1 text-[11px] font-mono text-atlas-textSecondary">
                                    When enabled, BUY notionals come from the USD lots below. STRONG setups (trend + volatility + conviction) get the bigger lot.
                                </div>
                            </div>
                            <Switch
                                data-testid="adaptive-sizing-switch"
                                checked={!!s.adaptive_sizing_enabled}
                                onCheckedChange={(v) => upd({ adaptive_sizing_enabled: v })}
                                className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border"
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <NumberField
                                id="normal-lot-usd"
                                label="NORMAL LOT (USD)"
                                tooltip="Fixed dollar size for a NORMAL-conviction swing entry. Default $20."
                                value={s.normal_lot_usd}
                                min={1}
                                max={1000}
                                step={0.5}
                                onChange={(v) => upd({ normal_lot_usd: v })}
                            />
                            <NumberField
                                id="strong-lot-usd"
                                label="STRONG LOT (USD)"
                                tooltip="Larger dollar size for a STRONG entry — fires only when conviction AND trend AND volatility all align. Default $30."
                                value={s.strong_lot_usd}
                                min={1}
                                max={1000}
                                step={0.5}
                                onChange={(v) => upd({ strong_lot_usd: v })}
                            />
                        </div>

                        <SliderField
                            id="strong-min-confidence"
                            label="STRONG · MIN LLM CONFIDENCE"
                            description="Macro conviction floor to qualify as STRONG."
                            value={s.strong_min_confidence}
                            min={0}
                            max={1}
                            step={0.05}
                            unit=""
                            onChange={(v) => upd({ strong_min_confidence: v })}
                        />
                        <div className="grid grid-cols-2 gap-4">
                            <SliderField
                                id="strong-min-atr-pct"
                                label="STRONG · MIN ATR PERCENTILE"
                                description="1h ATR rank vs last 30d."
                                value={s.strong_min_atr_percentile}
                                min={0}
                                max={100}
                                step={1}
                                unit="%"
                                onChange={(v) => upd({ strong_min_atr_percentile: v })}
                            />
                            <SliderField
                                id="strong-min-adx"
                                label="STRONG · MIN 1H ADX"
                                description="Trend-strength floor."
                                value={s.strong_min_adx}
                                min={0}
                                max={60}
                                step={1}
                                unit=""
                                onChange={(v) => upd({ strong_min_adx: v })}
                            />
                        </div>

                        <NumberField
                            id="max-concurrent"
                            label="MAX CONCURRENT POSITIONS"
                            value={s.max_concurrent_positions}
                            min={1}
                            max={20}
                            step={1}
                            onChange={(v) => upd({ max_concurrent_positions: Math.round(v) })}
                            description="Beyond this, fresh BUY signals are queued for the next cycle."
                        />
                    </div>
                </section>

                {/* EXITS & WATCHER */}
                <section className="panel" data-testid="settings-exits">
                    <SectionHeader label="EXITS · POSITION WATCHER" title="Stop-Loss & Trailing Take-Profit" />
                    <div className="p-5 space-y-5">
                        <SliderField
                            id="stop-loss-pct"
                            label="HARD STOP-LOSS"
                            description="Exit a single trade as soon as drawdown reaches this %."
                            value={s.stop_loss_pct}
                            min={0.1}
                            max={10}
                            step={0.1}
                            unit="%"
                            onChange={(v) => upd({ stop_loss_pct: v })}
                        />
                        <div className="grid grid-cols-2 gap-4">
                            <SliderField
                                id="trail-arm-pct"
                                label="TRAIL ARM"
                                description="Unrealized gain at which the trailing stop activates."
                                value={s.trail_arm_pct}
                                min={0.5}
                                max={20}
                                step={0.1}
                                unit="%"
                                onChange={(v) => upd({ trail_arm_pct: v })}
                            />
                            <SliderField
                                id="trail-distance-pct"
                                label="TRAIL DISTANCE (FALLBACK)"
                                description="Static pullback-from-peak exit. Used only when the volatility-adaptive trail is off or ATR percentile is unknown; otherwise the trail flexes 2%–6% with entry volatility."
                                value={s.trail_distance_pct}
                                min={0.1}
                                max={10}
                                step={0.1}
                                unit="%"
                                onChange={(v) => upd({ trail_distance_pct: v })}
                            />
                        </div>
                        <NumberField
                            id="watcher-interval"
                            label="POSITION WATCHER INTERVAL (SECONDS)"
                            value={s.position_watcher_interval_seconds}
                            min={5}
                            max={300}
                            step={1}
                            onChange={(v) => upd({ position_watcher_interval_seconds: Math.round(v) })}
                            description="How often open positions are checked for SL / trailing take-profit. Skips Gemini for speed."
                        />
                        <div className="border-t border-atlas-border pt-5">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="label-tag">VOLATILITY-ADAPTIVE TRAIL</div>
                                    <div className="mt-1 text-[11px] font-mono text-atlas-textSecondary">
                                        Trail distance = clamp(k × ATR percentile, min, max). Calm tape locks gains tighter; volatile entries get a wider leash so violent retracements don&apos;t shake the bot out.
                                    </div>
                                </div>
                                <Switch
                                    data-testid="dynamic-trail-switch"
                                    checked={!!s.dynamic_trail_enabled}
                                    onCheckedChange={(v) => upd({ dynamic_trail_enabled: v })}
                                    className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4 mt-4">
                                <SliderField
                                    id="dynamic-trail-min"
                                    label="TRAIL FLOOR"
                                    tooltip="Tightest the adaptive trailing distance can get, even in calm/low-volatility conditions. Default 2%."
                                    value={s.dynamic_trail_min_pct}
                                    min={0.5}
                                    max={5}
                                    step={0.1}
                                    unit="%"
                                    onChange={(v) => upd({ dynamic_trail_min_pct: v })}
                                />
                                <SliderField
                                    id="dynamic-trail-max"
                                    label="TRAIL CEILING"
                                    tooltip="Widest the adaptive trailing distance can get in high-volatility conditions, giving trends maximum room. Default 6%."
                                    value={s.dynamic_trail_max_pct}
                                    min={3}
                                    max={15}
                                    step={0.1}
                                    unit="%"
                                    onChange={(v) => upd({ dynamic_trail_max_pct: v })}
                                />
                            </div>
                        </div>
                    </div>
                </section>

                {/* VAULT ENGINE (capital sourcing) */}
                <section className="panel" data-testid="settings-vault">
                    <SectionHeader label="VAULT ENGINE" title="Capital Sourcing" />
                    <div className="p-5 space-y-5">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="label-tag">LIVE BALANCE SYNC</div>
                                <div className="mt-1 text-[11px] font-mono text-atlas-textSecondary">
                                    When ON (LIVE / DRY-RUN only), the bot pulls your free USD + USDC from the exchange each cycle and caps deployable capital at the override below. PAPER mode stays fully simulated.
                                </div>
                            </div>
                            <Switch
                                data-testid="vault-sync-switch"
                                checked={!!s.vault_sync_enabled}
                                onCheckedChange={(v) => upd({ vault_sync_enabled: v })}
                                className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border"
                            />
                        </div>
                        <NumberField
                            id="vault-max-override-usd"
                            label="MAX DEPLOYABLE CAPITAL (USD)"
                            value={s.vault_max_override_usd}
                            min={1}
                            max={1000000}
                            step={1}
                            onChange={(v) => upd({ vault_max_override_usd: v })}
                            description="Hard ceiling on the capital the bot can deploy. Used as the cap even when live balance is larger; the smaller live balance wins when sync is on."
                        />
                        <div className="flex items-center justify-between border-t border-atlas-border pt-5">
                            <div>
                                <div className="label-tag">4H TREND FILTER</div>
                                <div className="mt-1 text-[11px] font-mono text-atlas-textSecondary">
                                    Require Price &gt; 4h EMA50 &gt; 4h EMA200 before any swing BUY. Keeps entries aligned with the higher-timeframe uptrend.
                                </div>
                            </div>
                            <Switch
                                data-testid="htf-trend-switch"
                                checked={!!s.htf_trend_enabled}
                                onCheckedChange={(v) => upd({ htf_trend_enabled: v })}
                                className="data-[state=checked]:bg-atlas-cyan data-[state=unchecked]:bg-atlas-border"
                            />
                        </div>
                    </div>
                </section>

                {/* EXCHANGE FRICTION (fees + paper slippage) */}
                <section className="panel" data-testid="settings-friction">
                    <SectionHeader label="EXCHANGE FRICTION" title="Fees & Slippage" />
                    <div className="p-5 grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <NumberField
                            id="taker-fee-pct"
                            label="TAKER FEE (%)"
                            value={s.taker_fee_pct}
                            min={0}
                            max={5}
                            step={0.01}
                            onChange={(v) => upd({ taker_fee_pct: v })}
                            description="Per-leg taker fee for market fills (breakouts) and all exits."
                        />
                        <NumberField
                            id="maker-fee-pct"
                            label="MAKER FEE (%)"
                            value={s.maker_fee_pct}
                            min={0}
                            max={5}
                            step={0.01}
                            onChange={(v) => upd({ maker_fee_pct: v })}
                            description="Per-leg maker fee for Post-Only Normal/Strong entries."
                        />
                        <NumberField
                            id="breakout-slippage-pct"
                            label="BREAKOUT SLIPPAGE (%)"
                            value={s.breakout_paper_slippage_pct}
                            min={0}
                            max={5}
                            step={0.01}
                            onChange={(v) => upd({ breakout_paper_slippage_pct: v })}
                            description="Synthetic taker slippage applied to PAPER breakout market fills."
                        />
                    </div>
                </section>

                {/* OPERATIONAL */}
                <section className="panel" data-testid="settings-operational">
                    <SectionHeader label="OPERATIONS" title="Mode & Symbols" />
                    <div className="p-5 space-y-5">
                        <div>
                            <div className="label-tag mb-2">TRADING MODE</div>
                            <div className="grid grid-cols-3 gap-0 border border-atlas-border">
                                {["PAPER", "DRY_RUN", "LIVE"].map((m) => {
                                    const active = s.trading_mode === m;
                                    const colorWhenActive =
                                        m === "LIVE"
                                            ? "bg-atlas-warning/10 text-atlas-warning"
                                            : m === "DRY_RUN"
                                                ? "bg-atlas-cyan/10 text-atlas-cyan"
                                                : "bg-atlas-positive/10 text-atlas-positive";
                                    return (
                                        <button
                                            key={m}
                                            type="button"
                                            data-testid={`trading-mode-${m.toLowerCase()}`}
                                            onClick={() => upd({ trading_mode: m })}
                                            className={`py-3 font-mono text-xs tracking-widest font-bold transition-colors border-r last:border-r-0 border-atlas-border ${
                                                active ? colorWhenActive : "text-atlas-textSecondary hover:text-white"
                                            }`}
                                        >
                                            {m === "DRY_RUN" ? "DRY-RUN" : m}
                                        </button>
                                    );
                                })}
                            </div>
                            <div className="mt-2 text-[10px] font-mono text-atlas-textTertiary">
                                {s.trading_mode === "LIVE" && (
                                    "LIVE mode places real exchange orders. Also requires LIVE_TRADING_ENABLED=true in backend/.env."
                                )}
                                {s.trading_mode === "DRY_RUN" && (
                                    "DRY-RUN exercises the full LIVE code path on real market data but stops before create_order. No real money moves. Recommended before flipping to LIVE."
                                )}
                                {s.trading_mode === "PAPER" && (
                                    "PAPER simulation against live market data. Default. Safe."
                                )}
                            </div>
                        </div>

                        <div>
                            <div className="label-tag mb-2">ENABLED SYMBOLS</div>
                            <div className="flex flex-wrap gap-2">
                                {[
                                    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
                                    "BTC/USDC", "ETH/USDC", "SOL/USDC",
                                ].map((sym) => {
                                    const active = (s.enabled_symbols || []).includes(sym);
                                    return (
                                        <button
                                            key={sym}
                                            type="button"
                                            data-testid={`symbol-toggle-${sym.replace("/", "-")}`}
                                            onClick={() => {
                                                const cur = s.enabled_symbols || [];
                                                upd({
                                                    enabled_symbols: active
                                                        ? cur.filter((x) => x !== sym)
                                                        : [...cur, sym],
                                                });
                                            }}
                                            className={`px-3 py-1.5 font-mono text-[11px] tracking-widest font-bold border transition-colors ${
                                                active
                                                    ? "bg-atlas-cyan text-atlas-bg border-atlas-cyan"
                                                    : "text-atlas-textSecondary border-atlas-border hover:text-white"
                                            }`}
                                        >
                                            {sym}
                                        </button>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                </section>

                {/* SYSTEMIC BREAKOUT (Layer 5c) */}
                <section className="panel" data-testid="settings-breakout">
                    <SectionHeader label="LAYER 5c · SYSTEMIC BREAKOUT" title="High-Velocity Override" />
                    <div className="p-5 space-y-5">
                        <NumberField
                            id="breakout-lot-usd"
                            label="BREAKOUT LOT (USD)"
                            value={s.breakout_lot_usd}
                            min={1}
                            max={10000}
                            step={1}
                            onChange={(v) => upd({ breakout_lot_usd: v })}
                            description="Position size when all 3 breakout legs fire. Defaults to $50."
                        />
                        <SliderField
                            id="breakout-min-conf"
                            label="MIN CONFIDENCE"
                            description="Macro must be BULLISH at this or higher to qualify."
                            value={s.breakout_min_confidence}
                            min={0}
                            max={1}
                            step={0.01}
                            unit=""
                            onChange={(v) => upd({ breakout_min_confidence: v })}
                        />
                        <SliderField
                            id="breakout-vol-pct"
                            label="VOLUME PERCENTILE FLOOR"
                            description="Current 1h volume rank vs last 14h must meet/exceed this."
                            value={s.breakout_volume_percentile}
                            min={0}
                            max={100}
                            step={1}
                            unit="%"
                            onChange={(v) => upd({ breakout_volume_percentile: v })}
                        />
                        <SliderField
                            id="breakout-max-spread"
                            label="MAX SPREAD"
                            description="Tight book required for explosive fills."
                            value={s.breakout_max_spread_pct}
                            min={0}
                            max={1}
                            step={0.01}
                            unit="%"
                            onChange={(v) => upd({ breakout_max_spread_pct: v })}
                        />
                        <div className="border-t border-atlas-border pt-5">
                            <div className="label-tag mb-3">BREAKOUT TRAIL OVERRIDES</div>
                            <div className="grid grid-cols-2 gap-4">
                                <SliderField
                                    id="breakout-trail-arm"
                                    label="TRAIL ARM"
                                    description="Wider arm so breakouts can run."
                                    value={s.breakout_trail_arm_pct}
                                    min={0.5}
                                    max={20}
                                    step={0.1}
                                    unit="%"
                                    onChange={(v) => upd({ breakout_trail_arm_pct: v })}
                                />
                                <SliderField
                                    id="breakout-trail-dist"
                                    label="TRAIL DISTANCE"
                                    description="Wider distance to ride volatile vertical moves."
                                    value={s.breakout_trail_distance_pct}
                                    min={0.1}
                                    max={20}
                                    step={0.1}
                                    unit="%"
                                    onChange={(v) => upd({ breakout_trail_distance_pct: v })}
                                />
                            </div>
                        </div>
                    </div>
                </section>

                {/* SYMMETRIC EXIT COOLDOWNS */}
                <section className="panel" data-testid="settings-cooldowns">
                    <SectionHeader label="EXIT COOLDOWNS" title="Per-Symbol Time Lock" />
                    <div className="p-5 grid grid-cols-2 gap-4">
                        <NumberField
                            id="sl-cooldown"
                            label="SL_HIT LOCK (SECONDS)"
                            value={s.sl_cooldown_seconds}
                            min={0}
                            max={86400}
                            step={60}
                            onChange={(v) => upd({ sl_cooldown_seconds: Math.round(v) })}
                            description="Block re-entry on this symbol after a stop-loss. Default 7200 = 2h."
                        />
                        <NumberField
                            id="trail-cooldown"
                            label="TRAIL_HIT LOCK (SECONDS)"
                            value={s.trail_cooldown_seconds}
                            min={0}
                            max={86400}
                            step={60}
                            onChange={(v) => upd({ trail_cooldown_seconds: Math.round(v) })}
                            description="Let momentum reset after a winning trail exit. Default 1800 = 30m."
                        />
                    </div>
                </section>
                <section className="panel lg:col-span-2" data-testid="settings-history">
                    <SectionHeader label="HOUSEKEEPING" title="Clear Old Logs & Trade History" />
                    <div className="p-5 flex flex-col md:flex-row gap-4 items-start">
                        <div className="flex-1 font-mono text-[11px] text-atlas-textSecondary leading-relaxed">
                            Wipe all trades + AI reasoning rows. Useful when you&apos;ve changed thresholds and want a clean slate for the next observation window. <span className="text-atlas-warning font-bold">Cannot be undone.</span>
                        </div>
                        <Button
                            data-testid="clear-history-btn"
                            onClick={() => clearHistory(false)}
                            disabled={!isOwner}
                            variant="outline"
                            className="rounded-none border-atlas-border text-atlas-textSecondary hover:text-white hover:border-atlas-warning font-mono text-[11px] tracking-widest disabled:opacity-40"
                        >
                            CLEAR TRADES + REASONING
                        </Button>
                        <Button
                            data-testid="clear-history-reset-btn"
                            onClick={() => clearHistory(true)}
                            disabled={!isOwner}
                            variant="outline"
                            className="rounded-none border-atlas-negative/40 text-atlas-negative hover:bg-atlas-negative hover:text-white font-mono text-[11px] tracking-widest disabled:opacity-40"
                        >
                            CLEAR ALL + RESET TO $300
                        </Button>
                    </div>
                </section>

                {/* API KEYS */}
                <section className="panel lg:col-span-2" data-testid="settings-api-keys">
                    <SectionHeader label="EXCHANGE CREDENTIALS" title="API Keys (Optional)" />
                    <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <div className="label-tag mb-2 flex items-center gap-2">
                                <Key className="w-3 h-3" />
                                KRAKEN
                            </div>
                            <div className="space-y-3">
                                <Field
                                    id="kraken-key"
                                    label="API Key"
                                    value={s.kraken_api_key}
                                    onChange={(v) => upd({ kraken_api_key: v })}
                                />
                                <Field
                                    id="kraken-secret"
                                    label="API Secret"
                                    value={s.kraken_api_secret}
                                    onChange={(v) => upd({ kraken_api_secret: v })}
                                    type="password"
                                />
                            </div>
                        </div>
                        <div>
                            <div className="label-tag mb-2 flex items-center gap-2">
                                <Key className="w-3 h-3" />
                                COINBASE
                            </div>
                            <div className="space-y-3">
                                <Field
                                    id="coinbase-key"
                                    label="API Key"
                                    value={s.coinbase_api_key}
                                    onChange={(v) => upd({ coinbase_api_key: v })}
                                />
                                <Field
                                    id="coinbase-secret"
                                    label="API Secret"
                                    value={s.coinbase_api_secret}
                                    onChange={(v) => upd({ coinbase_api_secret: v })}
                                    type="password"
                                />
                            </div>
                        </div>
                    </div>
                    <div className="px-5 pb-5 -mt-2 text-[10px] font-mono text-atlas-textTertiary">
                        Keys are only used in LIVE mode. PAPER mode reads public market data; no auth required. Public Kraken API
                        provides live tickers and orderbooks even without keys.
                    </div>
                </section>
            </div>

            <div className="sticky bottom-0 panel p-4 flex items-center justify-between border-atlas-cyan/40">
                <div className="text-[10px] font-mono text-atlas-textSecondary">
                    UPDATED {s.updated_at ? new Date(s.updated_at).toLocaleString() : "—"}
                </div>
                <Button
                    data-testid="save-settings-button"
                    onClick={save}
                    disabled={saving || !isOwner}
                    title={isOwner ? "" : "Owner login required"}
                    className="rounded-none bg-atlas-cyan hover:bg-cyan-400 text-atlas-bg font-mono text-xs tracking-widest font-bold disabled:opacity-50"
                >
                    {saving ? <span className="blink-cursor">SAVING</span> : <><Save className="w-3.5 h-3.5 mr-2" />{isOwner ? "SAVE SETTINGS" : "READ-ONLY"}</>}
                </Button>
            </div>
        </div>
        </TooltipProvider>
    );
}

function SectionHeader({ label, title }) {
    return (
        <div className="px-5 pt-4 pb-3 border-b border-atlas-border">
            <div className="label-tag">{label}</div>
            <h3 className="font-heading text-xl font-bold mt-1">{title}</h3>
        </div>
    );
}

function TitleLabel({ children, tooltip, htmlFor }) {
    if (!tooltip) {
        return <Label htmlFor={htmlFor} className="label-tag">{children}</Label>;
    }
    return (
        <Tooltip delayDuration={120}>
            <TooltipTrigger asChild>
                <Label
                    htmlFor={htmlFor}
                    data-testid={htmlFor ? `tooltip-label-${htmlFor}` : undefined}
                    className="label-tag inline-flex items-center gap-1 cursor-help"
                >
                    {children}
                    <Info className="w-3 h-3 text-atlas-textTertiary shrink-0" />
                </Label>
            </TooltipTrigger>
            <TooltipContent
                side="top"
                className="max-w-[260px] bg-atlas-panel border border-atlas-border text-white font-mono text-[11px] leading-relaxed rounded-none"
            >
                {tooltip}
            </TooltipContent>
        </Tooltip>
    );
}

function SliderField({ id, label, description, tooltip, value, min, max, step, unit, onChange }) {
    return (
        <div data-testid={`slider-${id}`}>
            <div className="flex items-center justify-between mb-2">
                <TitleLabel tooltip={tooltip || description} htmlFor={`input-${id}`}>{label}</TitleLabel>
                <div className="font-mono text-base font-bold tabular-nums">
                    {Number(value).toFixed(unit === "" ? 2 : 2)}
                    <span className="text-atlas-textSecondary ml-1">{unit}</span>
                </div>
            </div>
            <Slider
                data-testid={`slider-input-${id}`}
                value={[Number(value)]}
                min={min}
                max={max}
                step={step}
                onValueChange={(v) => onChange(v[0])}
                className="[&_[role=slider]]:rounded-none [&_[role=slider]]:bg-atlas-cyan [&_[role=slider]]:border-atlas-cyan"
            />
            {description && <div className="mt-2 text-[10px] font-mono text-atlas-textTertiary">{description}</div>}
        </div>
    );
}

function Field({ id, label, value, onChange, type = "text", tooltip }) {
    return (
        <div>
            <TitleLabel tooltip={tooltip} htmlFor={id}>{label}</TitleLabel>
            <Input
                id={id}
                data-testid={`input-${id}`}
                type={type}
                value={value || ""}
                onChange={(e) => onChange(e.target.value)}
                placeholder="••••••••"
                className="atlas-input rounded-none mt-1"
            />
        </div>
    );
}

function NumberField({ id, label, value, min, max, step, onChange, description, tooltip }) {
    return (
        <div data-testid={`number-${id}`}>
            <TitleLabel tooltip={tooltip || description} htmlFor={id}>{label}</TitleLabel>
            <Input
                id={id}
                data-testid={`input-${id}`}
                type="number"
                value={value ?? ""}
                min={min}
                max={max}
                step={step}
                onChange={(e) => {
                    const raw = e.target.value;
                    const n = raw === "" ? 0 : Number(raw);
                    if (!Number.isNaN(n)) onChange(n);
                }}
                className="atlas-input rounded-none font-mono mt-1"
            />
            {description && <div className="mt-2 text-[10px] font-mono text-atlas-textTertiary">{description}</div>}
        </div>
    );
}
