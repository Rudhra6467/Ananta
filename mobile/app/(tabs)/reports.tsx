import React from "react";
import { View, Text, ScrollView, RefreshControl, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { FunnelBar } from "../../src/components/FunnelBar";
import { EdgeDiscovery } from "../../src/components/EdgeDiscovery";
import { LoadingView, ErrorView, EmptyView } from "../../src/components/StateView";
import { colors, spacing, type, pnlColor } from "../../src/theme";
import { pct } from "../../src/format";

export default function Reports() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { data, loading, error, refreshing, refresh } = useFetch(async () => {
    const [lab, edge] = await Promise.all([api.researchStrategyLab(), api.researchEntryQuality()]);
    return { ...lab, edge };
  }, [], 0);

  const strategies: any[] = data?.strategies || [];

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  return (
    <View style={styles.fill}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.lg }}>
        <Text style={type.h1}>Research</Text>
        <Text style={[type.bodyMuted, { marginTop: 2 }]}>Strategy lab — alpha models competing for capital</Text>
      </View>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}
      >
        {strategies.length === 0 ? (
          <EmptyView icon="flask-outline" title="No strategy data yet" />
        ) : (
          <>
            <EdgeDiscovery data={data?.edge} />
            {strategies.map((s) => (
              <StrategyCard key={s.id} s={s} onPress={() => router.push(`/strategy/${s.id}`)} />
            ))}
          </>
        )}
      </ScrollView>
    </View>
  );
}

export function StrategyCard({ s, onPress }: { s: any; onPress?: () => void }) {
  const execMode = s.mode === "EXECUTE";
  return (
    <Card testID={`strategy-${s.id}`} onPress={onPress} style={{ marginBottom: spacing.sm }}>
      <View style={styles.row}>
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Text style={styles.name} numberOfLines={1}>{s.name}</Text>
          <Text style={styles.scenario}>{s.scenario}</Text>
        </View>
        <Pill label={execMode ? "ACTIVE" : "SHADOW"} tone={execMode ? "teal" : "muted"} dot={execMode} />
      </View>

      <View style={{ marginTop: spacing.md }}>
        <FunnelBar detected={s.detected} qualified={s.qualified} resolved={s.resolved} />
      </View>

      <View style={styles.stats}>
        <Stat label="Qual %" value={pct(s.qualification_rate_pct)} />
        <Stat label="Win Rate" value={s.win_rate_pct == null ? "—" : `${s.win_rate_pct}%`} tone={s.win_rate_pct >= 50 ? colors.teal : undefined} />
        <Stat label="Exp Value" value={s.expected_value_pct == null ? "—" : pct(s.expected_value_pct)} tone={s.expected_value_pct != null ? pnlColor(s.expected_value_pct) : undefined} />
      </View>

      <View style={styles.verdict}>
        <Ionicons name="chevron-forward" size={14} color={colors.textFaint} />
        <Text style={styles.verdictText}>{s.verdict}</Text>
      </View>
    </Card>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statVal, tone ? { color: tone } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  row: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  name: { color: colors.text, fontSize: 16, fontWeight: "800" },
  scenario: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  stats: { flexDirection: "row", marginTop: spacing.md },
  statLabel: { color: colors.textFaint, fontSize: 11, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase" },
  statVal: { color: colors.text, fontSize: 16, fontWeight: "800", marginTop: 3 },
  verdict: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.md },
  verdictText: { color: colors.textMuted, fontSize: 12, fontStyle: "italic" },
});
