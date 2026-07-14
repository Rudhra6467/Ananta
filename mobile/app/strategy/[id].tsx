import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Modal, Alert, TextInput, ActivityIndicator, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { HealthRing } from "../../src/components/HealthRing";
import { MetricExplainer } from "../../src/components/MetricExplainer";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { STRATEGY_LESSON, lessonByKey } from "../../src/academy";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { pct } from "../../src/format";

/** Confirm dialog that works on native (Alert) AND react-native-web (window.confirm),
 * since multi-button Alert.alert is a no-op on web. */
function confirmAction(title: string, message: string, confirmLabel: string, onConfirm: () => void) {
  if (Platform.OS === "web") {
    // eslint-disable-next-line no-alert
    if (typeof window !== "undefined" && window.confirm(`${title}\n\n${message}`)) onConfirm();
    return;
  }
  Alert.alert(title, message, [
    { text: "Cancel", style: "cancel" },
    { text: confirmLabel, onPress: onConfirm },
  ]);
}

const STATUS_TONE: Record<string, any> = { LIVE: "teal", PAPER: "amber", DISABLED: "muted", ERROR: "red" };
const healthColor = (v: number) => (v >= 60 ? colors.teal : v >= 35 ? colors.amber : colors.red);
const STATES = [{ key: "LIVE", label: "LIVE" }, { key: "PAPER", label: "PAPER" }, { key: "DISABLED", label: "OFF" }];

export default function StrategyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const { data, loading, error, refresh } = useFetch(api.strategyMetrics, [], 0);
  const [lessonOpen, setLessonOpen] = useState(false);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const s = (data?.metrics || {})[id as string];
  if (!s) return <View style={styles.fill}><ErrorView message="Strategy not found" onRetry={refresh} /></View>;

  const lesson = lessonByKey(STRATEGY_LESSON[id as string] || "hunter");

  const setState = (status: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    Alert.alert("Change status", `Set ${s.name} to ${status}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Confirm", onPress: async () => { try { await api.strategySetState(id as string, status); refresh(); } catch (e: any) { Alert.alert("Failed", e?.message); } } },
    ]);
  };

  return (
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 40 }}>
      <Pressable onPress={() => router.back()} style={styles.back}><Ionicons name="chevron-back" size={20} color={colors.teal} /><Text style={styles.backTxt}>STRATEGY CENTER</Text></Pressable>

      <View style={[styles.rowBetween, { marginBottom: spacing.md }]}>
        <Text style={type.h1}>{s.name}</Text>
        <Pill label={s.status} tone={STATUS_TONE[s.status] || "muted"} dot />
      </View>

      {/* Health */}
      <Card testID="strategy-health-card" style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <SectionLabel>STRATEGY HEALTH</SectionLabel>
            <MetricExplainer metric="health" value={s.health} />
          </View>
        </View>
        <View style={[styles.rowBetween, { marginTop: spacing.sm }]}>
          <HealthRing score={s.health} />
          <View style={{ flex: 1, marginLeft: spacing.lg }}>
            {(s.health_breakdown || []).map((c: any) => {
              const explain = c.key === "win_rate" ? "win_rate" : c.key === "risk" ? "roi" : null;
              return (
                <View key={c.key} style={{ marginBottom: 6 }} testID={`health-comp-${c.key}`}>
                  <View style={styles.rowBetween}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                      <Text style={type.small}>{c.label}</Text>
                      {explain && <MetricExplainer metric={explain} value={c.score} size={13} />}
                    </View>
                    <Text style={[type.small, { color: healthColor(c.score), fontWeight: "700" }]}>{c.score}</Text>
                  </View>
                  <View style={styles.track}><View style={[styles.trackFill, { width: `${Math.max(2, c.score)}%`, backgroundColor: healthColor(c.score) }]} /></View>
                </View>
              );
            })}
          </View>
        </View>
        <Pressable testID="strategy-academy-link" onPress={() => setLessonOpen(true)} style={styles.learnRow}>
          <Ionicons name="book-outline" size={15} color={colors.teal} />
          <Text style={styles.learnTxt}>Learn how {s.name} works</Text>
          <Ionicons name="chevron-forward" size={15} color={colors.textFaint} />
        </Pressable>
      </Card>

      {/* Timeline */}
      <Card testID="strategy-timeline" style={{ marginBottom: spacing.md }}>
        <SectionLabel>LIFECYCLE TIMELINE</SectionLabel>
        {(s.timeline || []).map((e: any) => (
          <View key={e.key} style={styles.tlRow} testID={`timeline-${e.key}`}>
            <Ionicons name={e.done ? "checkmark-circle" : "ellipse-outline"} size={18} color={e.done ? colors.teal : colors.textFaint} />
            <View style={{ flex: 1 }}>
              <Text style={[type.body, { fontWeight: "600", color: e.done ? colors.text : colors.textFaint }]}>{e.label}</Text>
              <Text style={type.small}>{e.detail}</Text>
            </View>
          </View>
        ))}
      </Card>

      {/* Configs (Phase 2: activate a config to drive the live engine) */}
      <StrategyConfigs sKey={id as string} activeId={s.active_config_id} isOwner={isOwner} onChanged={refresh} />

      {/* Edit / status */}
      <Card testID="strategy-edit-card">
        <SectionLabel>EDIT STRATEGY</SectionLabel>
        <Text style={[type.small, { marginBottom: spacing.sm }]}>Set the live status. Full parameter tuning is available on the web app.</Text>
        <View style={styles.stateRow}>
          {STATES.map((st) => (
            <Pressable key={st.key} testID={`set-state-${st.key}`} onPress={() => setState(st.key)} disabled={!isOwner}
              style={[styles.stateBtn, s.status === st.key && styles.stateBtnActive, !isOwner && { opacity: 0.5 }]}>
              <Text style={[styles.stateTxt, s.status === st.key && { color: colors.bg }]}>{st.label}</Text>
            </Pressable>
          ))}
        </View>
      </Card>

      {/* Test this strategy → Research validate, pre-loaded for this strategy */}
      <Pressable testID="detail-test-strategy" onPress={() => router.push({ pathname: "/(tabs)/research", params: { strat: id as string } })} style={styles.testBtn}>
        <Ionicons name="shield-checkmark" size={16} color={colors.teal} />
        <Text style={styles.testTxt}>TEST THIS STRATEGY</Text>
      </Pressable>

      {/* Academy lesson deep-link modal */}
      <Modal visible={lessonOpen} transparent animationType="slide" onRequestClose={() => setLessonOpen(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.rowBetween}>
              <Text style={type.h2}>{lesson?.title}</Text>
              <Pressable testID="strategy-academy-close" onPress={() => setLessonOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </Pressable>
            </View>
            <Text style={[type.body, { marginTop: spacing.md, lineHeight: 22 }]}>{lesson?.body}</Text>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

function StrategyConfigs({ sKey, activeId, isOwner, onChanged }: { sKey: string; activeId?: string; isOwner: boolean; onChanged: () => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [importOpen, setImportOpen] = useState(false);
  const [text, setText] = useState("");

  const load = () => api.strategyConfigs(sKey).then((d: any) => setRows(d.configs || [])).catch(() => setRows([]));
  useEffect(() => { load(); }, [sKey]);

  const activate = (cfg: any) => {
    if (!isOwner) return Alert.alert("Owner login required");
    if (cfg.validation_status !== "passed") return Alert.alert("Validation required", "This config must pass validation before it can go live.");
    confirmAction("Activate config", `Make "${cfg.name}" the live config for this strategy? Its parameters will drive the engine.`, "Activate", async () => {
      setBusy(cfg.id);
      try { const r = await api.strategyConfigActivate(cfg.id); const ig = (r.ignored_account_level || []).length; Alert.alert("Activated", `${r.applied} strategy params now live${ig ? ` · ${ig} account-level ignored` : ""}`); load(); onChanged(); }
      catch (e: any) { Alert.alert("Failed", e?.response?.data?.detail || e?.message); }
      finally { setBusy(""); }
    });
  };

  const deactivate = (key: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    confirmAction("Revert to default", "This strategy will go back to the global baseline params.", "Revert", async () => {
      setBusy("deactivate");
      try { await api.strategyDeactivate(key); load(); onChanged(); }
      catch (e: any) { Alert.alert("Failed", e?.response?.data?.detail || e?.message); }
      finally { setBusy(""); }
    });
  };

  const doImport = async () => {
    if (!text.trim()) return;
    let payload: any;
    try { payload = JSON.parse(text); } catch { return Alert.alert("Invalid JSON", "Paste a valid exported config."); }
    setBusy("import");
    try {
      await api.strategyConfigImport(payload.config ? payload : { config: payload });
      setImportOpen(false); setText(""); load(); onChanged();
      Alert.alert("Imported", "Strategy config imported and validated.");
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      Alert.alert("Import failed", (d?.errors && d.errors.join(", ")) || d || e?.message);
    } finally { setBusy(""); }
  };

  return (
    <Card testID="strategy-configs-card" style={{ marginBottom: spacing.md }}>
      <View style={styles.rowBetween}>
        <SectionLabel>CONFIGS</SectionLabel>
        <Pressable testID="config-import-btn" onPress={() => (isOwner ? setImportOpen(true) : Alert.alert("Owner login required"))} hitSlop={8} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Ionicons name="cloud-upload-outline" size={15} color={colors.teal} />
          <Text style={{ color: colors.teal, fontSize: 11, fontWeight: "700" }}>IMPORT</Text>
        </Pressable>
      </View>
      <Text style={[type.small, { marginBottom: spacing.sm }]}>Activate a validated config to drive the live engine. Import a strategy as JSON.</Text>
      {rows === null ? <ActivityIndicator color={colors.teal} /> : rows.length === 0 ? (
        <Text style={type.small}>No saved configs yet.</Text>
      ) : rows.map((c: any) => {
        const isActive = c.id === activeId;
        const validated = c.validation_status === "passed";
        return (
          <View key={c.id} testID={`config-row-${c.id.slice(0, 8)}`} style={[styles.cfgRow, isActive && { borderColor: colors.teal }]}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Text style={[type.body, { fontWeight: "600" }]} numberOfLines={1}>{c.name}</Text>
                {isActive && <View testID={`config-live-${c.id.slice(0, 8)}`} style={styles.liveBadge}><Text style={styles.liveTxt}>LIVE</Text></View>}
              </View>
              <Text style={type.small}>{c.origin} · {Object.keys(c.params || {}).length} overrides · {validated ? "validated" : "unvalidated"}</Text>
            </View>
            {!isActive ? (
              <Pressable testID={`config-activate-${c.id.slice(0, 8)}`} onPress={() => activate(c)} disabled={!isOwner || !validated || !!busy}
                style={[styles.activateBtn, (!isOwner || !validated) && { opacity: 0.35 }]}>
                {busy === c.id ? <ActivityIndicator color={colors.teal} size="small" /> : (<><Ionicons name="flash" size={13} color={colors.teal} /><Text style={styles.activateTxt}>ACTIVATE</Text></>)}
              </Pressable>
            ) : (
              <Pressable testID={`config-deactivate-${c.id.slice(0, 8)}`} onPress={() => deactivate(c.strategy_key)} disabled={!isOwner || !!busy}
                style={[styles.activateBtn, { borderColor: colors.cardBorder }, !isOwner && { opacity: 0.35 }]}>
                {busy === "deactivate" ? <ActivityIndicator color={colors.textMuted} size="small" /> : (<><Ionicons name="power" size={13} color={colors.textMuted} /><Text style={[styles.activateTxt, { color: colors.textMuted }]}>REVERT</Text></>)}
              </Pressable>
            )}
          </View>
        );
      })}

      <Modal visible={importOpen} transparent animationType="slide" onRequestClose={() => setImportOpen(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard}>
            <View style={styles.rowBetween}>
              <Text style={type.h2}>Import Strategy</Text>
              <Pressable testID="config-import-close" onPress={() => setImportOpen(false)} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <Text style={[type.small, { marginVertical: spacing.sm }]}>Paste an exported config JSON (schema-validated, no code execution).</Text>
            <TextInput testID="config-import-input" value={text} onChangeText={setText} multiline placeholder={'{"strategy_key":"hunter","name":"My Import","params":{"rsi_reset_max":40}}'}
              placeholderTextColor={colors.textFaint} style={styles.importInput} />
            <Pressable testID="config-import-submit" onPress={doImport} disabled={busy === "import"} style={[styles.stateBtn, styles.stateBtnActive, { marginTop: spacing.sm }]}>
              {busy === "import" ? <ActivityIndicator color={colors.bg} /> : <Text style={[styles.stateTxt, { color: colors.bg }]}>IMPORT</Text>}
            </Pressable>
          </View>
        </View>
      </Modal>
    </Card>
  );
}


const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  back: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  backTxt: { color: colors.teal, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  track: { height: 6, borderRadius: 3, backgroundColor: colors.bgElevated, overflow: "hidden", marginTop: 2 },
  trackFill: { height: 6, borderRadius: 3 },
  learnRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  testBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: spacing.md, borderWidth: 1, borderColor: colors.tealDim, backgroundColor: colors.tealGlow, borderRadius: radius.md, paddingVertical: spacing.sm + 3 },
  testTxt: { color: colors.teal, fontWeight: "800", letterSpacing: 1, fontSize: 13 },
  learnTxt: { flex: 1, color: colors.teal, fontSize: 13, fontWeight: "700" },
  modalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, paddingBottom: 40, borderWidth: 1, borderColor: colors.cardBorder },
  tlRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  stateRow: { flexDirection: "row", gap: spacing.sm },
  stateBtn: { flex: 1, alignItems: "center", paddingVertical: spacing.sm + 2, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder },
  stateBtnActive: { backgroundColor: colors.teal, borderColor: colors.teal },
  stateTxt: { color: colors.textMuted, fontWeight: "700", letterSpacing: 1, fontSize: 12 },
  cfgRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.sm + 2, paddingVertical: spacing.sm, marginTop: spacing.sm },
  liveBadge: { borderWidth: 1, borderColor: colors.teal, backgroundColor: colors.tealGlow, borderRadius: 6, paddingHorizontal: 5, paddingVertical: 1 },
  liveTxt: { color: colors.teal, fontSize: 8, fontWeight: "800", letterSpacing: 0.5 },
  activateBtn: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.teal, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 6 },
  activateTxt: { color: colors.teal, fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  importInput: { minHeight: 110, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, color: colors.text, padding: spacing.sm, fontSize: 12, textAlignVertical: "top" },
});
