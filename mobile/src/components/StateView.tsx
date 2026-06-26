import React from "react";
import { View, Text, ActivityIndicator, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type } from "../theme";

export function LoadingView({ label = "Loading…" }: { label?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.teal} size="large" />
      <Text style={[type.bodyMuted, { marginTop: spacing.md }]}>{label}</Text>
    </View>
  );
}

export function EmptyView({
  icon = "documents-outline",
  title,
  subtitle,
}: {
  icon?: any;
  title: string;
  subtitle?: string;
}) {
  return (
    <View style={styles.center}>
      <Ionicons name={icon} size={40} color={colors.textFaint} />
      <Text style={[type.h3, { marginTop: spacing.md, textAlign: "center" }]}>{title}</Text>
      {subtitle ? (
        <Text style={[type.bodyMuted, { marginTop: spacing.xs, textAlign: "center" }]}>{subtitle}</Text>
      ) : null}
    </View>
  );
}

export function ErrorView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.center}>
      <Ionicons name="warning-outline" size={40} color={colors.red} />
      <Text style={[type.h3, { marginTop: spacing.md, textAlign: "center" }]}>Something went wrong</Text>
      <Text style={[type.bodyMuted, { marginTop: spacing.xs, textAlign: "center" }]}>{message}</Text>
      {onRetry ? (
        <Pressable testID="retry-btn" onPress={onRetry} style={styles.retry}>
          <Text style={{ color: colors.teal, fontWeight: "700" }}>Retry</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
    minHeight: 240,
  },
  retry: {
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.teal,
  },
});
