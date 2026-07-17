import React, { useEffect, useRef, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, TextInput, Modal, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { PageHeader } from "../../src/components/PageHeader";
import { Segmented } from "../../src/components/Segmented";
import { AskAnanta } from "../../src/components/AskAnanta";
import { FirstVisitTip } from "../../src/components/FirstVisitTip";
import { colors, spacing, type, radius } from "../../src/theme";

const SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"];
const CORE = ["hunter", "squeeze", "continuation"];
const SCOPES = [
  { id: "strategy", label: "Strategy", icon: "layers-outline", desc: "One alpha model (Hunter / Squeeze / Continuation)." },
  { id: "coin", label: "Specific Coin", icon: "logo-bitcoin", desc: "Override the exit for a single market." },
  { id: "global", label: "Global", icon: "globe-outline", desc: "Default exit for everything." },
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
  const { isOwner } = useAuth();
  const [sub, setSub] = useState("engine");
  const [settings, setSettings] = useState<any>(null);
  const [advOpen, setAdvOpen] = useState(false);
  const [trades, setTrades] = useState<any[]>([]);

  useEffect(() => {
    api.settings().then(setSettings).catch(() => {});
    api.trades(60).then((t: any) => setTrades(Array.isArray(t) ? t : (t.items || t.trades || []))).catch(() => {});
  }, []);

  const toggleKill = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const killed = !!settings?.manual_kill_switch;
    try { const s = await api.updateSettings({ manual_kill_switch: !killed }); setSettings(s); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const saveNum = async (k: string, v: string) => { const s = await api.updateSettings({ [k]: parseFloat(v) }); setSettings(s); };

  return (
    <View style={styles.fill}>
      <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
        <View style={styles.rowBetween}>
          <PageHeader title="Exit Engine" question="How should trades be closed?" />
          <Pressable testID="ee-advanced" onPress={() => setAdvOpen(true)} style={styles.advBtn}>
            <Ionicons name="settings-outline" size={13} color={colors.textMuted} /><Text style={styles.advTxt}> ADVANCED</Text>
          </Pressable>
        </View>
        <FirstVisitTip tipKey="exit-engine" text="Build an exit in 4 steps: scope, method, configure, then Test on history or Deploy to paper." />

        <View style={{ marginVertical: spacing.md }}>
          <Segmented testIDPrefix="ee-subtab"
            options={[{ key: "engine", label: "EXIT ENGINE" }, { key: "ai", label: "AI ANALYSIS" }]}
            value={sub} onChange={setSub} />
        </View>

        {sub === "engine" && <ExitFlow isOwner={isOwner} />}
        {sub === "ai" && <AiAnalysis isOwner={isOwner} trades={trades} />}
      </ScrollView>

      <Modal visible={advOpen} transparent animationType="slide" onRequestClose={() => setAdvOpen(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.rowBetween}>
              <Text style={type.h2}>Advanced Settings</Text>
              <Pressable testID="ee-adv-close" onPress={() => setAdvOpen(false)}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <View style={styles.rowBetween}>
              <SectionLabel>ENGINE & RISK</SectionLabel>
              <Pressable testID="ee-stop-ananta" onPress={toggleKill} style={[styles.stopBtn, settings?.manual_kill_switch && styles.stopBtnOn]}>
                <Ionicons name="power" size={13} color={colors.red} />
                <Text style={styles.stopTxt}>{settings?.manual_kill_switch ? "RELEASE" : "STOP ANANTA"}</Text>
              </Pressable>
            </View>
            {settings ? (
              <View style={{ marginTop: spacing.sm }}>
                <NumRow label="Stop-Loss %" k="stop_loss_pct" value={settings.stop_loss_pct} isOwner={isOwner} onSave={saveNum} />
                <NumRow label="Trail Arm %" k="trail_arm_pct" value={settings.trail_arm_pct} isOwner={isOwner} onSave={saveNum} />
                <NumRow label="Trail Distance %" k="trail_distance_pct" value={settings.trail_distance_pct} isOwner={isOwner} onSave={saveNum} />
                <NumRow label="Min Confidence" k="min_confidence" value={settings.min_confidence} isOwner={isOwner} onSave={saveNum} />
                <NumRow label="Daily Loss Cap %" k="max_daily_loss_pct" value={settings.max_daily_loss_pct} isOwner={isOwner} onSave={saveNum} />
              </View>
            ) : <ActivityIndicator color={colors.teal} />}
          </View>
        </View>
      </Modal>

      <AskAnanta tab="workspace" routeName="workspace" />
    </View>
  );
}

function ExitFlow({ isOwner }: { isOwner: boolean }) {
  const [step, setStep] = useState(1);
  const [scope, setScope] = useState<string | null>(null);
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
      <View style={styles.dots}>
        {["Scope", "Method", "Configure", "Test/Deploy"].map((l, i) => (
          <View key={l} style={[styles.dot, step === i + 1 && styles.dotActive]}>
            <Text style={[styles.dotTxt, step === i + 1 && { color: colors.teal }]}>{i + 1}. {l}</Text>
          </View>
        ))}
      </View>

      {step === 1 && (
        <Card testID="ee-step1">
          <SectionLabel>STEP 1 — WHAT TO MODIFY?</SectionLabel>
          {SCOPES.map((s) => (
            <Pressable key={s.id} testID={`ee-scope-${s.id}`} onPress={() => setScope(s.id)} style={[styles.optRow, scope === s.id && styles.optRowActive]}>
              <Ionicons name={s.icon as any} size={18} color={colors.teal} />
              <View style={{ flex: 1 }}>
                <Text style={type.body}>{s.label}</Text>
                <Text style={type.small}>{s.desc}</Text>
              </View>
              {scope === s.id && <Ionicons name="checkmark-circle" size={18} color={colors.teal} />}
            </Pressable>
          ))}
          {scope === "strategy" && <ChipRow items={CORE} value={strategy} onPick={setStrategy} prefix="ee-strat" />}
          {scope === "coin" && <ChipRow items={SYMBOLS} value={coin} onPick={setCoin} prefix="ee-coin" />}
          <Pressable testID="ee-next-1" disabled={!scope} onPress={() => setStep(2)} style={[styles.btn, styles.btnPrimary, !scope && { opacity: 0.4 }]}>
            <Text style={styles.btnPrimaryTxt}>CONTINUE</Text>
          </Pressable>
        </Card>
      )}

      {step === 2 && (
        <Card testID="ee-step2">
          <SectionLabel>STEP 2 — CHOOSE EXIT METHOD</SectionLabel>
          {METHODS.map((m) => (
            <Pressable key={m.id} testID={`ee-method-${m.id}`} onPress={() => pick(m)} style={styles.optRow}>
              <Ionicons name={m.icon as any} size={18} color={colors.teal} />
              <View style={{ flex: 1 }}>
                <Text style={type.body}>{m.name}</Text>
                <Text style={type.small}>{m.desc}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
            </Pressable>
          ))}
          <Pressable testID="ee-back-2" onPress={() => setStep(1)} style={[styles.btn, styles.btnGhost]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
        </Card>
      )}

      {step === 3 && method && (
        <Card testID="ee-step3">
          <SectionLabel>STEP 3 — CONFIGURE: {method.name.toUpperCase()}</SectionLabel>
          {FIELDS[method.id].length === 0 && <Text style={[type.small, { marginVertical: spacing.sm }]}>No parameters — exits the full position when momentum dies.</Text>}
          {FIELDS[method.id].map((f) => (
            <NumRow key={f.k} label={f.label} k={f.k} value={cfg[f.k]} isOwner onSave={(k: string, v: string) => setF(k, v)} />
          ))}
          {(method.engine === "native" || method.id === "chandelier") && (
            <Text style={styles.note}>Tested via the closest supported engine ({method.engine === "atr" ? "ATR trailing" : "Universal Exit Engine"}).</Text>
          )}
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable testID="ee-back-3" onPress={() => setStep(2)} style={[styles.btn, styles.btnGhost]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
            <Pressable testID="ee-next-3" onPress={() => setStep(4)} style={[styles.btn, styles.btnPrimary]}><Text style={styles.btnPrimaryTxt}>CONTINUE</Text></Pressable>
          </View>
        </Card>
      )}

      {step === 4 && method && (
        <Card testID="ee-step4">
          <SectionLabel>STEP 4 — TEST OR DEPLOY</SectionLabel>
          <Text style={[type.small, { marginBottom: spacing.sm }]}>Scope: <Text style={{ color: colors.text }}>{scope === "strategy" ? strategy : scope === "coin" ? coin : "Global"}</Text>  ·  Method: <Text style={{ color: colors.text }}>{method.name}</Text></Text>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <Pressable testID="ee-test" onPress={runTest} disabled={testing} style={[styles.btn, styles.btnGhost, { borderColor: colors.tealDim }]}>
              {testing ? <ActivityIndicator color={colors.teal} /> : <><Ionicons name="play" size={13} color={colors.teal} /><Text style={[styles.btnGhostTxt, { color: colors.teal }]}>  TEST</Text></>}
            </Pressable>
            <Pressable testID="ee-deploy" onPress={deploy} disabled={deploying} style={[styles.btn, styles.btnPrimary]}>
              {deploying ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="rocket" size={13} color={colors.bg} /><Text style={styles.btnPrimaryTxt}>  DEPLOY</Text></>}
            </Pressable>
          </View>
          <Pressable testID="ee-back-4" onPress={() => setStep(3)} style={[styles.btn, styles.btnGhost, { marginTop: spacing.sm }]}><Text style={styles.btnGhostTxt}>BACK</Text></Pressable>
          {result && <TestResult result={result} />}
        </Card>
      )}
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
        const ec = (per[s] || {}).exit_comparison || {};
        const rows = ec.rows || {};
        const keys = Object.keys(rows);
        if (!keys.length) return null;
        return (
          <View key={s} style={{ marginBottom: spacing.sm }}>
            <Text style={[type.small, { color: colors.textMuted }]}>{s}{ec.winner_key ? ` · best: ${rows[ec.winner_key]?.label}` : ""}</Text>
            {keys.map((k) => (
              <View key={k} style={styles.resRow}>
                <Text style={[type.small, { flex: 1, color: k === ec.winner_key ? colors.teal : colors.textMuted }]}>{rows[k].label}{k === ec.winner_key ? " ★" : ""}</Text>
                <Text style={styles.resVal}>PF {fmt(rows[k].profit_factor)}</Text>
                <Text style={styles.resVal}>{fmt(rows[k].total_return_pct)}%</Text>
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

const fmt = (x: any) => (typeof x === "number" ? x.toFixed(2) : x ?? "-");

function ChipRow({ items, value, onPick, prefix }: any) {
  return (
    <View style={styles.chipWrap}>
      {items.map((it: string) => (
        <Pressable key={it} testID={`${prefix}-${it.replace("/", "-")}`} onPress={() => onPick(it)} style={[styles.chip, value === it && styles.chipActive]}>
          <Text style={[styles.chipTxt, value === it && { color: colors.teal }]}>{it}</Text>
        </Pressable>
      ))}
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

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  advBtn: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: spacing.sm },
  advTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 10, letterSpacing: 0.5 },
  dots: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: spacing.md },
  dot: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingVertical: 3, paddingHorizontal: 8 },
  dotActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  dotTxt: { fontSize: 9, color: colors.textFaint, fontWeight: "700", letterSpacing: 0.4 },
  optRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  optRowActive: { backgroundColor: colors.tealGlow, borderRadius: radius.sm },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  chip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingVertical: 6, paddingHorizontal: spacing.sm },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 11 },
  note: { color: colors.gold, fontSize: 11, marginTop: spacing.sm, marginBottom: spacing.xs },
  numRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6 },
  input: { width: 96, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, color: colors.text, paddingHorizontal: spacing.sm, paddingVertical: 6, textAlign: "right", fontWeight: "700" },
  btn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", borderRadius: radius.md, paddingVertical: spacing.sm + 2, marginTop: spacing.sm },
  btnPrimary: { backgroundColor: colors.teal },
  btnPrimaryTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 12 },
  btnGhost: { borderWidth: 1, borderColor: colors.cardBorder },
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
