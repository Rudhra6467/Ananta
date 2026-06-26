import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, spacing, radius } from "../theme";

// Signal attrition funnel: Detected -> Qualified -> Resolved as proportional bars.
export function FunnelBar({
  detected,
  qualified,
  resolved,
}: {
  detected: number;
  qualified: number;
  resolved: number;
}) {
  const max = Math.max(detected, 1);
  const stages = [
    { label: "Detected", value: detected, color: colors.tealDim },
    { label: "Qualified", value: qualified, color: colors.teal },
    { label: "Resolved", value: resolved, color: colors.gold },
  ];
  return (
    <View>
      {stages.map((st) => (
        <View key={st.label} style={styles.stage}>
          <Text style={styles.label}>{st.label}</Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.max(2, (st.value / max) * 100)}%`, backgroundColor: st.color }]} />
          </View>
          <Text style={styles.value}>{st.value}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  stage: { flexDirection: "row", alignItems: "center", marginVertical: 3 },
  label: { color: colors.textMuted, fontSize: 11, fontWeight: "700", width: 64 },
  track: { flex: 1, height: 8, backgroundColor: colors.bgElevated, borderRadius: radius.pill, overflow: "hidden", marginHorizontal: spacing.sm },
  fill: { height: 8, borderRadius: radius.pill },
  value: { color: colors.text, fontSize: 12, fontWeight: "800", width: 42, textAlign: "right" },
});
