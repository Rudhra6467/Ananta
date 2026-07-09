import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Circle } from "react-native-svg";
import { colors } from "../theme";

const healthColor = (v: number) => (v >= 60 ? colors.teal : v >= 35 ? colors.amber : colors.red);
const healthLabel = (v: number) => (v >= 60 ? "Healthy" : v >= 35 ? "Needs work" : "At risk");

/** Radial health gauge — mirrors the web Strategy Health ring. */
export function HealthRing({ score = 0, size = 112, stroke = 9 }: { score?: number; size?: number; stroke?: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (clamped / 100) * c;
  const color = healthColor(clamped);
  const center = size / 2;

  return (
    <View style={{ alignItems: "center" }} testID="health-ring">
      <View style={{ width: size, height: size }}>
        <Svg width={size} height={size}>
          <Circle cx={center} cy={center} r={r} fill="none" stroke={colors.cardBorder} strokeWidth={stroke} />
          <Circle
            cx={center}
            cy={center}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
            transform={`rotate(-90 ${center} ${center})`}
          />
        </Svg>
        <View style={[StyleSheet.absoluteFill, { alignItems: "center", justifyContent: "center" }]}>
          <Text testID="health-score-value" style={[styles.score, { color }]}>{clamped}</Text>
        </View>
      </View>
      <Text style={[styles.band, { color }]}>{healthLabel(clamped)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  score: { fontSize: 34, fontWeight: "800", letterSpacing: -1 },
  band: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4, marginTop: 6 },
});
