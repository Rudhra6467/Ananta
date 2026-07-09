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
      Alert.alert("Analysis failed", e?.message || "Could not analyze the strategy");
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
            <Text style={styles.primaryBtnTxt}>{busy ? "Analyzing…" : "Analyze with AI"}</Text>
          </Pressable>
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
  codeInput: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, padding: spacing.md, color: colors.text, fontSize: 12, minHeight: 180, marginTop: 6, fontFamily: "monospace" },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.sm, paddingVertical: 14, marginTop: spacing.lg },
  primaryBtnTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
  statRow: { flexDirection: "row", gap: spacing.sm },
  statCard: { flex: 1, alignItems: "center", paddingVertical: spacing.md },
  issueRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 8 },
  ruleRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 6 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
});
