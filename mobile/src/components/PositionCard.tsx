import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Card } from "./Card";
import { Pill } from "./Pill";
import { colors, spacing, pnlColor } from "../theme";
import { usd, pct, price, base, duration } from "../format";

export type Position = {
  symbol: string;
  quantity: number;
  avg_cost: number;
  last_price?: number;
  peak_price?: number;
  entry_timestamp?: string;
  entry_attribution?: Record<string, any>;
};

function holdSeconds(iso?: string) {
  if (!iso) return 0;
  return Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
}

export function PositionCard({ p, onPress }: { p: Position; onPress?: () => void }) {
  const last = p.last_price ?? p.avg_cost;
  const unreal = (last - p.avg_cost) * p.quantity;
  const retPct = p.avg_cost > 0 ? ((last - p.avg_cost) / p.avg_cost) * 100 : 0;
  const tone = unreal >= 0 ? "teal" : "red";

  return (
    <Card testID={`position-${base(p.symbol)}`} onPress={onPress} style={styles.card}>
      <View style={styles.top}>
        <View>
          <Text style={styles.sym}>{base(p.symbol)}</Text>
          <Text style={styles.meta}>{p.quantity.toFixed(4)} @ {usd(p.avg_cost)}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={[styles.pnl, { color: pnlColor(unreal) }]}>
            {unreal >= 0 ? "+" : ""}{usd(unreal)}
          </Text>
          <Text style={[styles.ret, { color: pnlColor(retPct) }]}>{pct(retPct)}</Text>
        </View>
      </View>
      <View style={styles.bottom}>
        <Pill label={`LAST ${price(last)}`} tone="neutral" />
        <Pill label={`HELD ${duration(holdSeconds(p.entry_timestamp))}`} tone="muted" />
        <Pill label={unreal >= 0 ? "IN PROFIT" : "UNDERWATER"} tone={tone as any} dot />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { marginBottom: spacing.sm },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  sym: { color: colors.text, fontSize: 20, fontWeight: "800", letterSpacing: 0.5 },
  meta: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  pnl: { fontSize: 18, fontWeight: "800" },
  ret: { fontSize: 13, fontWeight: "700", marginTop: 2 },
  bottom: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, flexWrap: "wrap" },
});
