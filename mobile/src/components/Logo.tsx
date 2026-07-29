import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Path, Circle } from "react-native-svg";
import { colors } from "../theme";

// Ananta emblem — the A-with-trident (trisul) mark, matching the web logo so the brand
// is identical across web + mobile. `color` drives the ring / tines / A; the upward chart
// arrow uses the cyan accent.
export function Logo({ size = 26, showWord = true, color }: { size?: number; showWord?: boolean; color?: string }) {
  const main = color || colors.text;
  const accent = colors.teal;
  return (
    <View style={styles.row}>
      <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
        {/* outer ring */}
        <Circle cx="32" cy="32" r="29" stroke={main} strokeOpacity={0.35} strokeWidth={2} />
        {/* trident tines (top) */}
        <Path d="M22 15v9M32 9v13M42 15v9" stroke={main} strokeOpacity={0.5} strokeWidth={2} strokeLinecap="round" />
        {/* central sharp A */}
        <Path d="M32 17 L45 47 H38.5 L36 41 H28 L25.5 47 H19 L32 17 Z" fill={main} />
        <Path d="M30 35 H34 L32 29 Z" fill={colors.bg} />
        {/* upward chart arrow through the base */}
        <Path d="M16 44 L26 38 L33 42 L48 30" stroke={accent} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        <Path d="M42 29 H48 V35" stroke={accent} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        {/* constellation nodes */}
        <Circle cx="16" cy="44" r="1.6" fill={accent} />
        <Circle cx="48" cy="30" r="1.6" fill={accent} />
      </Svg>
      {showWord && (
        <Text style={styles.word}>
          ANANTA<Text style={styles.ai}>.AI</Text>
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center" },
  word: { color: colors.text, fontSize: 18, fontWeight: "800", letterSpacing: 1.5, marginLeft: 8 },
  ai: { color: colors.teal },
});
