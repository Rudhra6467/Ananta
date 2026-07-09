import React, { useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, radius, type } from "../theme";

type Band = { to: number; label: string; color: string };
type Metric = { title: string; desc: string; unit: string; bands: Band[] };

// Mirrors the web MetricExplainer bands so beginners learn inline.
const METRICS: Record<string, Metric> = {
  health: {
    title: "Strategy Health",
    desc: "A single 0–100 score = the average of six sub-metrics (win rate, risk, consistency, recent form, sample size, rating). One number to gauge overall quality.",
    unit: "",
    bands: [
      { to: 35, label: "At risk", color: colors.red },
      { to: 60, label: "Needs work", color: colors.amber },
      { to: 101, label: "Healthy", color: colors.teal },
    ],
  },
  win_rate: {
    title: "Win Rate",
    desc: "Percentage of closed trades that were profitable. High win rate alone doesn't guarantee profit — pair it with profit factor.",
    unit: "%",
    bands: [
      { to: 40, label: "Low", color: colors.red },
      { to: 55, label: "Fair", color: colors.amber },
      { to: 101, label: "Strong", color: colors.teal },
    ],
  },
  profit_factor: {
    title: "Profit Factor",
    desc: "How much your winners generate vs your losers (gross profit ÷ gross loss). Below 1.0 loses money; above 2.0 is excellent.",
    unit: "",
    bands: [
      { to: 1.0, label: "Losing", color: colors.red },
      { to: 1.5, label: "Marginal", color: colors.amber },
      { to: 999, label: "Good", color: colors.teal },
    ],
  },
  roi: {
    title: "Return on Investment",
    desc: "Net profit as a % of capital deployed by this strategy. Positive means the strategy is net profitable over its sample.",
    unit: "%",
    bands: [
      { to: 0, label: "Negative", color: colors.red },
      { to: 5, label: "Modest", color: colors.amber },
      { to: 999, label: "Strong", color: colors.teal },
    ],
  },
};

export function MetricExplainer({ metric, value, size = 15 }: { metric: string; value?: number; size?: number }) {
  const [open, setOpen] = useState(false);
  const m = METRICS[metric];
  if (!m) return null;

  const numeric = typeof value === "number" ? value : null;
  const band = numeric != null ? m.bands.find((b) => numeric < b.to) || m.bands[m.bands.length - 1] : null;

  return (
    <>
      <Pressable
        testID={`metric-explainer-${metric}`}
        onPress={() => setOpen(true)}
        hitSlop={12}
        style={{ paddingHorizontal: 2 }}
      >
        <Ionicons name="information-circle-outline" size={size} color={colors.textFaint} />
      </Pressable>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.overlay} onPress={() => setOpen(false)}>
          <Pressable style={styles.card} testID={`metric-explainer-card-${metric}`} onPress={() => {}}>
            <View style={styles.headerRow}>
              <Text style={styles.title}>{m.title}</Text>
              <Pressable onPress={() => setOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={20} color={colors.textMuted} />
              </Pressable>
            </View>
            <Text style={styles.desc}>{m.desc}</Text>
            <View style={styles.bands}>
              {m.bands.map((b, i) => {
                const prev = i === 0 ? null : m.bands[i - 1].to;
                const range = prev == null ? `< ${b.to}${m.unit}` : b.to >= 999 ? `≥ ${prev}${m.unit}` : `${prev}–${b.to}${m.unit}`;
                const active = band === b;
                return (
                  <View key={b.label} style={styles.bandRow}>
                    <Text style={[styles.bandLabel, { color: b.color, opacity: active ? 1 : 0.6, fontWeight: active ? "800" : "600" }]}>{b.label}</Text>
                    <Text style={[styles.bandRange, { color: b.color, opacity: active ? 1 : 0.6 }]}>{range}</Text>
                  </View>
                );
              })}
            </View>
            {numeric != null && band && (
              <View style={styles.yourValue}>
                <Text style={styles.yourValueTxt}>
                  Your value <Text style={{ color: band.color, fontWeight: "800" }}>{numeric}{m.unit} · {band.label}</Text>
                </Text>
              </View>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: spacing.lg },
  card: { backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder, padding: spacing.lg },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  title: { color: colors.text, fontSize: 16, fontWeight: "800" },
  desc: { color: colors.textMuted, fontSize: 13, lineHeight: 19, marginBottom: spacing.md },
  bands: { gap: 6 },
  bandRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  bandLabel: { fontSize: 12 },
  bandRange: { fontSize: 12, fontWeight: "600" },
  yourValue: { marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  yourValueTxt: { color: colors.textMuted, fontSize: 13 },
});
