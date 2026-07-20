import React, { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, TextInput, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { AskAnanta } from "../../src/components/AskAnanta";
import { colors, spacing, type, radius } from "../../src/theme";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"];
const CORE = ["hunter", "squeeze", "continuation"];
const SCOPES = [
  { id: "strategy", name: "Modify for a Strategy", label: "Strategy", icon: "layers-outline", desc: "Apply this exit to one alpha model (Hunter / Squeeze / Continuation)." },
  { id: "coin", name: "Modify for a Specific Coin", label: "Specific Coin", icon: "logo-bitcoin", desc: "Override the exit for a single market, e.g. BTC/USD." },
  { id: "global", name: "Modify Global Default", label: "Global", icon: "globe-outline", desc: "The default exit for all strategies and coins." },
];
const METHODS = [
  { id: "fixed_pct", name: "Fixed % Target + Stop", desc: "Simple target and stop. Best for beginners.", icon: "flag-outline", engine: "fixed" },
  { id: "atr_trailing", name: "ATR Trailing Stop", desc: "Volatility-based trailing. Good for trends.", icon: "pulse-outline", engine: "atr" },
  { id: "structural_trail", name: "Structural Stop + Trail", desc: "Swing low/high. Best for Hunter / pullbacks.", icon: "git-branch-outline", engine: "native" },
  { id: "breakeven_trail", name: "Breakeven + Trail", desc: "Move to breakeven in profit. Protects winners.", icon: "shield-checkmark-outline", engine: "native" },
  { id: "partial_profit", name: "Partial Profit Taking", desc: "Take 40-50% at target, trail the rest.", icon: "pie-chart-outline", engine: "native" },
  { id: "momentum_exhaustion", name: "Momentum Exhaustion", desc: "Exit when momentum dies.", icon: "trending-down-outline", engine: "native" },
  { id: "time_based", name: "Time-Based Exit", desc: "Exit after N hours. Capital efficiency.", icon: "time-outline", engine: "native" },
  { id: "chandelier", name: "Chandelier Exit", desc: "Classic volatility trail for strong trends.", icon: "swap-vertical-outline", engine: "atr" },
];
const DEFAULTS: Record<string, any> = {
  fixed_pct: { target_pct: 3.0, stop_pct: 2.2 },
  atr_trailing: { atr_mult: 2.5, atr_period: 14, trail_arm: 1.6, trail_dist: 2.0 },
  structural_trail: { trail_atr_mult: 2.0, profit_arm_pct: 3.0 },
  breakeven_trail: { breakeven_r: 1.0, profit_arm_pct: 3.0 },
  partial_profit: { profit_arm_pct: 3.0 },
  momentum_exhaustion: {},
  time_based: { time_exit_hours: 48 },
  chandelier: { atr_period: 22, atr_mult: 3.0 },
};
const FIELDS: Record<string, { k: string; label: string }[]> = {
  fixed_pct: [{ k: "target_pct", label: "Take-Profit target (%)" }, { k: "stop_pct", label: "Stop-Loss (%)" }],
  atr_trailing: [{ k: "atr_mult", label: "ATR stop multiple (x)" }, { k: "atr_period", label: "ATR period" }, { k: "trail_arm", label: "Trail arm (%)" }, { k: "trail_dist", label: "Trail distance (xATR)" }],
  structural_trail: [{ k: "trail_atr_mult", label: "Trail ATR multiple (x)" }, { k: "profit_arm_pct", label: "Profit-protect arm (%)" }],
  breakeven_trail: [{ k: "breakeven_r", label: "Breakeven at (R)" }, { k: "profit_arm_pct", label: "Profit-floor arm (%)" }],
  partial_profit: [{ k: "profit_arm_pct", label: "Profit-protect arm (%)" }],
  momentum_exhaustion: [],
  time_based: [{ k: "time_exit_hours", label: "Time exit (hours)" }],
  chandelier: [{ k: "atr_period", label: "ATR period" }, { k: "atr_mult", label: "ATR multiple (x)" }],
};

export default function ExitEngine() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [view, setView] = useState<"home" | "edit" | "strategy" | "coin" | "global" | "ai" | "risk">("home");
  const [settings, setSettings] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);

  const loadSettings = () => api.settings().then(setSettings).catch(() => {});
  useEffect(() => {
    loadSettings();
    api.trades(60).then((t: any) => setTrades(Array.isArray(t) ? t : (t.items || t.trades || []))).catch(() => {});
  }, []);

  const killed = !!settings?.manual_kill_switch;
  const toggleKill = async () => {
    if (!isOwner) return Alert.alert("Owner login required", "Log in as the owner to stop/resume Ananta.");
    try { const s = await api.updateSettings({ manual_kill_switch: !killed }); setSettings(s); }
    catch (e: any) { Alert.alert("Failed", e?.message); }
  };

  const inWizard = view === "edit" || view === "strategy" || view === "coin" || view === "global";
  const wizardScope = view === "strategy" ? "strategy" : view === "coin" ? "coin" : "global";
  const backHome = () => { setView("home"); loadSettings(); };

  return (
    <View style={styles.fill}>
      <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
        <View style={styles.headerRow}>
          <Text style={styles.pageTitle}>Exit Engine</Text>
          <Pressable testID="ee-stop-ananta" onPress={toggleKill} style={[styles.stopPill, killed && styles.stopPillOn]}>
            <Ionicons name="power" size={13} color={killed ? colors.bg : "#fff"} />
            <Text style={[styles.stopPillTxt, killed && { color: colors.bg }]}>{killed ? "Resume" : "Stop Ananta"}</Text>
          </Pressable>
        </View>

        {view === "home" && (
          <ExitHome settings={settings}
            onEdit={() => setView("edit")} onScope={(s) => setView(s)}
            onExplain={() => setView("ai")} onTest={() => router.push("/research")} onRisk={() => setView("risk")} />
        )}

        {inWizard && (<>
          <BackHeader onBack={backHome} />
          <ExitFlow isOwner={isOwner} initialScope={wizardScope} initialStep={view === "edit" || view === "global" ? 2 : 1} onExit={backHome} />
        </>)}

        {view === "ai" && (<><BackHeader onBack={() => setView("home")} /><AiAnalysis isOwner={isOwner} trades={trades} /></>)}

        {view === "risk" && (<><BackHeader onBack={() => setView("home")} /><RiskMonitor isOwner={isOwner} settings={settings} setSettings={setSettings} /></>)}
      </ScrollView>

      <AskAnanta tab="workspace" routeName="workspace" />
    </View>
  );
}

function BackHeader({ onBack }: { onBack: () => void }) {
  return (
    <Pressable testID="ee-back-home" onPress={onBack} style={styles.backHeader} hitSlop={8}>
      <Ionicons name="chevron-back" size={18} color={colors.teal} />
      <Text style={styles.backTxt}>Exit Engine</Text>
    </Pressable>
  );
}

function ExitHome({ settings, onEdit, onScope, onExplain, onTest, onRisk }:
  { settings: any; onEdit: () => void; onScope: (s: "strategy" | "coin" | "global") => void; onExplain: () => void; onTest: () => void; onRisk: () => void }) {
  if (!settings) return <ActivityIndicator color={colors.teal} style={{ marginTop: spacing.xl }} />;
  const engineName = settings.dynamic_trail_enabled === false ? "Fixed-% Stop" : "ATR Trailing Stop";
  const trailMult = settings.profile_overrides?.hunter?.trail_atr_mult ?? 2.0;
  const params = [
    { label: "Trail Multiplier", value: `${trailMult}x` },
    { label: "Breakeven Arm", value: `${settings.trail_arm_pct ?? 0}%` },
    { label: "Hard Stop-Loss", value: `${settings.stop_loss_pct ?? 0}%` },
    { label: "Dynamic Trail", value: settings.dynamic_trail_enabled === false ? "Off" : "On" },
  ];

  return (
    <View>
      <Text style={styles.sectionTitle}>Current Active Exit</Text>
      <View style={styles.activeCard} testID="ee-active-exit">
        <Text style={styles.activeName} testID="ee-active-name">{engineName}</Text>
        <View style={styles.paramGrid}>
          {params.map((p) => (
            <View key={p.label} style={styles.paramCell} testID={`ee-param-${p.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
              <Text style={styles.paramLabel}>{p.label}</Text>
              <Text style={styles.paramValue}>{p.value}</Text>
            </View>
          ))}
        </View>
        <Pressable testID="ee-edit-current" onPress={onEdit} style={styles.editBtn}>
          <Ionicons name="create-outline" size={16} color={colors.bg} />
          <Text style={styles.editTxt}>Edit Current Exit</Text>
        </Pressable>
      </View>

      <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Modify Exit Rules</Text>
      {SCOPES.map((s) => (
        <Pressable key={s.id} testID={`ee-modify-${s.id}`} onPress={() => onScope(s.id as any)} style={styles.modifyCard}>
          <View style={styles.modifyIcon}><Ionicons name={s.icon as any} size={20} color={colors.teal} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.modifyTitle}>{s.name}</Text>
            <Text style={styles.modifyDesc} numberOfLines={2}>{s.desc}</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
        </Pressable>
      ))}

      <View style={styles.bottomRow}>
        <Pressable testID="ee-explain" onPress={onExplain} style={styles.bottomBtn}>
          <Ionicons name="sparkles" size={14} color={colors.bg} />
          <Text style={styles.bottomTxt}>Explain My Exits</Text>
        </Pressable>
        <Pressable testID="ee-test-performance" onPress={onTest} style={styles.bottomBtn}>
          <Ionicons name="stats-chart" size={14} color={colors.bg} />
          <Text style={styles.bottomTxt}>Test Strategy Performance</Text>
        </Pressable>
      </View>

      <Pressable testID="ee-risk-monitor" onPress={onRisk} style={styles.riskLink}>
        <Ionicons name="shield-checkmark-outline" size={14} color={colors.textMuted} />
        <Text style={styles.riskLinkTxt}>Risk Monitor & Safeguards</Text>
        <Ionicons name="chevron-forward" size={14} color={colors.textFaint} />
      </Pressable>
    </View>
  );
}

function ExitFlow({ isOwner, initialScope = null, initialStep = 1, onExit }: { isOwner: boolean; initialScope?: string | null; initialStep?: number; onExit?: () => void }) {
  const [step, setStep] = useState(initialStep);
  const [scope, setScope] = useState<string | null>(initialScope);
  const [strategy, setStrategy] = useState("hunter");
  const [coin, setCoin] = useState("BTC/USD");
  const [method, setMethod] = useState<any>(null);
  const [cfg, setCfg] = useState<any>({});
  const [testing, setTesting] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [result, setResult] = useState<any>(null);
  const poll = useRef<any>(null);
  useEffect(() => () => clearInterval(poll.current), []);

  const pick = (m: any) => { setMethod(m); setCfg({ ...DEFAULTS[m.id] }); setResult(null); setStep(3); };
  const setF = (k: string, v: string) => setCfg((c: any) => ({ ...c, [k]: parseFloat(v) }));

  const buildSpec = () => {
    const spec: any = { kind: "backtest", symbols: SYMBOLS, period: "3m", timeframe: "1h",
      strategies: scope === "strategy" ? [strategy] : CORE, exit_method: method.engine };
    if (method.engine === "fixed") { spec.target_profit = +(75 * (cfg.target_pct / 100)).toFixed(2); spec.target_loss = +(75 * (cfg.stop_pct / 100)).toFixed(2); }
    else if (method.engine === "atr") spec.atr_params = { multiplier: cfg.atr_mult, period: cfg.atr_period || 14, trail_activation_pct: cfg.trail_arm ?? 3.0, trail_distance: cfg.trail_dist ?? 2.0 };
    return spec;
  };

  const runTest = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setTesting(true); setResult(null);
    try {
      const { id } = await api.labCreateRun(buildSpec());
      poll.current = setInterval(async () => {
        try {
          const run = await api.labRun(id);
          if (run.status === "DONE" || run.status === "ERROR") {
            clearInterval(poll.current); setTesting(false);
            if (run.status === "ERROR") return Alert.alert("Backtest failed", run.error || "");
            setResult(run.result || {});
          }
        } catch { /* keep polling */ }
      }, 2500);
    } catch (e: any) { setTesting(false); Alert.alert("Could not start", e?.response?.data?.detail || e?.message); }
  };

  const deploy = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setDeploying(true);
    try {
      const patch: any = { exit_method_pref: method.id };
      if (method.id === "fixed_pct") patch.stop_loss_pct = cfg.stop_pct;
      if (method.id === "atr_trailing" || method.id === "chandelier") { patch.trail_arm_pct = cfg.trail_arm ?? 1.6; patch.trail_distance_pct = cfg.trail_dist ?? 0.9; }
      if (method.id === "breakeven_trail" || method.id === "structural_trail") patch.profit_protection_enabled = true;
      const prof: any = {};
      if (cfg.trail_atr_mult != null) prof.trail_atr_mult = cfg.trail_atr_mult;
      if (cfg.profit_arm_pct != null) prof.profit_arm_pct = cfg.profit_arm_pct;
      if (cfg.time_exit_hours != null) prof.time_exit_hours = cfg.time_exit_hours;
      if (scope === "strategy" && Object.keys(prof).length) patch.profile_overrides = { [strategy]: prof };
      if (scope === "coin") patch.asset_exit_overrides = { [coin]: { method: method.id, ...cfg } };
      await api.updateSettings(patch);
      const where = scope === "strategy" ? `strategy "${strategy}"` : scope === "coin" ? coin : "all markets";
      Alert.alert("Deployed", `${method.name} applied to ${where}. Live next cycle.`);
    } catch (e: any) { Alert.alert("Deploy failed", e?.response?.data?.detail || e?.message); }
    finally { setDeploying(false); }
  };

  return (
    <View>
      <StepBar step={step} />

      {step === 1 && (
        <View testID="ee-step1">
          <StepHead n={1} q="What do you want to modify?" />
          {SCOPES.map((s) => (
            <Pressable key={s.id} testID={`ee-scope-${s.id}`} onPress={() => setScope(s.id)}
              style={[styles.bigCard, scope === s.id && styles.bigCardActive]}>
              <View style={[styles.bigIcon, scope === s.id && styles.bigIconActive]}>
                <Ionicons name={s.icon as any} size={20} color={colors.teal} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.bigTitle}>{s.name}</Text>
                <Text style={[type.small, { marginTop: 3, lineHeight: 17 }]}>{s.desc}</Text>
              </View>
              <Ionicons name={scope === s.id ? "checkmark-circle" : "chevron-forward"} size={19}
                color={scope === s.id ? colors.teal : colors.textFaint} />
            </Pressable>
          ))}
          {scope === "strategy" && <ChipRow label="STRATEGY" items={CORE} value={strategy} onPick={setStrategy} prefix="ee-strat" />}
          {scope === "coin" && <ChipRow label="COIN" items={SYMBOLS} value={coin} onPick={setCoin} prefix="ee-coin" />}
          <Pressable testID="ee-next-1" disabled={!scope} onPress={() => setStep(2)} style={[styles.btn, styles.btnPrimary, styles.btnFull, !scope && { opacity: 0.4 }]}>
            <Text style={styles.btnPrimaryTxt}>CONTINUE</Text>
          </Pressable>
        </View>
      )}

      {step === 2 && (
        <View testID="ee-step2">
          <StepHead n={2} q="Choose an exit method" sub="Eight proven exit styles — pick the one that fits your approach." />
          {METHODS.map((m) => (
            <Pressable key={m.id} testID={`ee-method-${m.id}`} onPress={() => pick(m)}
              style={[styles.bigCard, method?.id === m.id && styles.bigCardActive]}>
              <View style={[styles.bigIcon, method?.id === m.id && styles.bigIconActive]}>
                <Ionicons name={m.icon as any} size={19} color={colors.teal} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <Text style={styles.bigTitle}>{m.name}</Text>
                  {m.engine === "native" && <Text style={styles.engineTag}>UNIVERSAL ENGINE</Text>}
                </View>
                <Text style={[type.small, { marginTop: 3, lineHeight: 17 }]}>{m.desc}</Text>
              </View>
              <Ionicons name="chevron-forward" size={17} color={colors.textFaint} />
            </Pressable>
          ))}
          <Pressable testID="ee-back-2" onPress={() => (initialStep === 2 ? onExit?.() : setStep(1))} style={[styles.btn, styles.btnGhost, styles.btnFull]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
        </View>
      )}

      {step === 3 && method && (
        <View testID="ee-step3">
          <StepHead n={3} q={`Configure: ${method.name}`} sub="Only the parameters relevant to this method are shown." />
          <Card>
            {FIELDS[method.id].length === 0 && <Text style={[type.small, { marginBottom: spacing.sm }]}>No parameters — exits the full position when momentum dies (overbought + volume climax + exhaustion candle).</Text>}
            {FIELDS[method.id].map((f) => (
              <NumRow key={f.k} label={f.label} k={f.k} value={cfg[f.k]} isOwner onSave={(k: string, v: string) => setF(k, v)} />
            ))}
            {(method.engine === "native" || method.id === "chandelier") && (
              <Text style={styles.note}>Tested via the closest supported engine ({method.engine === "atr" ? "ATR trailing" : "Universal Exit Engine"}).</Text>
            )}
          </Card>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable testID="ee-back-3" onPress={() => setStep(2)} style={[styles.btn, styles.btnGhost]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
            <Pressable testID="ee-next-3" onPress={() => setStep(4)} style={[styles.btn, styles.btnPrimary]}><Text style={styles.btnPrimaryTxt}>CONTINUE</Text></Pressable>
          </View>
        </View>
      )}

      {step === 4 && method && (
        <View testID="ee-step4">
          <StepHead n={4} q="Test or Deploy" sub="Test on historical data first, then deploy when you're confident." />
          <Card>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryK}>SCOPE</Text>
              <Text style={styles.summaryV}>{scope === "strategy" ? strategy : scope === "coin" ? coin : "Global"}</Text>
            </View>
            <View style={[styles.summaryRow, { borderTopWidth: 1, borderTopColor: colors.cardBorder }]}>
              <Text style={styles.summaryK}>METHOD</Text>
              <Text style={styles.summaryV}>{method.name}</Text>
            </View>
          </Card>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable testID="ee-test" onPress={runTest} disabled={testing} style={[styles.btn, styles.btnGhost, { borderColor: colors.tealDim }]}>
              {testing ? <ActivityIndicator color={colors.teal} /> : <><Ionicons name="play" size={13} color={colors.teal} /><Text style={[styles.btnGhostTxt, { color: colors.teal }]}>  TEST THIS EXIT</Text></>}
            </Pressable>
            <Pressable testID="ee-deploy" onPress={deploy} disabled={deploying} style={[styles.btn, styles.btnPrimary]}>
              {deploying ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="rocket" size={13} color={colors.bg} /><Text style={styles.btnPrimaryTxt}>  DEPLOY</Text></>}
            </Pressable>
          </View>
          <Pressable testID="ee-back-4" onPress={() => setStep(3)} style={[styles.btn, styles.btnGhost, styles.btnFull]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
          {result && <TestResult result={result} />}
        </View>
      )}
    </View>
  );
}

function StepBar({ step }: { step: number }) {
  const labels = ["Scope", "Method", "Configure", "Deploy"];
  return (
    <View style={styles.stepBar}>
      {labels.map((l, i) => {
        const n = i + 1; const active = step === n; const done = step > n;
        return (
          <View key={l} style={styles.stepCol}>
            <Text numberOfLines={1} style={[styles.stepTxt, (active || done) && styles.stepTxtOn]}>{n}. {l}</Text>
            <View style={[styles.stepUnderline, active && styles.stepUnderlineActive, done && styles.stepUnderlineDone]} />
          </View>
        );
      })}
    </View>
  );
}

function StepHead({ n, q, sub }: { n: number; q: string; sub?: string }) {
  return (
    <View style={{ marginBottom: spacing.md }}>
      <Text style={styles.stepKicker}>STEP {n}</Text>
      <Text style={styles.stepQ}>{q}</Text>
      {!!sub && <Text style={[type.small, { marginTop: 4, lineHeight: 17 }]}>{sub}</Text>}
    </View>
  );
}

function TestResult({ result }: { result: any }) {
  const per = result.per_symbol || {};
  const syms = Object.keys(per);
  if (!syms.length) return <Text style={[type.small, { marginTop: spacing.md }]}>No result rows.</Text>;
  return (
    <View style={{ marginTop: spacing.md }}>
      <SectionLabel>BACKTEST PERFORMANCE (3M · 1H)</SectionLabel>
      {syms.map((s) => {
        const d = per[s] || {};
        return (
          <View key={s} style={styles.resRow}>
            <Text style={[type.body, { flex: 1 }]}>{s}</Text>
            <Text style={[styles.resVal, { color: (d.total_return_pct ?? 0) >= 0 ? colors.teal : colors.red }]}>{fmt(d.total_return_pct)}%</Text>
            <Text style={styles.resVal}>{fmt(d.win_rate_pct)}% win</Text>
            <Text style={styles.resVal}>PF {fmt(d.profit_factor)}</Text>
          </View>
        );
      })}
      <SectionLabel style={{ marginTop: spacing.md }}>WHAT-IF — SAME ENTRIES, OTHER EXITS</SectionLabel>
      {syms.map((s) => {
        const byTf = (result.exit_comparison || {})[s] || {};
        const ec = byTf["1h"] || byTf[Object.keys(byTf)[0]] || {};
        const rows = ec.rows || {};
        const keys = Object.keys(rows).filter((k) => !rows[k].error);
        if (!keys.length) return null;
        return (
          <View key={s} style={{ marginBottom: spacing.sm }}>
            <Text style={[type.small, { color: colors.textMuted }]}>{s}{ec.winner_key ? ` · best: ${rows[ec.winner_key]?.label}` : ""}</Text>
            {keys.map((k) => (
              <View key={k} style={styles.resRow}>
                <Text style={[type.small, { flex: 1, color: k === ec.winner_key ? colors.teal : colors.textMuted }]} numberOfLines={1}>{rows[k].label}{k === ec.winner_key ? " ★" : ""}</Text>
                <Text style={styles.resVal}>PF {fmt(rows[k].profit_factor)}</Text>
                <Text style={[styles.resVal, { color: (rows[k].total_return_pct ?? 0) >= 0 ? colors.teal : colors.red }]}>{fmt(rows[k].total_return_pct)}%</Text>
              </View>
            ))}
          </View>
        );
      })}
    </View>
  );
}

function AiAnalysis({ isOwner, trades }: { isOwner: boolean; trades: any[] }) {
  const [loading, setLoading] = useState(false);
  const [ans, setAns] = useState("");
  const closed = (trades || []).filter((t) => t.side === "SELL" && t.pnl != null).slice(0, 12);
  const explain = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setLoading(true); setAns("");
    try {
      const r = await api.aiQuery("Analyse ONLY my exit performance from closed trades: which exit modules closed trades, win rate and average P&L per exit type, and how much of the favourable move (MFE) my exits captured. Give 3 concrete suggestions to improve exits.", `exit-explain-${Date.now()}`);
      setAns(r?.answer || r?.response || "No analysis returned.");
    } catch (e: any) { Alert.alert("AI failed", e?.response?.data?.detail || e?.message); }
    finally { setLoading(false); }
  };
  return (
    <View>
      <Card style={{ marginBottom: spacing.md }} testID="ee-explain">
        <SectionLabel>EXPLAIN EXIT PERFORMANCE</SectionLabel>
        <Text style={[type.small, { marginBottom: spacing.sm }]}>AI reads your closed trades and explains how your exits behaved.</Text>
        <Pressable testID="ee-explain-run" onPress={explain} disabled={loading} style={[styles.btn, styles.btnPrimary]}>
          {loading ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="sparkles" size={14} color={colors.bg} /><Text style={styles.btnPrimaryTxt}>  EXPLAIN MY EXITS</Text></>}
        </Pressable>
        {!!ans && <Text style={[type.small, { marginTop: spacing.sm, lineHeight: 20 }]}>{ans}</Text>}
      </Card>
      <Card testID="ee-closed">
        <SectionLabel>CLOSED TRADES BREAKDOWN</SectionLabel>
        {closed.length === 0 ? <Text style={[type.small, { marginTop: spacing.sm }]}>No closed trades yet.</Text> : closed.map((t, i) => (
          <View key={t.id || i} style={styles.tradeRow}>
            <Text style={[type.body, { width: 54 }]}>{(t.symbol || "").split("/")[0]}</Text>
            <Text style={[type.small, { color: colors.teal, width: 70 }]}>{t.exit_module ? `mod ${t.exit_module}` : (t.exit_reason || "-")}</Text>
            <Text style={[type.small, { flex: 1, textAlign: "right" }]} numberOfLines={1}>{t.exit_reason || "-"}</Text>
            <Text style={[styles.resVal, { color: t.pnl >= 0 ? colors.teal : colors.red }]}>{t.pnl >= 0 ? "+" : ""}${(t.pnl || 0).toFixed(2)}</Text>
          </View>
        ))}
      </Card>
    </View>
  );
}

function RiskMonitor({ isOwner, settings, setSettings }: { isOwner: boolean; settings: any; setSettings: (s: any) => void }) {
  const [risk, setRisk] = useState<any>(null);
  useEffect(() => {
    api.riskStatus().then(setRisk).catch(() => {});
    const t = setInterval(() => api.riskStatus().then(setRisk).catch(() => {}), 15000);
    return () => clearInterval(t);
  }, []);

  const save = async (k: string, v: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    try { const s = await api.updateSettings({ [k]: parseFloat(v) }); setSettings(s); } catch (e: any) { Alert.alert("Save failed", e?.message); }
  };
  const saveBool = async (k: string, v: boolean) => {
    if (!isOwner) return Alert.alert("Owner login required");
    try { const s = await api.updateSettings({ [k]: v }); setSettings(s); } catch (e: any) { Alert.alert("Save failed", e?.message); }
  };
  const toggleKill = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const killed = !!settings?.manual_kill_switch;
    try { const s = await api.updateSettings({ manual_kill_switch: !killed }); setSettings(s); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const [savedFlash, setSavedFlash] = useState(false);
  const saveAll = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const patch: any = {
      min_confidence: settings.min_confidence, htf_trend_enabled: settings.htf_trend_enabled,
      level_entry_enabled: settings.level_entry_enabled, adaptive_sizing_enabled: settings.adaptive_sizing_enabled,
      breakout_min_confidence: settings.breakout_min_confidence, max_concurrent_positions: settings.max_concurrent_positions,
      allowed_regimes: Array.isArray(settings.allowed_regimes) ? settings.allowed_regimes : [],
      max_daily_loss_pct: settings.max_daily_loss_pct, max_spread_pct: settings.max_spread_pct, normal_lot_usd: settings.normal_lot_usd,
    };
    try {
      const s = await api.updateSettings(patch);
      setSettings(s);
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    } catch (e: any) { Alert.alert("Save failed", e?.response?.data?.detail || e?.message || "Please try again."); }
  };

  if (!settings) return <ActivityIndicator color={colors.teal} style={{ marginTop: spacing.lg }} />;

  const engineName = settings.dynamic_trail_enabled === false ? "Fixed-% Stop" : "ATR Trailing Stop";
  const trailMult = settings.profile_overrides?.hunter?.trail_atr_mult ?? 2.0;
  const safe = risk?.status?.overall_safe !== false;
  const killed = !!settings.manual_kill_switch;

  return (
    <View>
      {/* ENTRY SETUP — rules that decide WHEN Ananta opens a new position */}
      <Card testID="rm-entry-setup" style={{ marginBottom: spacing.md }}>
        <SectionLabel>ENTRY SETUP</SectionLabel>
        <Text style={[type.small, { marginTop: 4, marginBottom: spacing.sm, lineHeight: 17 }]}>
          Rules that decide when Ananta opens a new position.
        </Text>
        <NumRow label="Min Confidence" k="min_confidence" value={settings.min_confidence} isOwner={isOwner} onSave={save} />
        <ToggleRow label="HTF Trend Filter" desc="Require price > 4h EMA50 > EMA200" k="htf_trend_enabled" value={settings.htf_trend_enabled} isOwner={isOwner} onSave={saveBool} />
        <ToggleRow label="Support / Level Entry" desc="Only enter at clean historical support zones" k="level_entry_enabled" value={settings.level_entry_enabled} isOwner={isOwner} onSave={saveBool} />
        <ToggleRow label="Adaptive Sizing" desc="Size the lot by setup strength" k="adaptive_sizing_enabled" value={settings.adaptive_sizing_enabled} isOwner={isOwner} onSave={saveBool} />
        <NumRow label="Breakout Min Confidence" k="breakout_min_confidence" value={settings.breakout_min_confidence} isOwner={isOwner} onSave={save} />
        <NumRow label="Max Open Positions" k="max_concurrent_positions" value={settings.max_concurrent_positions} isOwner={isOwner} onSave={save} />
        <RegimeChips value={settings.allowed_regimes} isOwner={isOwner} onSave={saveBool} />
      </Card>

      {/* ACTIVE EXIT ENGINE — read-only summary (configured in the Exit Engine flow) */}
      <Card testID="rm-active-exit" style={{ marginBottom: spacing.md }}>
        <SectionLabel>ACTIVE EXIT ENGINE</SectionLabel>
        <View style={styles.rmStatusRow}>
          <Text style={styles.rmStatusLabel}>STATUS</Text>
          <Text style={[styles.rmStatusVal, { color: colors.teal }]}>{engineName} ●</Text>
        </View>
        <SummaryRow label="Trail Multiplier" value={`${trailMult}x`} />
        <SummaryRow label="Breakeven Arm" value={`${settings.trail_arm_pct}%`} />
        <SummaryRow label="Hard Stop-Loss" value={`${settings.stop_loss_pct}%`} />
      </Card>

      {/* SAFEGUARDS — account-level protection */}
      <Card testID="rm-safeguards">
        <View style={styles.rowBetween}>
          <SectionLabel>RISK MONITOR · SAFEGUARDS</SectionLabel>
          <Pressable testID="rm-stop-ananta" onPress={toggleKill} style={[styles.stopBtn, killed && styles.stopBtnOn]}>
            <Ionicons name="power" size={13} color={colors.red} />
            <Text style={styles.stopTxt}>{killed ? "RELEASE" : "STOP ANANTA"}</Text>
          </Pressable>
        </View>
        <View style={[styles.rmStatusRow, { marginBottom: spacing.sm }]}>
          <Text style={styles.rmStatusLabel}>RISK STATUS</Text>
          <Text style={[styles.rmStatusVal, { color: safe ? colors.teal : colors.red }]}>{safe ? "Protected ●" : "Alert ●"}</Text>
        </View>
        <NumRow label="Daily Loss Cap %" k="max_daily_loss_pct" value={settings.max_daily_loss_pct} isOwner={isOwner} onSave={save} />
        <NumRow label="Max Spread %" k="max_spread_pct" value={settings.max_spread_pct} isOwner={isOwner} onSave={save} />
        <NumRow label="Normal Lot (USD)" k="normal_lot_usd" value={settings.normal_lot_usd} isOwner={isOwner} onSave={save} />
      </Card>

      {/* Save — changes also auto-save; this gives explicit confirmation */}
      <Pressable testID="rm-save-settings" onPress={saveAll} disabled={!isOwner}
        style={[styles.saveBtn, savedFlash && styles.saveBtnDone, !isOwner && { opacity: 0.5 }]}>
        <Ionicons name={savedFlash ? "checkmark-circle" : "save-outline"} size={16} color={savedFlash ? colors.green : colors.teal} />
        <Text style={[styles.saveTxt, savedFlash && { color: colors.green }]}>{savedFlash ? "Saved" : "Save Settings"}</Text>
      </Pressable>
      <Text style={styles.saveHint}>Changes also save automatically</Text>
    </View>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryRow}>
      <Text style={[type.body, { color: colors.textMuted }]}>{label}</Text>
      <Text style={[type.body, { fontWeight: "800" }]}>{value}</Text>
    </View>
  );
}

const fmt = (x: any) => (typeof x === "number" ? x.toFixed(2) : x ?? "-");

function ChipRow({ label, items, value, onPick, prefix }: any) {
  return (
    <View style={{ marginTop: spacing.sm }}>
      {!!label && <Text style={[type.label, { marginBottom: 6 }]}>{label}</Text>}
      <View style={styles.chipWrap}>
        {items.map((it: string) => (
          <Pressable key={it} testID={`${prefix}-${it.replace("/", "-")}`} onPress={() => onPick(it)} style={[styles.chip, value === it && styles.chipActive]}>
            <Text style={[styles.chipTxt, value === it && { color: colors.teal }]}>{it}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function NumRow({ label, k, value, isOwner, onSave }: any) {
  const [v, setV] = useState(String(value ?? ""));
  useEffect(() => setV(String(value ?? "")), [value]);
  return (
    <View style={styles.numRow}>
      <Text style={[type.body, { flex: 1 }]}>{label}</Text>
      <TextInput testID={`ee-set-${k}`} value={v} onChangeText={setV} editable={isOwner} keyboardType="decimal-pad"
        onEndEditing={() => onSave(k, v)} style={styles.input} placeholderTextColor={colors.textFaint} />
    </View>
  );
}

const REGIMES = ["COMPRESSION", "REVERSAL", "TREND_UP", "TREND_DOWN", "RANGE", "NEUTRAL"];

function RegimeChips({ value, isOwner, onSave }: any) {
  const active: string[] = Array.isArray(value) ? value : [];
  const toggle = (r: string) => onSave("allowed_regimes", active.includes(r) ? active.filter((x) => x !== r) : [...active, r]);
  return (
    <View style={{ paddingVertical: 8 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={[type.body]}>Allowed Regimes</Text>
        <Text style={[type.small]} testID="rm-regimes-count">{active.length ? `${active.length} selected` : "All regimes"}</Text>
      </View>
      <Text style={[type.small, { marginTop: 2, marginBottom: 6, lineHeight: 16 }]}>Only open entries in these regimes. None = trade all.</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
        {REGIMES.map((r) => {
          const on = active.includes(r);
          return (
            <Pressable key={r} testID={`rm-regime-${r}`} disabled={!isOwner} onPress={() => toggle(r)}
              style={[styles.regChip, on && styles.regChipOn, !isOwner && { opacity: 0.5 }]}>
              <Text style={[styles.regChipTxt, on && { color: colors.teal }]}>{r}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function ToggleRow({ label, desc, k, value, isOwner, onSave }: any) {
  const on = !!value;
  return (
    <View style={styles.toggleRow}>
      <View style={{ flex: 1, paddingRight: spacing.sm }}>
        <Text style={[type.body]}>{label}</Text>
        {!!desc && <Text style={[type.small, { marginTop: 2, lineHeight: 16 }]}>{desc}</Text>}
      </View>
      <Pressable testID={`rm-toggle-${k}`} disabled={!isOwner} onPress={() => onSave(k, !on)}
        style={[styles.switch, on && styles.switchOn, !isOwner && { opacity: 0.5 }]}>
        <View style={[styles.knob, on && styles.knobOn]} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.lg },
  pageTitle: { color: colors.text, fontSize: 26, fontWeight: "800" },
  stopPill: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.red, borderRadius: radius.pill, paddingHorizontal: 14, paddingVertical: 9 },
  stopPillOn: { backgroundColor: colors.teal },
  stopPillTxt: { color: "#fff", fontWeight: "800", fontSize: 12, letterSpacing: 0.3 },
  sectionTitle: { color: colors.text, fontSize: 17, fontWeight: "800", marginBottom: spacing.sm },
  activeCard: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.teal + "40", borderRadius: radius.lg, padding: spacing.md },
  activeName: { color: colors.teal, fontSize: 20, fontWeight: "800", marginBottom: spacing.md },
  paramGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  paramCell: { width: "47.8%", flexGrow: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md },
  paramLabel: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.5, textTransform: "uppercase" },
  paramValue: { color: colors.text, fontSize: 20, fontWeight: "800", marginTop: 4 },
  editBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 13, marginTop: spacing.md },
  editTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
  modifyCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, backgroundColor: colors.card, marginBottom: spacing.sm },
  modifyIcon: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.tealGlow, alignItems: "center", justifyContent: "center" },
  modifyTitle: { color: colors.text, fontWeight: "700", fontSize: 15 },
  modifyDesc: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 3 },
  bottomRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg },
  bottomBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 13, paddingHorizontal: spacing.sm },
  bottomTxt: { color: colors.bg, fontWeight: "800", fontSize: 12, textAlign: "center" },
  riskLink: { flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "center", marginTop: spacing.md, paddingVertical: 12 },
  riskLinkTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 13 },
  backHeader: { flexDirection: "row", alignItems: "center", gap: 2, marginBottom: spacing.md, alignSelf: "flex-start" },
  backTxt: { color: colors.teal, fontWeight: "800", fontSize: 14 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  advBtn: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: spacing.sm },
  advTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 10, letterSpacing: 0.5 },
  rmStatusRow: { paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder, marginTop: 4 },
  rmStatusLabel: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.8 },
  rmStatusVal: { fontSize: 18, fontWeight: "800", marginTop: 4 },
  stepBar: { flexDirection: "row", gap: 6, marginBottom: spacing.lg },
  stepCol: { flex: 1, alignItems: "center" },
  stepTxt: { fontSize: 10, color: colors.textFaint, fontWeight: "700", letterSpacing: 0.2 },
  stepTxtOn: { color: colors.teal, fontWeight: "800" },
  stepUnderline: { height: 2, alignSelf: "stretch", backgroundColor: colors.cardBorder, borderRadius: 2, marginTop: 7 },
  stepUnderlineActive: { backgroundColor: colors.teal },
  stepUnderlineDone: { backgroundColor: colors.tealDim },
  stepKicker: { color: colors.teal, fontWeight: "800", fontSize: 11, letterSpacing: 1 },
  stepQ: { color: colors.text, fontWeight: "700", fontSize: 18, marginTop: 4 },
  bigCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, backgroundColor: colors.card, marginBottom: spacing.sm },
  bigCardActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  bigIcon: { width: 44, height: 44, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center", backgroundColor: colors.tealGlow },
  bigIconActive: { borderColor: colors.teal },
  bigTitle: { color: colors.text, fontWeight: "700", fontSize: 15 },
  engineTag: { color: colors.gold, fontSize: 8, fontWeight: "800", letterSpacing: 0.6, borderWidth: 1, borderColor: colors.goldDim || colors.gold, borderRadius: 999, paddingHorizontal: 6, paddingVertical: 2 },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.sm },
  summaryK: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.8 },
  summaryV: { color: colors.text, fontSize: 13, fontWeight: "700" },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingVertical: 6, paddingHorizontal: spacing.sm },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 11 },
  note: { color: colors.gold, fontSize: 11, marginTop: spacing.sm, marginBottom: spacing.xs },
  numRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6 },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8 },
  switch: { width: 46, height: 28, borderRadius: 999, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, padding: 3, justifyContent: "center" },
  switchOn: { backgroundColor: colors.tealGlow, borderColor: colors.teal },
  knob: { width: 20, height: 20, borderRadius: 999, backgroundColor: colors.textFaint, alignSelf: "flex-start" },
  knobOn: { backgroundColor: colors.teal, alignSelf: "flex-end" },
  regChip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingVertical: 5, paddingHorizontal: 10 },
  regChipOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  regChipTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 10, letterSpacing: 0.3 },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: spacing.md, paddingVertical: 14, borderRadius: radius.md, borderWidth: 1, borderColor: colors.teal, backgroundColor: colors.tealGlow },
  saveBtnDone: { borderColor: colors.green, backgroundColor: colors.greenGlow },
  saveTxt: { color: colors.teal, fontWeight: "800", fontSize: 14, letterSpacing: 0.3 },
  saveHint: { color: colors.textFaint, fontSize: 11, textAlign: "center", marginTop: spacing.sm },
  input: { width: 96, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, color: colors.text, paddingHorizontal: spacing.sm, paddingVertical: 6, textAlign: "right", fontWeight: "700" },
  btn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", borderRadius: radius.md, paddingVertical: spacing.sm + 2, marginTop: spacing.sm },
  btnPrimary: { backgroundColor: colors.teal },
  btnPrimaryTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 12 },
  btnGhost: { borderWidth: 1, borderColor: colors.cardBorder },
  btnFull: { alignSelf: "stretch" },
  btnGhostTxt: { color: colors.textMuted, fontWeight: "700", letterSpacing: 0.6, fontSize: 12 },
  resRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 5, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  resVal: { color: colors.textMuted, fontWeight: "700", fontSize: 11, fontVariant: ["tabular-nums"] },
  tradeRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  stopBtn: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.redDim, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: spacing.sm },
  stopBtnOn: { backgroundColor: colors.redGlow, borderColor: colors.red },
  stopTxt: { color: colors.red, fontWeight: "800", letterSpacing: 0.6, fontSize: 11 },
  modalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, paddingBottom: 40, borderWidth: 1, borderColor: colors.cardBorder },
});
