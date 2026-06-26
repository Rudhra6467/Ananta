import React from "react";
import { View, Text, StyleSheet, ViewStyle, Pressable } from "react-native";
import { colors, radius, spacing, type } from "../theme";

export function Card({
  children,
  style,
  onPress,
  testID,
}: {
  children: React.ReactNode;
  style?: ViewStyle | ViewStyle[];
  onPress?: () => void;
  testID?: string;
}) {
  if (onPress) {
    return (
      <Pressable
        testID={testID}
        onPress={onPress}
        style={({ pressed }) => [styles.card, pressed && styles.pressed, style as any]}
      >
        {children}
      </Pressable>
    );
  }
  return (
    <View testID={testID} style={[styles.card, style as any]}>
      {children}
    </View>
  );
}

export function SectionLabel({ children, style }: { children: React.ReactNode; style?: any }) {
  return <Text style={[type.label, { marginBottom: spacing.sm }, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: spacing.md,
  },
  pressed: {
    backgroundColor: colors.cardPressed,
    transform: [{ scale: 0.99 }],
  },
});
