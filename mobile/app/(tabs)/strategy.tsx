import React from "react";
import { View, Text, ScrollView, StyleSheet, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { PageHeader } from "../../src/components/PageHeader";
import { colors, spacing, type, pnlColor } from "../../src/theme";
import { pct, timeAgo } from "../../src/format";

const STATUS_TONE: Record<string, any> = { LIVE: "teal", PAPER: "amber", DISABLED: "muted", ERROR: "red", TESTING: "neutral", OPTIMIZING: "neutral" };
const healthColor = (v: number) => (v >= 60 ? colors.teal : v >= 35 ? colors.amber : colors.red);

export default function StrategyList() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { data, loading, error, refresh, refreshing } = useFetch(api.strategyMetrics, [], 20000);

  if (loading && !data) return <View style={styles.fill}><LoadingView label="Strategies" /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const metrics = data?.metrics || {};
  const list = Object.values(metrics) as any[];

  return (
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}>
      <PageHeader title="Strategy Center" question="What strategies do I own?" />

      {list.map((s: any) => (
        <Card key={s.key} testID={`strategy-card-${s.key}`} onPress={() => router.push(`/strategy/${s.key}`)} style={{ marginBottom: spacing.sm }}>
          <View style={styles.rowBetween}>
            <Text style={type.h3}>{s.name}</Text>
            <Pill label={s.status} tone={STATUS_TONE[s.status] || "muted"} dot />
          </View>
          <View style={[styles.rowBetween, { marginTop: spacing.sm }]}>
            <View>
              <Text style={type.label}>HEALTH</Text>
              <Text style={[type.h2, { color: healthColor(s.health) }]}>{s.health}</Text>
            </View>
            <Stat label="WIN RATE" value={`${s.win_rate}%`} />
            <Stat label="ROI" value={pct(s.roi)} color={s.roi >= 0 ? colors.teal : colors.red} />
            <Stat label="TRADES" value={String(s.trades)} />
          </View>
          <View style={[styles.rowBetween, { marginTop: spacing.sm }]}>
            <Text style={type.small}>{s.last_trade ? `Last trade ${timeAgo(s.last_trade)}` : "No trades yet"}</Text>
            <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
          </View>
        </Card>
      ))}
    </ScrollView>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={{ alignItems: "flex-end" }}>
      <Text style={type.label}>{label}</Text>
      <Text style={[type.h3, { fontSize: 16, color: color || colors.text }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
});
