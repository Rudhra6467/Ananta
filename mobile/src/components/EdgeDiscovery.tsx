import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { Card, SectionLabel } from "./Card";
import { colors, spacing, pnlColor } from "../theme";
import { pct } from "../format";

const GRADE_TONE: Record<string, string> = {
  "A+": colors.teal,
  A: colors.teal,
  B: colors.amber,
  C: colors.red,
};

// "Edge Discovery" — does entry-quality grade predict outcome? (Phase E2)
export function EdgeDiscovery({ data }: { data: any }) {
  const total = data?.total_graded ?? 0;
  const grades: Record<string, any> = data?.grade_distribution || {};
  const order = ["A+", "A", "B", "C"].filter((g) => grades[g]);

  return (
    <View style={{ marginBottom: spacing.sm }}>
      <SectionLabel>Edge Discovery</SectionLabel>
      <Card testID="edge-discovery-card">
        {total === 0 ? (
          <Text style={styles.empty}>
            Accumulating graded trades. Once Hunter & Squeeze close positions, you'll see whether
            A-grade setups actually beat B-grade — straight from your own data.
          </Text>
        ) : (
          <>
            <Text style={styles.caption}>
              Win rate by entry grade · {total} graded trade{total === 1 ? "" : "s"}
            </Text>
            {order.map((g) => {
              const row = grades[g];
              const tone = GRADE_TONE[g] || colors.textMuted;
              return (
                <View key={g} style={styles.row} testID={`edge-grade-${g}`}>
                  <View style={[styles.gradeBadge, { borderColor: tone }]}>
                    <Text style={[styles.gradeText, { color: tone }]}>{g}</Text>
                  </View>
                  <View style={styles.barTrack}>
                    <View style={[styles.barFill, { width: `${Math.max(3, row.win_rate_pct)}%`, backgroundColor: tone }]} />
                  </View>
                  <Text style={styles.winRate}>{row.win_rate_pct}%</Text>
                  <Text style={[styles.avgRet, { color: pnlColor(row.avg_return_pct) }]}>{pct(row.avg_return_pct)}</Text>
                </View>
              );
            })}
            <Text style={styles.legend}>grade · win rate · avg return</Text>
          </>
        )}
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { color: colors.textMuted, fontSize: 13, lineHeight: 19 },
  caption: { color: colors.textMuted, fontSize: 12, marginBottom: spacing.sm, fontWeight: "600" },
  row: { flexDirection: "row", alignItems: "center", marginVertical: 4 },
  gradeBadge: { width: 34, height: 26, borderRadius: 8, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  gradeText: { fontSize: 13, fontWeight: "800" },
  barTrack: { flex: 1, height: 8, backgroundColor: colors.bgElevated, borderRadius: 999, marginHorizontal: spacing.sm, overflow: "hidden" },
  barFill: { height: 8, borderRadius: 999 },
  winRate: { color: colors.text, fontSize: 13, fontWeight: "800", width: 44, textAlign: "right" },
  avgRet: { fontSize: 12, fontWeight: "700", width: 60, textAlign: "right" },
  legend: { color: colors.textFaint, fontSize: 11, marginTop: spacing.sm, fontStyle: "italic" },
});
