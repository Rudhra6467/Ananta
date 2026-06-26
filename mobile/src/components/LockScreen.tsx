import React, { useEffect } from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../auth";
import { Logo } from "./Logo";
import { colors, spacing, type, radius } from "../theme";

// Full-screen biometric lock overlay for returning owner sessions.
export function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const { authenticateBiometric, logout } = useAuth();

  const attempt = async () => {
    const ok = await authenticateBiometric();
    if (ok) onUnlock();
  };

  useEffect(() => {
    attempt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={styles.overlay}>
      <Logo size={40} showWord={false} />
      <Text style={[type.h2, { marginTop: spacing.lg }]}>Locked</Text>
      <Text style={[type.bodyMuted, { marginTop: spacing.xs, textAlign: "center" }]}>
        Unlock Ananta to access your cockpit
      </Text>
      <Pressable testID="biometric-unlock-btn" onPress={attempt} style={styles.unlock}>
        <Ionicons name="finger-print" size={22} color={colors.bg} />
        <Text style={styles.unlockText}>Unlock</Text>
      </Pressable>
      <Pressable testID="lock-logout-btn" onPress={logout} style={{ marginTop: spacing.lg }}>
        <Text style={{ color: colors.textMuted, fontWeight: "600" }}>Sign out instead</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  unlock: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    marginTop: spacing.xl,
  },
  unlockText: { color: colors.bg, fontWeight: "800", fontSize: 16 },
});
