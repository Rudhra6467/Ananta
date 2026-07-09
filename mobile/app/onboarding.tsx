import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { setItem } from "../src/storage";
import { Logo } from "../src/components/Logo";
import { colors, spacing, type, radius } from "../src/theme";

const STEPS = [
  { icon: "person-add", label: "Create Account", detail: "Owner identity verified" },
  { icon: "link", label: "Connect Exchange", detail: "Kraken · CCXT" },
  { icon: "shield-checkmark", label: "API Verified", detail: "Read-only market access" },
  { icon: "wallet", label: "Import Portfolio", detail: "$1,200 paper book" },
  { icon: "git-branch", label: "Choose Strategy", detail: "Hunter · Squeeze · Continuation" },
  { icon: "flask", label: "Run Validation", detail: "Walk-Forward + Monte Carlo" },
  { icon: "sparkles", label: "AI Review", detail: "Strategy Architect sign-off" },
  { icon: "pulse", label: "Paper Trading", detail: "Live simulation engaged" },
  { icon: "rocket", label: "Ready For Live", detail: "Gate armed — you decide when" },
] as const;

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [active, setActive] = useState(-1);
  const [done, setDone] = useState(false);
  const timers = useRef<any[]>([]);

  useEffect(() => {
    STEPS.forEach((_, i) => timers.current.push(setTimeout(() => setActive(i), 400 + i * 550)));
    timers.current.push(setTimeout(() => { setActive(STEPS.length); setDone(true); }, 400 + STEPS.length * 550));
    return () => timers.current.forEach(clearTimeout);
  }, []);

  const finish = async () => {
    await setItem("ananta_onboarded", "1");
    router.replace("/(tabs)");
  };

  return (
    <View style={[styles.fill, { paddingTop: insets.top + spacing.lg }]}>
      <Pressable testID="onboarding-skip" onPress={finish} style={[styles.skip, { top: insets.top + spacing.sm }]}>
        <Text style={styles.skipTxt}>{done ? "CLOSE" : "SKIP"}</Text>
      </Pressable>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40 }}>
        <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
          <Logo size={44} />
          <Text style={[type.h1, { marginTop: spacing.sm }]}>Welcome to Ananta</Text>
          <Text style={[type.small, { marginTop: 4 }]}>Provisioning your trading operating system</Text>
        </View>

        {STEPS.map((s, i) => {
          const state = i < active ? "done" : i === active ? "run" : "idle";
          return (
            <View key={s.label} style={[styles.step, { opacity: state === "idle" ? 0.4 : 1 }]} testID={`onboarding-step-${i}`}>
              <View style={[styles.node, state !== "idle" && { borderColor: colors.teal }]}>
                <Ionicons name={(state === "done" ? "checkmark" : s.icon) as any} size={16} color={state === "idle" ? colors.textFaint : colors.teal} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[type.h3, { fontSize: 15, color: state === "idle" ? colors.textFaint : colors.text }]}>{s.label}</Text>
                <Text style={type.small}>{s.detail}</Text>
              </View>
              {state === "done" && <Text style={styles.badge}>DONE</Text>}
              {state === "run" && <Text style={[styles.badge, { color: colors.teal }]}>…</Text>}
            </View>
          );
        })}

        {done && (
          <View style={styles.finale} testID="onboarding-finale">
            <Ionicons name="rocket" size={28} color={colors.teal} />
            <Text style={[type.h2, { textAlign: "center", marginTop: spacing.sm }]}>Your trading OS is ready.</Text>
            <Text style={[type.small, { textAlign: "center", marginTop: 4 }]}>Estimated setup time: 4 minutes</Text>
            <Pressable testID="onboarding-enter" onPress={finish} style={styles.enter}>
              <Text style={styles.enterTxt}>ENTER ANANTA</Text>
            </Pressable>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  skip: { position: "absolute", right: spacing.md, zIndex: 10, padding: spacing.sm },
  skipTxt: { color: colors.textFaint, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  step: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  node: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center", backgroundColor: colors.card },
  badge: { color: colors.teal, fontSize: 9, fontWeight: "700", letterSpacing: 1 },
  finale: { marginTop: spacing.lg, alignItems: "center", backgroundColor: colors.tealGlow, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.teal, padding: spacing.lg },
  enter: { marginTop: spacing.md, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.xl },
  enterTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 1, fontSize: 13 },
});
