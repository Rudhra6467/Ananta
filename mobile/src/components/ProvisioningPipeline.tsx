import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Modal, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { Logo } from "./Logo";
import { colors, spacing, radius } from "../theme";

type Step = { key: string; icon: any; label: string; subs: string[] };

const STEPS: Step[] = [
  { key: "account", icon: "link", label: "Account & Exchange", subs: ["Owner identity verified", "Kraken connected · API verified"] },
  { key: "portfolio", icon: "bulb", label: "Portfolio & Strategy", subs: ["Paper portfolio initialized", "Core strategies selected"] },
  { key: "validate", icon: "flask", label: "Validate & AI Review", subs: ["Walk-Forward + Monte Carlo", "Strategy Architect sign-off"] },
  { key: "live", icon: "rocket", label: "Go Live", subs: ["Paper trading engaged", "Live gate armed — you decide when"] },
];

/** Animated 4-step provisioning pipeline — mirrors the web OnboardingPipeline. */
export function ProvisioningPipeline({ visible, onDone }: { visible: boolean; onDone: () => void }) {
  const insets = useSafeAreaInsets();
  const [active, setActive] = useState(-1);
  const [done, setDone] = useState(false);
  const timers = useRef<any[]>([]);

  useEffect(() => {
    if (!visible) return;
    setActive(-1); setDone(false);
    timers.current.forEach(clearTimeout);
    timers.current = [];
    STEPS.forEach((_, i) => { timers.current.push(setTimeout(() => setActive(i), 400 + i * 750)); });
    timers.current.push(setTimeout(() => { setActive(STEPS.length); setDone(true); }, 400 + STEPS.length * 750));
    return () => timers.current.forEach(clearTimeout);
  }, [visible]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDone}>
      <View style={[styles.overlay, { paddingTop: insets.top + spacing.lg, paddingBottom: insets.bottom + spacing.lg }]} testID="provisioning-pipeline">
        <Pressable testID="provisioning-skip" onPress={onDone} style={styles.skip} hitSlop={10}>
          <Text style={styles.skipTxt}>{done ? "CLOSE" : "SKIP"}</Text>
          <Ionicons name="close" size={14} color={colors.textMuted} />
        </Pressable>

        <View style={styles.header}>
          <Logo size={44} showWord={false} color="#D2D6DC" />
          <Text style={styles.title}>Welcome to Ananta</Text>
          <Text style={styles.kicker}>PROVISIONING YOUR TRADING OPERATING SYSTEM</Text>
        </View>

        <View style={styles.pipeline}>
          <View style={styles.rail} />
          <View style={[styles.railFill, { height: `${Math.max(0, Math.min(1, (active + 1) / STEPS.length)) * 100}%` }]} />
          {STEPS.map((s, i) => {
            const state = i < active ? "done" : i === active ? "run" : "idle";
            return (
              <View key={s.key} style={[styles.step, { opacity: state === "idle" ? 0.4 : 1 }]} testID={`provisioning-step-${s.key}`}>
                <View style={[styles.node, state === "done" && styles.nodeDone, state === "run" && styles.nodeRun]}>
                  {state === "done" ? <Ionicons name="checkmark" size={15} color={colors.teal} />
                    : state === "run" ? <ActivityIndicator size="small" color={colors.teal} />
                    : <Ionicons name={s.icon} size={14} color={colors.textFaint} />}
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.stepHead}>
                    <Text style={[styles.stepLabel, state === "idle" && { color: colors.textMuted }]}>{s.label}</Text>
                    {state === "done" && <Text style={styles.badge}>DONE</Text>}
                    {state === "run" && <Text style={styles.badge}>RUNNING</Text>}
                  </View>
                  {s.subs.map((sub, j) => <Text key={j} style={styles.sub}>{sub}</Text>)}
                </View>
              </View>
            );
          })}
        </View>

        {done && (
          <View style={styles.finale} testID="provisioning-finale">
            <Ionicons name="sparkles" size={26} color={colors.teal} style={{ marginBottom: spacing.xs }} />
            <Text style={styles.finaleTitle}>Your trading operating system is ready.</Text>
            <Pressable testID="provisioning-enter" onPress={onDone} style={styles.enterBtn}>
              <Text style={styles.enterTxt}>ENTER ANANTA</Text>
            </Pressable>
          </View>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: "rgba(6,8,12,0.97)", paddingHorizontal: spacing.xl, justifyContent: "center" },
  skip: { position: "absolute", right: spacing.lg, top: spacing.xl, flexDirection: "row", alignItems: "center", gap: 4 },
  skipTxt: { color: colors.textMuted, fontSize: 10, fontWeight: "700", letterSpacing: 1.5 },
  header: { alignItems: "center", marginBottom: spacing.xl },
  title: { fontSize: 26, fontWeight: "300", color: colors.text, marginTop: spacing.sm },
  kicker: { color: colors.teal, fontSize: 9, letterSpacing: 1.5, fontWeight: "800", marginTop: 6, textAlign: "center" },
  pipeline: { paddingLeft: 34, position: "relative" },
  rail: { position: "absolute", left: 13, top: 6, bottom: 6, width: 1, backgroundColor: colors.cardBorder },
  railFill: { position: "absolute", left: 13, top: 6, width: 1, backgroundColor: colors.teal },
  step: { flexDirection: "row", gap: spacing.md, paddingBottom: spacing.lg, position: "relative" },
  node: { position: "absolute", left: -34, top: 0, width: 27, height: 27, borderRadius: 14, borderWidth: 1, borderColor: colors.cardBorder, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" },
  nodeDone: { borderColor: colors.tealDim },
  nodeRun: { borderColor: colors.teal },
  stepHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  stepLabel: { fontSize: 15, fontWeight: "700", color: colors.text, flexShrink: 1 },
  badge: { color: colors.teal, fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  sub: { color: colors.textFaint, fontSize: 11, marginTop: 2 },
  finale: { marginTop: spacing.lg, borderWidth: 1, borderColor: colors.tealDim, backgroundColor: colors.tealGlow, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center" },
  finaleTitle: { fontSize: 17, fontWeight: "700", color: colors.text, textAlign: "center" },
  enterBtn: { marginTop: spacing.md, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 14, alignItems: "center", alignSelf: "stretch" },
  enterTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 1.5, fontSize: 13 },
});
