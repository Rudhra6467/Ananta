import React from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { CandleChart } from "../../src/components/charts";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { colors, spacing, type, pnlColor } from "../../src/theme";
import { price, pct } from "../../src/format";

export default function AssetDetail() {
  const { symbol } = useLocalSearchParams<{ symbol: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const full = `${symbol}/USD`;

  const { data, loading, error, refresh } = useFetch(async () => {
    const [candles, market, reasoning] = await Promise.all([
      api.candles(full, "1h", 60),
      api.marketSnapshots(),
      api.reasoning(1, full),
    ]);
    return { candles, market, reasoning };
  }, [symbol]);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const snap = (data!.market?.snapshots || []).find((s: any) => s.symbol === full) || {};
  const candles = (data!.candles?.candles || []).map((c: any) => ({ t: c.t, open: c.open, high: c.high, low: c.low, close: c.close }));
  const item = (data!.reasoning?.items || [])[0] || {};
  const ev = item.evidence || {};
  const lvl = ev.level || {};
  const regime = ev.market_regime;
  const rsi = lvl.rsi_4h;
  const trendAligned = ev.htf_trend_aligned;
  const hunterTriggered = lvl.primary_triggered;
  const breaker = ev.breaker_state;

  return (
    <View style={styles.fill}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="asset-back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.headerTitle}>{symbol}/USD</Text>
        <View style={{ width: 26 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        <View style={styles.priceRow}>
          <Text style={styles.price}>{price(snap.price)}</Text>
          <Text style={[styles.change, { color: pnlColor(snap.change_24h_pct ?? 0) }]}>
            {(snap.change_24h_pct ?? 0) >= 0 ? "▲" : "▼"} {pct(snap.change_24h_pct)} · 24h
          </Text>
        </View>

        <Card style={{ marginTop: spacing.md }}>
          <CandleChart candles={candles} width={width - spacing.lg * 2 - spacing.md * 2} />
          <Text style={styles.chartLabel}>1H · last {candles.length} candles</Text>
        </Card>

        <SectionLabel style={{ marginTop: spacing.lg }}>Engine Read</SectionLabel>
        <Card>
          <ReadRow label="Hunter setup" value={hunterTriggered ? "TRIGGERED" : "No setup"} tone={hunterTriggered ? colors.teal : colors.textMuted} />
          <ReadRow label="Regime" value={regime || "—"} />
          <ReadRow label="HTF trend" value={trendAligned == null ? "—" : trendAligned ? "Aligned ↑" : "Not aligned"} tone={trendAligned ? colors.teal : colors.textMuted} />
          <ReadRow label="RSI (4h)" value={rsi != null ? String(rsi) : "—"} />
          <ReadRow label="Breaker" value={breaker || "—"} tone={breaker === "PASS" ? colors.teal : breaker === "VETO" ? colors.red : colors.amber} last />
        </Card>

        <SectionLabel style={{ marginTop: spacing.lg }}>Current Reasoning</SectionLabel>
        <Card>
          <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm }}>
            <Pill label={item.bias || "NEUTRAL"} tone={item.bias === "BULLISH" ? "teal" : item.bias === "BEARISH" ? "red" : "muted"} dot />
            {item.confidence != null && <Pill label={`conf ${(item.confidence * 100).toFixed(0)}%`} tone="neutral" />}
          </View>
          <Text style={styles.reason}>{item.reason || "No reasoning recorded for this asset yet."}</Text>
        </Card>
      </ScrollView>
    </View>
  );
}

function ReadRow({ label, value, tone, last }: { label: string; value: string; tone?: string; last?: boolean }) {
  return (
    <View style={[styles.row, !last && styles.divider]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, tone ? { color: tone } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.text, fontSize: 18, fontWeight: "800", letterSpacing: 0.5 },
  priceRow: { alignItems: "flex-start" },
  price: { color: colors.text, fontSize: 38, fontWeight: "800", letterSpacing: -1 },
  change: { fontSize: 15, fontWeight: "700", marginTop: 4 },
  chartLabel: { color: colors.textFaint, fontSize: 12, marginTop: spacing.sm },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: spacing.md },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  rowLabel: { color: colors.textMuted, fontSize: 14 },
  rowValue: { color: colors.text, fontSize: 14, fontWeight: "700" },
  reason: { color: colors.text, fontSize: 14, lineHeight: 20 },
});
