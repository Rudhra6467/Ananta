import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { colors, spacing, radius } from "../theme";

const STRAT_ICON: Record<string, any> = { hunter: "trending-up", squeeze: "trending-up", continuation: "trending-up" };

/** Cockpit "Strategy Health" card — top-2 recommended strategies from the daily sweep. */
export function StrategyHealthCard() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.labHealth()
      .then((d) => { if (alive) setData(d?.ready ? d : null); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const recommended = (data?.strategies || [])
    .filter((s: any) => s.recommendation?.tone === "positive")
    .sort((a: any, b: any) => (b.headline?.net_pnl ?? 0) - (a.headline?.net_pnl ?? 0))
    .slice(0, 2);

  return (
    <View style={styles.wrap} testID="strategy-health-card">
      <View style={styles.head}>
        <Text style={styles.title}>Strategy Health</Text>
        <Pressable testID="cockpit-view-health" onPress={() => router.push("/research?sub=health")} hitSlop={8} style={styles.viewBtn}>
          <Text style={styles.viewTxt}>View Health</Text>
          <Ionicons name="arrow-forward" size={12} color={colors.teal} />
        </Pressable>
      </View>

      {loading ? (
        <View style={{ paddingVertical: spacing.lg, alignItems: "center" }} testID="health-card-loading">
          <ActivityIndicator color={colors.teal} />
        </View>
      ) : recommended.length === 0 ? (
        <Text style={styles.empty} testID="health-card-empty">
          No strategies currently recommended for paper trading.
        </Text>
      ) : (
        <View style={styles.row}>
          {recommended.map((s: any) => <HealthMini key={s.strategy} s={s} />)}
        </View>
      )}
    </View>
  );
}

function HealthMini({ s }: { s: any }) {
  const rec = s.recommendation || {};
  const pnl = Number(s.headline?.net_pnl ?? 0);
  return (
    <View style={styles.mini} testID={`health-card-${s.strategy}`}>
      <View style={styles.miniIcon}>
        <Ionicons name={(STRAT_ICON[s.strategy] || "trending-up") as any} size={20} color={colors.bg} />
      </View>
      <Text style={styles.miniName} numberOfLines={2}>{s.name}</Text>
      <View style={styles.badge}>
        <Text style={styles.badgeTxt} numberOfLines={2}>{rec.badge || "Recommended for Paper Trading"}</Text>
      </View>
      <Text style={styles.pnl}>
        <Text style={{ color: pnl >= 0 ? colors.teal : colors.red, fontWeight: "800", fontSize: 26 }}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</Text>
        <Text style={{ color: colors.textFaint, fontSize: 11, fontWeight: "700" }}>  P&L</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md },
  title: { color: colors.text, fontSize: 20, fontWeight: "800" },
  viewBtn: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: "rgba(20,224,201,0.4)", borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6 },
  viewTxt: { color: colors.teal, fontSize: 12, fontWeight: "700" },
  empty: { color: colors.textMuted, fontSize: 13 },
  row: { flexDirection: "row", gap: spacing.sm },
  mini: { flex: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, minHeight: 168 },
  miniIcon: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center", marginBottom: spacing.sm },
  miniName: { color: colors.text, fontSize: 20, fontWeight: "800", lineHeight: 24 },
  badge: { alignSelf: "flex-start", backgroundColor: colors.green, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, marginTop: spacing.sm },
  badgeTxt: { color: colors.text, fontSize: 9, fontWeight: "800", letterSpacing: 0.4, textTransform: "uppercase" },
  pnl: { marginTop: spacing.md },
});
