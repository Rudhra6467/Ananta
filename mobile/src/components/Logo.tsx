import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../theme";

// Imperial-gold trident mark (branding only) + ANANTA wordmark.
export function Logo({ size = 26, showWord = true, color }: { size?: number; showWord?: boolean; color?: string }) {
  const stroke = color || colors.gold;
  return (
    <View style={styles.row}>
      <Svg width={size} height={size} viewBox="0 0 24 24">
        {/* central shaft */}
        <Path d="M12 3 L12 21" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
        {/* outer prongs */}
        <Path d="M6 4 L6 9 Q6 12 12 12 Q18 12 18 9 L18 4" stroke={stroke} strokeWidth={1.8} fill="none" strokeLinecap="round" />
        {/* prong tips */}
        <Path d="M6 4 L5 6 M6 4 L7 6 M18 4 L17 6 M18 4 L19 6 M12 3 L11 5 M12 3 L13 5" stroke={stroke} strokeWidth={1.6} strokeLinecap="round" />
        {/* base */}
        <Path d="M9 21 L15 21" stroke={stroke} strokeWidth={1.8} strokeLinecap="round" />
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
  ai: { color: colors.gold },
});
