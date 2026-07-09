import React from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { pct } from "../../src/format";

const STATUS_TONE: Record<string, any> = { LIVE: "teal", PAPER: "amber", DISABLED: "muted", ERROR: "red" };
const healthColor = (v: number) => (v >= 60 ? colors.teal : v >= 35 ? colors.amber : colors.red);
const STATES = [{ key: "LIVE", label: "LIVE" }, { key: "PAPER", label: "PAPER" }, { key: "DISABLED", label: "OFF" }];

export default function StrategyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const { data, loading, error, refresh } = useFetch(api.strategyMetrics, [], 0);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const s = (data?.metrics || {})[id as string];
  if (!s) return <View style={styles.fill}><ErrorView message="Strategy not found" onRetry={refresh} /></View>;

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
        <SectionLabel>STRATEGY HEALTH</SectionLabel>
        <View style={styles.rowBetween}>
          <Text style={[type.hero, { fontSize: 52, color: healthColor(s.health) }]} testID="health-score-value">{s.health}</Text>
          <View style={{ flex: 1, marginLeft: spacing.lg }}>
            {(s.health_breakdown || []).map((c: any) => (
              <View key={c.key} style={{ marginBottom: 6 }} testID={`health-comp-${c.key}`}>
                <View style={styles.rowBetween}><Text style={type.small}>{c.label}</Text><Text style={[type.small, { color: healthColor(c.score), fontWeight: "700" }]}>{c.score}</Text></View>
                <View style={styles.track}><View style={[styles.trackFill, { width: `${Math.max(2, c.score)}%`, backgroundColor: healthColor(c.score) }]} /></View>
              </View>
            ))}
          </View>
        </View>
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
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  back: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  backTxt: { color: colors.teal, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  track: { height: 6, borderRadius: 3, backgroundColor: colors.bgElevated, overflow: "hidden", marginTop: 2 },
  trackFill: { height: 6, borderRadius: 3 },
  tlRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  stateRow: { flexDirection: "row", gap: spacing.sm },
  stateBtn: { flex: 1, alignItems: "center", paddingVertical: spacing.sm + 2, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder },
  stateBtnActive: { backgroundColor: colors.teal, borderColor: colors.teal },
  stateTxt: { color: colors.textMuted, fontWeight: "700", letterSpacing: 1, fontSize: 12 },
});
