import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, TextInput, Modal, Alert, ActivityIndicator, Switch } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { setItem } from "../../src/storage";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { PageHeader } from "../../src/components/PageHeader";
import { Segmented } from "../../src/components/Segmented";
import { AskAnanta } from "../../src/components/AskAnanta";
import { FirstVisitTip } from "../../src/components/FirstVisitTip";
import { colors, spacing, type, radius } from "../../src/theme";
import { LESSONS } from "../../src/academy";

export default function Workspace() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner, owner, logout } = useAuth();
  const [settings, setSettings] = useState<any>(null);
  const [demo, setDemo] = useState<any>(null);
  const [env, setEnv] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [lesson, setLesson] = useState<any>(null);
  const [sub, setSub] = useState("ai");

  const load = () => {
    api.settings().then(setSettings).catch(() => {});
    api.demoStatus().then(setDemo).catch(() => {});
    api.getEnvironment().then(setEnv).catch(() => {});
  };
  useEffect(load, []);

  const saveSetting = async (key: string, val: string) => {
    if (!isOwner) return;
    const num = parseFloat(val); if (Number.isNaN(num)) return;
    try { const s = await api.updateSettings({ [key]: num }); setSettings(s); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const runDemo = async (kind: "load" | "reset") => {
    if (!isOwner) return Alert.alert("Owner login required");
    setBusy(kind);
    try {
      if (kind === "load") { const r = await api.demoLoad(); Alert.alert("Demo loaded", `${r.trades} trades across ${r.strategies.length} strategies`); }
      else { await api.demoReset(); Alert.alert("Reset", "Clean $1,200 paper book"); }
      load();
    } catch (e: any) { Alert.alert("Failed", e?.response?.data?.detail || e?.message); } finally { setBusy(""); }
  };
  const replayTour = async () => { await setItem("ananta_onboarded", "0"); router.push("/onboarding"); };
  const toggleKill = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const killed = !!settings?.manual_kill_switch;
    try { const s = await api.updateSettings({ manual_kill_switch: !killed }); setSettings(s); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };

  return (
    <View style={styles.fill}>
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
      <PageHeader title="Ananta Setup" question="How is my system configured?" />
      <FirstVisitTip tipKey="workspace" text="Configure your exit engine and risk before going live. Use Replay Guided Tour anytime." />

      <View style={{ marginBottom: spacing.md }}>
        <Segmented testIDPrefix="ws-subtab"
          options={[{ key: "ai", label: "AI INFO" }, { key: "engine", label: "ENGINE & RISK" }, { key: "learn", label: "LEARNING" }]}
          value={sub} onChange={setSub} />
      </View>

      {sub === "ai" && (
        <>
          {/* AI Copilot toggle (Ask Ananta) */}
          <Card style={{ marginBottom: spacing.md }} testID="ws-copilot">
            <View style={styles.rowBetween}>
              <View style={{ flex: 1, marginRight: spacing.sm }}>
                <SectionLabel>ASK ANANTA (AI COPILOT)</SectionLabel>
                <Text style={type.small}>Embedded AI assistant that answers questions and can execute actions with confirmation. Off until launch.</Text>
              </View>
              <Switch testID="ask-ananta-toggle" value={!!settings?.ask_ananta_enabled} disabled={!isOwner}
                onValueChange={async (v) => { if (!isOwner) return Alert.alert("Owner login required"); try { const s = await api.updateSettings({ ask_ananta_enabled: v }); setSettings(s); } catch (e: any) { Alert.alert("Failed", e?.message); } }}
                trackColor={{ true: colors.tealDim, false: colors.cardBorder }} thumbColor={settings?.ask_ananta_enabled ? colors.teal : colors.textFaint} />
            </View>
          </Card>
          <Card testID="ws-ai-coach-link">
            <SectionLabel>AI TRADE COACH</SectionLabel>
            <Text style={[type.small, { marginBottom: spacing.sm }]}>Structured logic setups, coaching logs and weekly reviews live in the Research and Trade tabs.</Text>
            <Pressable testID="ws-open-coach" onPress={() => router.push("/(tabs)/research")} style={[styles.btn, styles.btnGhost]}>
              <Ionicons name="sparkles" size={14} color={colors.teal} /><Text style={styles.btnGhostTxt}>  OPEN AI ANALYSIS</Text>
            </Pressable>
          </Card>
        </>
      )}

      {sub === "engine" && (
        <>
          {/* Engine & Risk + Stop Ananta */}
          <Card style={{ marginBottom: spacing.md }} testID="ws-settings">
            <View style={styles.rowBetween}>
              <SectionLabel>ENGINE & RISK</SectionLabel>
              <Pressable testID="ws-stop-ananta" onPress={toggleKill} style={[styles.stopBtn, settings?.manual_kill_switch && styles.stopBtnOn]}>
                <Ionicons name="power" size={13} color={colors.red} />
                <Text style={styles.stopTxt}>{settings?.manual_kill_switch ? "RELEASE" : "STOP ANANTA"}</Text>
              </Pressable>
            </View>
            {settings ? (
              <View style={{ marginTop: spacing.sm }}>
                <NumRow label="Min Confidence" k="min_confidence" value={settings.min_confidence} isOwner={isOwner} onSave={saveSetting} />
                <NumRow label="Daily Loss Cap %" k="max_daily_loss_pct" value={settings.max_daily_loss_pct} isOwner={isOwner} onSave={saveSetting} />
                <NumRow label="Max Open Positions" k="max_concurrent_positions" value={settings.max_concurrent_positions} isOwner={isOwner} onSave={saveSetting} />
              </View>
            ) : <ActivityIndicator color={colors.teal} />}
          </Card>

          <Card style={{ marginBottom: spacing.md }}>
            <SectionLabel>SYSTEM</SectionLabel>
            <Row label="Trading Mode" value={(env?.mode || "—").toUpperCase()} />
            <Row label="Live Gate" value={env?.ready_to_trade ? "Armed" : "Closed"} />
          </Card>

          {/* Competition Demo */}
          <Card style={{ borderColor: colors.tealDim }} testID="ws-demo">
            <View style={styles.rowBetween}>
              <SectionLabel>COMPETITION DEMO</SectionLabel>
              <Pill label={demo?.loaded ? `Loaded · ${demo.demo_trades}` : "Not loaded"} tone={demo?.loaded ? "teal" : "muted"} />
            </View>
            <Text style={[type.small, { marginVertical: spacing.sm }]}>One tap preloads a curated workspace across the 3 real strategies. Overwrites preview data.</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Pressable testID="ws-demo-load" onPress={() => runDemo("load")} disabled={!!busy || !isOwner} style={[styles.btn, styles.btnPrimary, (!isOwner) && { opacity: 0.4 }]}>
                {busy === "load" ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.btnPrimaryTxt}>LOAD DEMO</Text>}
              </Pressable>
              <Pressable testID="ws-demo-reset" onPress={() => runDemo("reset")} disabled={!!busy || !isOwner} style={[styles.btn, styles.btnGhost, (!isOwner) && { opacity: 0.4 }]}>
                <Text style={styles.btnGhostTxt}>RESET</Text>
              </Pressable>
            </View>
          </Card>
        </>
      )}

      {sub === "learn" && (
        <>
          {/* Academy */}
          <Card style={{ marginBottom: spacing.md }} testID="ws-academy">
            <SectionLabel>ACADEMY</SectionLabel>
            {LESSONS.map((l, i) => (
              <Pressable key={l.key} testID={`academy-lesson-${i}`} onPress={() => setLesson(l)} style={styles.lessonRow}>
                <Ionicons name="book" size={16} color={colors.teal} />
                <Text style={[type.body, { flex: 1 }]}>{l.title}</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
              </Pressable>
            ))}
          </Card>

          <Card style={{ marginBottom: spacing.md }}>
            <SectionLabel>GUIDES & DEMOS</SectionLabel>
            <Pressable testID="ws-tour-replay" onPress={replayTour} style={[styles.btn, styles.btnGhost, { marginTop: spacing.sm }]}>
              <Ionicons name="play" size={14} color={colors.teal} /><Text style={styles.btnGhostTxt}>  REPLAY GUIDED TOUR</Text>
            </Pressable>
          </Card>

          {/* About + logout */}
          <Card testID="ws-about">
            <SectionLabel>ABOUT</SectionLabel>
            <Text style={type.small}>Ananta.AI — an AI-native operating system for algorithmic trading. Spot-only, capital-preservation first.</Text>
            {isOwner && (
              <Pressable testID="ws-logout-btn" onPress={() => { logout(); Alert.alert("Signed out"); }} style={[styles.btn, styles.btnGhost, { marginTop: spacing.md }]}>
                <Ionicons name="log-out-outline" size={16} color={colors.textMuted} /><Text style={styles.btnGhostTxt}>  LOG OUT</Text>
              </Pressable>
            )}
          </Card>
        </>
      )}

      <Modal visible={!!lesson} transparent animationType="slide" onRequestClose={() => setLesson(null)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.rowBetween}>
              <Text style={type.h2}>{lesson?.title}</Text>
              <Pressable testID="academy-close" onPress={() => setLesson(null)}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <Text style={[type.body, { marginTop: spacing.md, lineHeight: 22 }]}>{lesson?.body}</Text>
          </View>
        </View>
      </Modal>
    </ScrollView>
    <AskAnanta tab="workspace" routeName="workspace" />
    </View>
  );
}

function NumRow({ label, k, value, isOwner, onSave }: any) {
  const [v, setV] = useState(String(value ?? ""));
  useEffect(() => setV(String(value ?? "")), [value]);
  return (
    <View style={styles.numRow}>
      <Text style={[type.body, { flex: 1 }]}>{label}</Text>
      <TextInput testID={`set-${k}`} value={v} onChangeText={setV} editable={isOwner} keyboardType="decimal-pad"
        onEndEditing={() => onSave(k, v)} style={styles.input} placeholderTextColor={colors.textFaint} />
    </View>
  );
}
function Row({ label, value }: { label: string; value: string }) {
  return <View style={styles.rowBetween}><Text style={type.body}>{label}</Text><Text style={[type.body, { color: colors.teal, fontWeight: "700" }]}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  numRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6 },
  input: { width: 90, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, color: colors.text, paddingHorizontal: spacing.sm, paddingVertical: 6, textAlign: "right", fontWeight: "700" },
  btn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", borderRadius: radius.md, paddingVertical: spacing.sm + 2 },
  btnPrimary: { backgroundColor: colors.teal },
  btnPrimaryTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 12 },
  btnGhost: { borderWidth: 1, borderColor: colors.cardBorder },
  btnGhostTxt: { color: colors.textMuted, fontWeight: "700", letterSpacing: 0.6, fontSize: 12 },
  lessonRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  stopBtn: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.redDim, borderRadius: radius.sm, paddingVertical: 5, paddingHorizontal: spacing.sm },
  stopBtnOn: { backgroundColor: colors.redGlow, borderColor: colors.red },
  stopTxt: { color: colors.red, fontWeight: "800", letterSpacing: 0.6, fontSize: 11 },
  modalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, paddingBottom: 40, borderWidth: 1, borderColor: colors.cardBorder },
});
