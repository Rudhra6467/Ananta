import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { LoadingView } from "../../src/components/StateView";
import { colors, spacing, type, radius } from "../../src/theme";

const GRADE_COLOR: Record<string, string> = { A: colors.teal, B: colors.teal, C: colors.amber, D: colors.amber, E: colors.red };

export default function LibraryDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [s, setS] = useState<any>(null);
  const [grading, setGrading] = useState(false);

  const load = () => api.libraryGet(id as string).then((d: any) => {
    if (d.internal && d.engine_key) { router.replace(`/strategy/${d.engine_key}`); return; }
    setS(d);
  }).catch(() => setS(false));
  useEffect(() => { load(); }, [id]);

  const regrade = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setGrading(true);
    try { const g = await api.libraryAiGrade(id as string); Alert.alert("Re-graded", `${g.ai_grade} · ${g.ai_health_score}/100`); load(); }
    catch (e: any) { Alert.alert("AI grade failed", e?.response?.data?.detail || e?.message); }
    finally { setGrading(false); }
  };

  if (s === null) return <View style={styles.fill}><LoadingView /></View>;
  if (s === false) return <View style={styles.fill}><Text style={[type.body, { padding: spacing.lg }]}>Strategy not found.</Text></View>;
  const r = s.historical_results || {};

  return (
    <ScrollView style={styles.fill} testID="catalog-detail" contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
      <Pressable testID="catalog-back" onPress={() => router.back()} style={styles.back}>
        <Ionicons name="chevron-back" size={18} color={colors.teal} />
        <Text style={{ color: colors.teal, fontWeight: "700", fontSize: 12 }}>Library</Text>
      </Pressable>

      <Card style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={type.h2} numberOfLines={2}>{s.name}</Text>
            <Text style={[type.small, { marginTop: 2 }]}>{s.style} · {s.category} · {s.source}</Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <View style={[styles.grade, { borderColor: GRADE_COLOR[s.ai_grade] || colors.amber }]}>
              <Text style={[styles.gradeTxt, { color: GRADE_COLOR[s.ai_grade] || colors.amber }]}>Grade {s.ai_grade}</Text>
            </View>
            <Pressable testID="catalog-favorite" onPress={() => api.libraryFavorite(id as string).then(load)} hitSlop={8}>
              <Ionicons name={s.favorite ? "heart" : "heart-outline"} size={22} color={s.favorite ? colors.teal : colors.textMuted} />
            </Pressable>
          </View>
        </View>
        <Text style={[type.body, { marginTop: spacing.sm, lineHeight: 20 }]}>{s.description}</Text>
        <View style={styles.tagWrap}>
          {(s.market_regimes || []).map((m: string) => <Pill key={m} label={m} tone="neutral" />)}
          <Pill label={s.risk} tone="neutral" />
          {(s.timeframes || []).map((t: string) => <Pill key={t} label={t} tone="neutral" />)}
        </View>
      </Card>

      <Card testID="catalog-ai" style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Ionicons name="sparkles" size={15} color={colors.teal} />
            <SectionLabel>AI ASSESSMENT</SectionLabel>
          </View>
          <Pressable testID="catalog-regrade" onPress={regrade} disabled={grading || !isOwner} style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: !isOwner ? 0.4 : 1 }}>
            {grading ? <ActivityIndicator color={colors.teal} size="small" /> : <Ionicons name="refresh" size={14} color={colors.teal} />}
            <Text style={{ color: colors.teal, fontSize: 11, fontWeight: "700" }}>Re-grade</Text>
          </Pressable>
        </View>
        <Text style={[type.body, { marginTop: spacing.sm, lineHeight: 20 }]}>{s.ai_summary}</Text>
        <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm }}>
          <Text style={type.small}>Health <Text style={{ color: colors.text, fontWeight: "800" }}>{s.ai_health_score}/100</Text></Text>
          <Text style={type.small}>Confidence <Text style={{ color: colors.text, fontWeight: "800" }}>{s.ai_confidence}%</Text></Text>
        </View>
      </Card>

      <Card style={{ marginBottom: spacing.md }}>
        <SectionLabel>BACKTEST PERFORMANCE</SectionLabel>
        <Text style={[type.small, { marginBottom: spacing.sm }]}>Seeded — run a real backtest to validate.</Text>
        <View style={styles.perfGrid}>
          {[["ROI", `${r.roi}%`], ["Win Rate", `${r.win_rate}%`], ["Profit Factor", r.profit_factor], ["Sharpe", r.sharpe],
            ["Sortino", r.sortino], ["Max DD", `${r.max_drawdown}%`], ["Avg Trade", `${r.avg_trade}%`], ["Trades", r.trade_count]].map(([k, v]) => (
            <View key={String(k)} style={styles.perfCell}>
              <Text style={type.label}>{String(k).toUpperCase()}</Text>
              <Text style={[type.h3, { fontSize: 15 }]}>{String(v)}</Text>
            </View>
          ))}
        </View>
      </Card>

      <RuleList title="ENTRY RULES" items={s.entry_rules} tone={colors.teal} />
      <RuleList title="EXIT RULES" items={s.exit_rules} tone={colors.teal} />
      <RuleList title="IDEAL CONDITIONS" items={s.ideal_conditions} tone={colors.teal} />
      <RuleList title="AVOID CONDITIONS" items={s.avoid_conditions} tone={colors.red} />
    </ScrollView>
  );
}

function RuleList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <SectionLabel>{title}</SectionLabel>
      {(items || []).map((it, i) => (
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
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.sm },
  grade: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  gradeTxt: { fontSize: 10, fontWeight: "800" },
  tagWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.sm },
  perfGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  perfCell: { width: "47%", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, padding: spacing.sm, backgroundColor: colors.bgElevated },
  ruleRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 6 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
});
