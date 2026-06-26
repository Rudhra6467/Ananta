import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { colors, radius, spacing } from "../theme";

export function Segmented({
  options,
  value,
  onChange,
  testIDPrefix = "seg",
}: {
  options: { key: string; label: string }[];
  value: string;
  onChange: (key: string) => void;
  testIDPrefix?: string;
}) {
  return (
    <View style={styles.wrap}>
      {options.map((o) => {
        const active = o.key === value;
        return (
          <Pressable
            key={o.key}
            testID={`${testIDPrefix}-${o.key}`}
            onPress={() => onChange(o.key)}
            style={[styles.item, active && styles.itemActive]}
          >
            <Text style={[styles.label, active && styles.labelActive]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    backgroundColor: colors.card,
    borderRadius: radius.pill,
    padding: 4,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  item: {
    flex: 1,
    alignItems: "center",
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.pill,
  },
  itemActive: { backgroundColor: colors.teal },
  label: { color: colors.textMuted, fontWeight: "700", fontSize: 13 },
  labelActive: { color: colors.bg },
});
