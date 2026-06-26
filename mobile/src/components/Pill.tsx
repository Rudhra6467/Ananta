import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { colors, radius, spacing } from "../theme";

type Tone = "teal" | "red" | "amber" | "muted" | "neutral";

const TONES: Record<Tone, { bg: string; fg: string }> = {
  teal: { bg: colors.tealGlow, fg: colors.teal },
  red: { bg: colors.redGlow, fg: colors.red },
  amber: { bg: "rgba(242,169,59,0.12)", fg: colors.amber },
  muted: { bg: "rgba(138,148,166,0.12)", fg: colors.textMuted },
  neutral: { bg: "rgba(255,255,255,0.06)", fg: colors.text },
};

export function Pill({
  label,
  tone = "muted",
  dot = false,
}: {
  label: string;
  tone?: Tone;
  dot?: boolean;
}) {
  const t = TONES[tone];
  return (
    <View style={[styles.pill, { backgroundColor: t.bg }]}>
      {dot && <View style={[styles.dot, { backgroundColor: t.fg }]} />}
      <Text style={[styles.text, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 5,
    borderRadius: radius.pill,
    alignSelf: "flex-start",
  },
  dot: { width: 7, height: 7, borderRadius: 4, marginRight: 6 },
  text: { fontSize: 12, fontWeight: "700", letterSpacing: 0.4 },
});
