import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing } from "../theme";
import { clockTime, base } from "../format";

export type ReasoningItem = {
  id: string;
  timestamp: string;
  symbol: string;
  bias?: string;
  confidence?: number;
  reason?: string;
  decision?: string;
};

function toneFor(item: ReasoningItem): { color: string } {
  const d = (item.decision || item.bias || "").toUpperCase();
  if (d.includes("BUY") || d.includes("BULL")) return { color: colors.teal };
  if (d.includes("SELL") || d.includes("BEAR") || d.includes("KILL")) return { color: colors.red };
  return { color: colors.textFaint };
}

// Narrative AI decision timeline — turns raw cycle logs into a glanceable feed.
export function AITimeline({ items, max = 8 }: { items: ReasoningItem[]; max?: number }) {
  const rows = (items || []).slice(0, max);
  if (rows.length === 0) {
    return <Text style={[styles.empty]}>No AI activity yet — the engine is warming up.</Text>;
  }
  return (
    <View>
      {rows.map((it, i) => {
        const t = toneFor(it);
        const isLast = i === rows.length - 1;
        return (
          <View key={it.id || i} style={styles.row} testID={`ai-timeline-${i}`}>
            <View style={styles.rail}>
              <View style={[styles.dot, { backgroundColor: t.color }]} />
              {!isLast && <View style={styles.line} />}
            </View>
            <View style={styles.content}>
              <View style={styles.head}>
                <Text style={styles.sym}>{base(it.symbol)}</Text>
                <Text style={styles.time}>{clockTime(it.timestamp)}</Text>
              </View>
              <Text style={styles.text} numberOfLines={2}>
                {it.reason || it.decision || "—"}
              </Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { color: colors.textMuted, fontSize: 14, paddingVertical: spacing.md },
  row: { flexDirection: "row" },
  rail: { width: 22, alignItems: "center" },
  dot: { width: 10, height: 10, borderRadius: 5, marginTop: 4 },
  line: { width: 2, flex: 1, backgroundColor: colors.cardBorder, marginVertical: 2 },
  content: { flex: 1, paddingBottom: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sym: { color: colors.text, fontWeight: "800", fontSize: 14, letterSpacing: 0.5 },
  time: { color: colors.textFaint, fontSize: 12, fontWeight: "600" },
  text: { color: colors.textMuted, fontSize: 13, marginTop: 2, lineHeight: 18 },
});
