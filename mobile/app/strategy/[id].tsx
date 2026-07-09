import React, { useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Modal, Alert } from "react-native";
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

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  back: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  backTxt: { color: colors.teal, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  track: { height: 6, borderRadius: 3, backgroundColor: colors.bgElevated, overflow: "hidden", marginTop: 2 },
  trackFill: { height: 6, borderRadius: 3 },
  learnRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  learnTxt: { flex: 1, color: colors.teal, fontSize: 13, fontWeight: "700" },
  modalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, paddingBottom: 40, borderWidth: 1, borderColor: colors.cardBorder },
  tlRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  stateRow: { flexDirection: "row", gap: spacing.sm },
  stateBtn: { flex: 1, alignItems: "center", paddingVertical: spacing.sm + 2, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder },
  stateBtnActive: { backgroundColor: colors.teal, borderColor: colors.teal },
  stateTxt: { color: colors.textMuted, fontWeight: "700", letterSpacing: 1, fontSize: 12 },
});
