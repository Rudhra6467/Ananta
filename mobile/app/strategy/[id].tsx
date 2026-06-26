import React from "react";
import { View, Text, ScrollView, StyleSheet, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { FunnelBar } from "../../src/components/FunnelBar";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { colors, spacing, type, pnlColor } from "../../src/theme";
import { pct } from "../../src/format";

export default function StrategyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { data, loading, error, refresh } = useFetch(api.researchStrategyLab, []);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const s = (data?.strategies || []).find((x: any) => x.id === id);
  if (!s) return <View style={styles.fill}><ErrorView message="Strategy not found" onRetry={refresh} /></View>;

  const exec = s.mode === "EXECUTE";
  const vsh = s.vs_hunter || {};

  return (
    <View style={styles.fill}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="strategy-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>{s.scenario}</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <Text style={type.h1}>{s.name}</Text>
        <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
          <Pill label={exec ? "ACTIVE TRADER" : "SHADOW MODE"} tone={exec ? "teal" : "muted"} dot={exec} />
          <Pill label={s.verdict} tone="neutral" />
        </View>

        <SectionLabel style={{ marginTop: spacing.lg }}>Signal Attrition</SectionLabel>
        <Card>
          <FunnelBar detected={s.detected} qualified={s.qualified} resolved={s.resolved} />
          <View style={styles.inlineStats}>
            <Mini label="Qualification" value={pct(s.qualification_rate_pct)} />
            <Mini label="Breaker Pass" value={String(s.breaker_pass ?? 0)} />
            <Mini label="Conversion" value={pct(s.conversion_rate_pct)} />
          </View>
        </Card>

        <SectionLabel style={{ marginTop: spacing.lg }}>Outcomes</SectionLabel>
        <Card>
          <View style={styles.grid}>
            <Metric label="Wins" value={String(s.wins ?? 0)} tone={colors.teal} />
            <Metric label="Losses" value={String(s.losses ?? 0)} tone={colors.red} />
            <Metric label="Win Rate" value={s.win_rate_pct == null ? "—" : `${s.win_rate_pct}%`} tone={s.win_rate_pct >= 50 ? colors.teal : undefined} />
            <Metric label="Avg Return" value={s.avg_return_pct == null ? "—" : pct(s.avg_return_pct)} tone={s.avg_return_pct != null ? pnlColor(s.avg_return_pct) : undefined} />
            <Metric label="Expectancy" value={s.expected_value_pct == null ? "—" : pct(s.expected_value_pct)} tone={s.expected_value_pct != null ? pnlColor(s.expected_value_pct) : undefined} />
            <Metric label="Profit Factor" value={s.profit_factor == null ? "—" : s.profit_factor.toFixed(2)} />
            <Metric label="Max Drawdown" value={`${s.max_drawdown_pct ?? 0}%`} tone={colors.red} />
            <Metric label="Resolved" value={String(s.resolved ?? 0)} />
          </View>
        </Card>

        {s.id !== "hunter" && (
          <>
            <SectionLabel style={{ marginTop: spacing.lg }}>Comparison vs Hunter</SectionLabel>
            <Card>
              <CompRow label="Win Rate" value={vsh.win_rate} suffix="" />
              <CompRow label="Avg Return" value={vsh.avg_return} pctVal />
              <CompRow label="Expected Value" value={vsh.expected_value} pctVal />
              <CompRow label="Profit Factor" value={vsh.profit_factor} last />
            </Card>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.miniLabel}>{label}</Text>
      <Text style={styles.miniVal}>{value}</Text>
    </View>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.miniLabel}>{label}</Text>
      <Text style={[styles.metricVal, tone ? { color: tone } : null]}>{value}</Text>
    </View>
  );
}

function CompRow({ label, value, pctVal, suffix, last }: { label: string; value: any; pctVal?: boolean; suffix?: string; last?: boolean }) {
  const display = value == null ? "—" : pctVal ? pct(value) : `${value}${suffix ?? ""}`;
  const tone = value == null ? colors.textMuted : value >= 0 ? colors.teal : colors.red;
  return (
    <View style={[styles.row, !last && styles.divider]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, { color: tone }]}>{display}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.text, fontSize: 16, fontWeight: "700", flex: 1, textAlign: "center" },
  inlineStats: { flexDirection: "row", marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.cardBorder, paddingTop: spacing.md },
  miniLabel: { color: colors.textFaint, fontSize: 11, fontWeight: "700", letterSpacing: 0.4, textTransform: "uppercase" },
  miniVal: { color: colors.text, fontSize: 16, fontWeight: "800", marginTop: 3 },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  metric: { width: "50%", paddingVertical: spacing.sm },
  metricVal: { color: colors.text, fontSize: 20, fontWeight: "800", marginTop: 3 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.md },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  rowLabel: { color: colors.textMuted, fontSize: 14 },
  rowValue: { fontSize: 15, fontWeight: "800" },
});
