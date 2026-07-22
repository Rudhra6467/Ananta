import React, { useEffect, useState } from "react";
import {
  View, Text, ScrollView, StyleSheet, Pressable, TextInput, ActivityIndicator, Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { colors, spacing, type, radius } from "../../src/theme";

const FMT_ICON: Record<string, any> = {
  pine_script: "logo-tradingview", freqtrade: "git-branch", jesse: "cube", json: "code-slash", auto: "sparkles",
};
const SEV_COLOR: Record<string, string> = { error: colors.red, warning: colors.amber, info: colors.teal };
const SEV_ICON: Record<string, any> = { error: "close-circle", warning: "warning", info: "information-circle" };

const SAMPLE = `//@version=5
strategy("Golden Cross", overlay=true)
fast = ta.sma(close, input.int(50))
slow = ta.sma(close, input.int(200))
if ta.crossover(fast, slow)
    strategy.entry("Long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("Long")`;

export default function ImportStrategy() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [step, setStep] = useState<"input" | "review">("input");
  const [formats, setFormats] = useState<any[]>([]);
  const [fmt, setFmt] = useState("auto");
  const [name, setName] = useState("");
  const [raw, setRaw] = useState("");
  const [detected, setDetected] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<any>(null);

  useEffect(() => { api.importFormats().then((d: any) => setFormats(d.formats || [])).catch(() => {}); }, []);
  useEffect(() => {
    if (!raw.trim()) { setDetected(null); return; }
    const t = setTimeout(() => { api.importDetect(raw).then(setDetected).catch(() => {}); }, 400);
    return () => clearTimeout(t);
  }, [raw]);

  const analyze = async () => {
    if (!isOwner) return Alert.alert("Owner login required", "Log in as the owner to import strategies.");
    if (!raw.trim()) return Alert.alert("Paste your strategy code first");
    setBusy(true);
    try {
      const d = await api.importAnalyze({ raw_content: raw, source_format: fmt, name: name || undefined });
      setDraft(d); setStep("review");
    } catch (e: any) {
      const msg = e?.message || "Could not analyze the strategy";
      const credits = /credit|budget|quota|402|insufficient/i.test(msg);
      Alert.alert("Analysis failed", credits
        ? "AI credits are exhausted. You can still 'Save without AI' and edit the strategy manually."
        : msg);
    } finally { setBusy(false); }
  };

  const saveDirect = async () => {
    if (!isOwner) return Alert.alert("Owner login required", "Log in as the owner to import strategies.");
    if (!raw.trim()) return Alert.alert("Paste your strategy code first");
    setBusy(true);
    try {
      const d = await api.importDirect({ raw_content: raw, source_format: fmt, name: name || undefined });
      setDraft(d); setStep("review");
    } catch (e: any) {
      Alert.alert("Could not save", e?.message || "Direct import failed. For JSON, check the syntax.");
    } finally { setBusy(false); }
  };

  const setField = (k: string, v: any) => setDraft((d: any) => ({ ...d, [k]: v }));

  const approve = async () => {
    setBusy(true);
    try {
      await api.importUpdate(draft.id, {
        name: draft.name, description: draft.description, risk: draft.risk,
        ai_summary: draft.ai_summary, recommended_market: draft.recommended_market,
      });
      const r = await api.importApprove(draft.id);
      Alert.alert("Imported", `${draft.name} added to your Library`);
      router.replace(`/library/${r.library_id}`);
    } catch (e: any) {
      Alert.alert("Could not save", e?.message || "Approval failed");
    } finally { setBusy(false); }
  };

  const v = draft?.validation || { issues: [], status: "review", error_count: 0 };
  const blocked = (v.error_count || 0) > 0;

  return (
    <ScrollView style={styles.fill} testID="import-screen" keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
      <Pressable testID="import-back" onPress={() => (step === "review" ? setStep("input") : router.back())} style={styles.back}>
        <Ionicons name="chevron-back" size={18} color={colors.teal} />
        <Text style={{ color: colors.teal, fontWeight: "700", fontSize: 12 }}>{step === "review" ? "Edit source" : "Library"}</Text>
      </Pressable>

      <Text style={type.h2}>Import Strategy</Text>
      <Text style={[type.small, { marginTop: 2, marginBottom: spacing.md }]}>
        {step === "input" ? "Pine Script · Freqtrade · Jesse · JSON" : "Review the AI conversion, then save"}
      </Text>

      {step === "input" ? (
        <>
          <SectionLabel>SOURCE FRAMEWORK</SectionLabel>
          <View style={styles.chipWrap}>
            {formats.map((f: any) => {
              const active = fmt === f.key;
              const isDet = detected && f.key === detected.best && fmt === "auto";
              return (
                <Pressable key={f.key} testID={`import-fmt-${f.key}`} onPress={() => setFmt(f.key)} style={[styles.chip, active && styles.chipActive]}>
                  <Ionicons name={FMT_ICON[f.key] || "code-slash"} size={12} color={active ? colors.teal : colors.textMuted} />
                  <Text style={[styles.chipTxt, active && { color: colors.teal }]}>{f.label}</Text>
                  {isDet && <Text style={{ color: colors.teal, fontSize: 8, fontWeight: "800" }}>· detected</Text>}
                </Pressable>
              );
            })}
          </View>

          <SectionLabel style={{ marginTop: spacing.md }}>NAME (OPTIONAL)</SectionLabel>
          <TextInput testID="import-name" value={name} onChangeText={setName} placeholder="e.g. My Golden Cross"
            placeholderTextColor={colors.textFaint} style={styles.input} />

          <View style={[styles.rowBetween, { marginTop: spacing.md }]}>
            <SectionLabel>STRATEGY CODE</SectionLabel>
            <Pressable testID="import-sample" onPress={() => setRaw(SAMPLE)}><Text style={{ color: colors.teal, fontSize: 11, fontWeight: "700" }}>Load sample</Text></Pressable>
          </View>
          <TextInput testID="import-code" value={raw} onChangeText={setRaw} multiline
            placeholder="Paste your Pine Script / Freqtrade / Jesse / JSON here…"
            placeholderTextColor={colors.textFaint} style={styles.codeInput} textAlignVertical="top" autoCapitalize="none" autoCorrect={false} />
          {detected && !!raw.trim() && (
            <Text style={[type.small, { marginTop: 4 }]}>Auto-detected: {detected.best} ({Math.round((detected.scores?.[detected.best] || 0) * 100)}%)</Text>
          )}

          <Pressable testID="import-analyze-btn" onPress={analyze} disabled={busy || !raw.trim()}
            style={[styles.primaryBtn, (busy || !raw.trim()) && { opacity: 0.5 }]}>
            {busy ? <ActivityIndicator color={colors.bg} /> : <Ionicons name="sparkles" size={16} color={colors.bg} />}
            <Text style={styles.primaryBtnTxt}>{busy ? "Working…" : "Analyze with AI"}</Text>
          </Pressable>
          <Pressable testID="import-direct-btn" onPress={saveDirect} disabled={busy || !raw.trim()}
            style={[styles.secondaryBtn, (busy || !raw.trim()) && { opacity: 0.5 }]}>
            <Ionicons name="save-outline" size={15} color={colors.teal} />
            <Text style={styles.secondaryBtnTxt}>Save without AI</Text>
          </Pressable>
          <Text style={[type.small, { textAlign: "center", marginTop: 6, color: colors.textFaint }]}>
            No credits needed. Best for JSON — you can edit details on the next screen.
          </Text>
        </>
      ) : (
        <View testID="import-review">
          <View style={styles.statRow}>
            <Card style={styles.statCard}><Text style={[type.h2, { color: confColor(draft.conversion_confidence) }]}>{draft.conversion_confidence}%</Text><Text style={type.label}>CONVERSION</Text></Card>
            <Card style={styles.statCard}><Text style={[type.h2, { color: colors.text }]}>{draft.ai_health_score}</Text><Text style={type.label}>HEALTH · {draft.ai_grade}</Text></Card>
            <Card style={styles.statCard}><Text style={[type.h2, { color: colors.text }]}>{(draft.direction || "long").toUpperCase()}</Text><Text style={type.label}>DIRECTION</Text></Card>
          </View>

          <Card testID="import-validation" style={{ marginTop: spacing.sm }}>
            <View style={styles.rowBetween}>
              <SectionLabel>VALIDATION REPORT</SectionLabel>
              <Text style={{ color: v.status === "ready" ? colors.teal : v.status === "blocked" ? colors.red : colors.amber, fontSize: 11, fontWeight: "800" }}>{v.status.toUpperCase()}</Text>
            </View>
            {(!v.issues || v.issues.length === 0) ? (
              <Text style={[type.body, { color: colors.teal, marginTop: 6, fontSize: 13 }]}>Clean conversion — no issues.</Text>
            ) : v.issues.map((it: any, i: number) => (
              <View key={i} style={styles.issueRow}>
                <Ionicons name={SEV_ICON[it.severity]} size={14} color={SEV_COLOR[it.severity]} style={{ marginTop: 2 }} />
                <Text style={[type.small, { flex: 1, color: colors.text, fontSize: 12 }]}>{it.message}</Text>
              </View>
            ))}
          </Card>

          {!!draft.conversion_report && (
            <Card style={{ marginTop: spacing.sm }}>
              <SectionLabel>AI CONVERSION REPORT</SectionLabel>
              <Text style={[type.body, { marginTop: 6, fontSize: 13, lineHeight: 19 }]}>{draft.conversion_report}</Text>
            </Card>
          )}

          <ExecutableRules draft={draft} />

          <Card style={{ marginTop: spacing.sm }}>
            <SectionLabel>REVIEW &amp; EDIT</SectionLabel>
            <Text style={[type.label, { marginTop: spacing.sm }]}>NAME</Text>
            <TextInput testID="edit-name" value={draft.name} onChangeText={(t) => setField("name", t)} style={styles.input} placeholderTextColor={colors.textFaint} />
            <Text style={[type.label, { marginTop: spacing.sm }]}>RISK</Text>
            <TextInput value={draft.risk} onChangeText={(t) => setField("risk", t)} style={styles.input} placeholderTextColor={colors.textFaint} />
            <Text style={[type.label, { marginTop: spacing.sm }]}>DESCRIPTION</Text>
            <TextInput value={draft.description} onChangeText={(t) => setField("description", t)} multiline style={[styles.input, { minHeight: 56 }]} textAlignVertical="top" placeholderTextColor={colors.textFaint} />
          </Card>

          <RuleList title="ENTRY RULES" items={draft.entry_rules} tone={colors.teal} />
          <RuleList title="EXIT RULES" items={draft.exit_rules} tone={colors.teal} />
          {draft.strengths?.length > 0 && <RuleList title="STRENGTHS" items={draft.strengths} tone={colors.teal} />}
          {draft.weaknesses?.length > 0 && <RuleList title="WEAKNESSES" items={draft.weaknesses} tone={colors.red} />}

          <Pressable testID="import-approve-btn" onPress={approve} disabled={busy || blocked}
            style={[styles.primaryBtn, { backgroundColor: colors.teal }, (busy || blocked) && { opacity: 0.4 }]}>
            {busy ? <ActivityIndicator color={colors.bg} /> : <Ionicons name="checkmark-circle" size={16} color={colors.bg} />}
            <Text style={styles.primaryBtnTxt}>{blocked ? "Resolve errors to save" : "Save to Library"}</Text>
          </Pressable>
        </View>
      )}
    </ScrollView>
  );
}

function ExecutableRules({ draft }: { draft: any }) {
  const [running, setRunning] = useState(false);
  const [bt, setBt] = useState<any>(draft.preview_backtest || null);
  const spec = draft.declarative_spec || {};
  const declarable = !!draft.declarable;
  const fmtCond = (c: any) => `${c.lhs} ${String(c.op).replace("_", " ")}${c.rhs !== undefined ? " " + c.rhs : ""}`;
  const runPreview = async () => {
    setRunning(true);
    try {
      const r = await api.importBacktestPreview(draft.id, "BTC/USD", 30);
      setBt({ ...r.historical_results, bars: r.bars });
    } catch (e: any) { Alert.alert("Preview failed", e?.message || "Error"); }
    finally { setRunning(false); }
  };
  return (
    <Card testID="import-executable" style={{ marginTop: spacing.sm }}>
      <SectionLabel>EXECUTABLE RULES</SectionLabel>
      <View testID="import-declarable-badge" style={[styles.badge, { borderColor: declarable ? colors.teal : colors.amber, backgroundColor: declarable ? colors.tealGlow : "rgba(242,169,59,0.1)" }]}>
        <Ionicons name={declarable ? "flash" : "warning"} size={12} color={declarable ? colors.teal : colors.amber} />
        <Text style={{ color: declarable ? colors.teal : colors.amber, fontWeight: "800", fontSize: 10 }}>{declarable ? "COMPILES TO ENGINE · RUNNABLE" : "METADATA ONLY"}</Text>
      </View>
      {declarable ? (
        <View style={{ gap: 4, marginTop: 6 }}>
          <Text style={type.small}>ENTRY (all): <Text style={{ color: colors.text }}>{(spec.entry || []).map(fmtCond).join("  AND  ")}</Text></Text>
          <Text style={type.small}>EXIT (any): <Text style={{ color: colors.text }}>{(spec.exit || []).map(fmtCond).join("  OR  ") || "structural stop only"}</Text></Text>
          <Text style={type.small}>PARAMS: <Text style={{ color: colors.text }}>{Object.entries(draft.engine_params || {}).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}</Text></Text>
          <Pressable testID="import-backtest-preview-btn" onPress={runPreview} disabled={running} style={[styles.previewBtn, running && { opacity: 0.5 }]}>
            {running ? <ActivityIndicator color={colors.bg} /> : <Text style={{ color: colors.bg, fontWeight: "800", fontSize: 12 }}>RUN BACKTEST PREVIEW</Text>}
          </Pressable>
          {bt && <Text testID="import-preview-result" style={[type.small, { marginTop: 6 }]}>ROI <Text style={{ color: bt.roi >= 0 ? colors.teal : colors.red, fontWeight: "700" }}>{bt.roi}%</Text> · WR {bt.win_rate}% · PF {bt.profit_factor} · {bt.trade_count} trades ({bt.bars} bars)</Text>}
        </View>
      ) : (
        <Text style={[type.small, { marginTop: 6, lineHeight: 18 }]}>{draft.declarative_reason || "Saved as a reference blueprint — the rule engine can't auto-run this logic yet."}</Text>
      )}
    </Card>
  );
}


const confColor = (v: number) => (v >= 75 ? colors.teal : v >= 50 ? colors.amber : colors.red);

function RuleList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items || items.length === 0) return null;
  return (
    <Card style={{ marginTop: spacing.sm }}>
      <SectionLabel>{title}</SectionLabel>
      {items.map((it, i) => (
        <View key={i} style={styles.ruleRow}>
          <View style={[styles.dot, { backgroundColor: tone }]} />
          <Text style={[type.body, { flex: 1, fontSize: 13 }]}>{it}</Text>
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  back: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  chip: { flexDirection: "row", alignItems: "center", gap: 5, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm + 2, paddingVertical: 7 },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  input: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, color: colors.text, fontSize: 14, marginTop: 6 },
  badge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", borderWidth: 1, borderRadius: radius.pill, paddingVertical: 4, paddingHorizontal: 10, marginTop: 8 },
  previewBtn: { backgroundColor: colors.teal, borderRadius: radius.sm, paddingVertical: 10, alignItems: "center", marginTop: 8 },

  codeInput: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, padding: spacing.md, color: colors.text, fontSize: 12, minHeight: 180, marginTop: 6, fontFamily: "monospace" },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.sm, paddingVertical: 14, marginTop: spacing.lg },
  primaryBtnTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
  secondaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: "transparent", borderWidth: 1, borderColor: colors.teal, borderRadius: radius.sm, paddingVertical: 12, marginTop: spacing.sm },
  secondaryBtnTxt: { color: colors.teal, fontWeight: "800", fontSize: 13 },
  statRow: { flexDirection: "row", gap: spacing.sm },
  statCard: { flex: 1, alignItems: "center", paddingVertical: spacing.md },
  issueRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 8 },
  ruleRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 6 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
});
