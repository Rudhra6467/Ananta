import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { colors, spacing, radius } from "../theme";

const STRAT_ICON: Record<string, any> = { hunter: "trending-up", squeeze: "flash", continuation: "pulse" };
const TONE: Record<string, { color: string; bg: string; border: string }> = {
  positive: { color: colors.teal, bg: colors.tealGlow, border: "rgba(20,224,201,0.4)" },
  warning: { color: colors.amber, bg: "rgba(242,169,59,0.12)", border: "rgba(242,169,59,0.4)" },
  negative: { color: colors.red, bg: colors.redGlow, border: "rgba(255,90,106,0.4)" },
};

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
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={styles.title}>Strategy Health</Text>
          {recommended.length > 0 && (
            <View style={styles.countBadge} testID="health-recommended-badge">
              <Text style={styles.countTxt}>{recommended.length}</Text>
            </View>
          )}
        </View>
        <Pressable testID="cockpit-view-health" onPress={() => router.push("/research?sub=health")} hitSlop={8} style={styles.viewBtn}>
          <Text style={styles.viewTxt}>View Health</Text>
          <Ionicons name="arrow-forward" size={12} color={colors.teal} />
        </Pressable>
      </View>

      {loading ? (
        <View style={{ paddingVertical: spacing.md, alignItems: "center" }} testID="health-card-loading">
          <ActivityIndicator color={colors.teal} />
        </View>
      ) : recommended.length === 0 ? (
        <Text style={styles.empty} testID="health-card-empty">
          No strategies currently recommended for paper trading.
        </Text>
      ) : (
        <>
          <Text style={styles.sub} testID="health-card-count">
            {recommended.length} {recommended.length === 1 ? "strategy" : "strategies"} recommended for paper trading.
          </Text>
          <View style={styles.row}>
            {recommended.map((s: any) => <HealthMini key={s.strategy} s={s} />)}
          </View>
        </>
      )}
    </View>
  );
}

function HealthMini({ s }: { s: any }) {
  const rec = s.recommendation || {};
  const tone = TONE[rec.tone] || TONE.warning;
  const pnl = Number(s.headline?.net_pnl ?? 0);
  return (
    <View style={styles.mini} testID={`health-card-${s.strategy}`}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={styles.miniIcon}>
          <Ionicons name={(STRAT_ICON[s.strategy] || "cube") as any} size={16} color={colors.teal} />
        </View>
        <Text style={styles.miniName} numberOfLines={1}>{s.name}</Text>
      </View>
      <View style={[styles.badge, { backgroundColor: tone.bg, borderColor: tone.border }]}>
        <Text style={[styles.badgeTxt, { color: tone.color }]} numberOfLines={2}>{rec.badge || "Recommended"}</Text>
      </View>
      <Text style={styles.pnl}>
        <Text style={{ color: pnl >= 0 ? colors.teal : colors.red, fontWeight: "800" }}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</Text>
        <Text style={{ color: colors.textFaint }}> P&L</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { color: colors.text, fontSize: 18, fontWeight: "700" },
  countBadge: { minWidth: 20, paddingHorizontal: 6, height: 18, borderRadius: 9, backgroundColor: "rgba(20,224,201,0.15)", borderWidth: 1, borderColor: "rgba(20,224,201,0.35)", alignItems: "center", justifyContent: "center" },
  countTxt: { color: colors.teal, fontSize: 10, fontWeight: "800" },
  viewBtn: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: "rgba(20,224,201,0.4)", borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 },
  viewTxt: { color: colors.teal, fontSize: 11, fontWeight: "700" },
  empty: { color: colors.textMuted, fontSize: 12, marginTop: spacing.sm },
  sub: { color: colors.textMuted, fontSize: 12, marginTop: spacing.sm, marginBottom: spacing.sm },
  row: { flexDirection: "row", gap: spacing.sm },
  mini: { flex: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.sm + 2, gap: spacing.sm },
  miniIcon: { width: 30, height: 30, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.cardBorder, backgroundColor: "rgba(20,224,201,0.05)", alignItems: "center", justifyContent: "center" },
  miniName: { color: colors.text, fontSize: 14, fontWeight: "700", flex: 1 },
  badge: { alignSelf: "flex-start", borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 3 },
  badgeTxt: { fontSize: 8, fontWeight: "800", letterSpacing: 0.4, textTransform: "uppercase" },
  pnl: { fontSize: 14 },
});
