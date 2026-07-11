import React, { createContext, useCallback, useContext, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, TextInput, ActivityIndicator, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import api from "./api";
import { useAuth } from "./auth";
import { colors, spacing, type, radius } from "./theme";

type AccessGateCtx = { gate: (feature: string) => boolean; isOwner: boolean };
const Ctx = createContext<AccessGateCtx | null>(null);

/**
 * Mobile access gate (parity with web). Owner: gated actions proceed (returns true).
 * Public: surface UI stays visible, deeper actions open the Waitlist modal (returns false).
 * Auth-agnostic so we can swap in real accounts later without touching call sites.
 */
export function AccessGateProvider({ children }: { children: React.ReactNode }) {
  const { isOwner } = useAuth();
  const [feature, setFeature] = useState<string | null>(null);

  const gate = useCallback((featureLabel: string) => {
    if (isOwner) return true;
    setFeature(featureLabel || "this feature");
    return false;
  }, [isOwner]);

  return (
    <Ctx.Provider value={{ gate, isOwner }}>
      {children}
      <WaitlistModal feature={feature} onClose={() => setFeature(null)} />
    </Ctx.Provider>
  );
}

export function useAccessGate(): AccessGateCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAccessGate must be used within AccessGateProvider");
  return ctx;
}

function WaitlistModal({ feature, onClose }: { feature: string | null; onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    if (!name.trim() || !email.trim()) { Alert.alert("Missing info", "Please enter your name and email."); return; }
    setBusy(true);
    try {
      const r = await api.accessRequest({ name: name.trim(), email: email.trim(), feature, platform: "mobile" });
      setDone(true);
      if (r?.already_on_list) Alert.alert("Already on the list", "We'll be in touch soon!");
    } catch (e: any) {
      Alert.alert("Could not submit", e?.message || "Please try again.");
    } finally { setBusy(false); }
  };

  const close = () => { onClose(); setTimeout(() => { setName(""); setEmail(""); setDone(false); }, 200); };

  return (
    <Modal visible={!!feature} transparent animationType="fade" onRequestClose={close}>
      <Pressable style={styles.overlay} onPress={close}>
        <Pressable style={styles.sheet} onPress={() => {}}>
          <View style={styles.head}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name="lock-closed" size={16} color={colors.teal} />
              <Text style={type.h3}>Request early access</Text>
            </View>
            <Pressable testID="waitlist-close" onPress={close} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>

          {done ? (
            <View style={{ alignItems: "center", gap: 8, paddingVertical: spacing.md }}>
              <Ionicons name="sparkles" size={30} color={colors.teal} />
              <Text style={type.h3}>You&apos;re on the list</Text>
              <Text style={[type.body, { color: colors.textMuted, textAlign: "center" }]}>We&apos;ll notify you when access opens. Thanks!</Text>
              <Pressable testID="waitlist-done-btn" onPress={close} style={styles.btn}><Text style={styles.btnTxt}>Done</Text></Pressable>
            </View>
          ) : (
            <View style={{ gap: 10, marginTop: spacing.md }}>
              <Text style={[type.body, { color: colors.textMuted }]}>
                <Text style={{ color: colors.text }}>{feature}</Text> is part of the full Ananta experience. Join the waitlist and we&apos;ll notify you when access opens.
              </Text>
              <TextInput testID="waitlist-name" placeholder="Your name" placeholderTextColor={colors.textFaint}
                value={name} onChangeText={setName} style={styles.input} />
              <TextInput testID="waitlist-email" placeholder="you@email.com" placeholderTextColor={colors.textFaint}
                value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" style={styles.input} />
              <Pressable testID="waitlist-submit" onPress={submit} disabled={busy} style={[styles.btn, busy && { opacity: 0.5 }]}>
                {busy ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.btnTxt}>Join the waitlist</Text>}
              </Pressable>
            </View>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.overlay, padding: spacing.lg },
  sheet: { width: "100%", maxWidth: 380, backgroundColor: colors.card, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, padding: spacing.lg },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  input: { backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 12, color: colors.text, fontSize: 14 },
  btn: { backgroundColor: colors.teal, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center", marginTop: 4 },
  btnTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
});
