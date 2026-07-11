import React, { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, TextInput, ScrollView, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useSegments } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { useAuth } from "../auth";
import { useAccessGate } from "../access";
import { colors, spacing, type, radius } from "../theme";

const SUGGESTIONS: Record<string, string[]> = {
  cockpit: ["Today's performance", "Why were setups rejected?", "What's the market regime?", "Start paper trading"],
  trade: ["Explain this position", "Pause Hunter", "Add a strategy", "Why is a trade open?"],
  strategy: ["What's my best strategy?", "Explain Hunter", "Import or build a strategy"],
  research: ["How do I validate a strategy?", "Explain the AI score", "Why did this fail?"],
  workspace: ["Explain this page", "What does the exit engine do?", "Paper vs Live?", "Configure risk"],
};

type Msg = { role: "user" | "assistant"; text: string; actions?: any[] };

export function AskAnanta({ tab, routeName }: { tab: string; routeName: string }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const segments = useSegments();
  const { isOwner } = useAuth();
  const { gate } = useAccessGate();
  const [enabled, setEnabled] = useState(false);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const session = useRef<string | undefined>(undefined);

  useEffect(() => {
    const load = () => api.settings().then((s: any) => setEnabled(!!s?.ask_ananta_enabled)).catch(() => {});
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, []);

  // (tabs) screens stay mounted after first visit, so gate this fixed-position chip to
  // the tab it belongs to — otherwise it leaks onto Trade/Strategy/Research.
  const last = segments[segments.length - 1] as string | undefined;
  const activeRoute = !last || last === "(tabs)" ? "index" : last;
  if (activeRoute !== routeName) return null;

  // Public visitors see the copilot chip but opening it is gated to the waitlist.
  if (!isOwner) {
    return (
      <Pressable testID="ask-ananta-chip" onPress={() => gate("Ask Ananta AI Copilot")}
        style={[styles.chip, { bottom: insets.bottom + 78, backgroundColor: colors.teal }]}>
        <Ionicons name="sparkles" size={18} color={colors.bg} />
        <Text style={[styles.chipTxt, { color: colors.bg }]}>Ask Ananta</Text>
      </Pressable>
    );
  }

  const toggleEnabled = async () => {
    try {
      const s = await api.updateSettings({ ask_ananta_enabled: !enabled });
      const next = !!s?.ask_ananta_enabled;
      setEnabled(next);
      if (!next) setOpen(false);
    } catch (e: any) { Alert.alert("Toggle failed", e?.message || String(e)); }
  };

  const send = async (text: string) => {
    const question = (text || "").trim();
    if (!question) return;
    setMsgs((m) => [...m, { role: "user", text: question }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.anantaAsk(question, session.current, tab);
      session.current = r.session_id;
      setMsgs((m) => [...m, { role: "assistant", text: r.answer, actions: r.actions || [] }]);
    } catch (e: any) {
      setMsgs((m) => [...m, { role: "assistant", text: e?.message || "Ask Ananta is unavailable." }]);
    } finally { setBusy(false); }
  };

  const runAction = (a: any) => {
    Alert.alert("Confirm", a.label + "?", [
      { text: "Cancel", style: "cancel" },
      { text: "Confirm", onPress: async () => {
        try {
          if (a.type === "strategy_disable") { await api.strategyDisable(a.params.key); Alert.alert("Done", `${a.params.key} paused`); }
          else if (a.type === "strategy_enable") { await api.strategyDeploy(a.params.key); Alert.alert("Done", `${a.params.key} enabled`); }
          else if (a.type === "open_research") { setOpen(false); router.push("/(tabs)/research"); }
          else if (a.type === "open_wizard") { setOpen(false); router.push("/(tabs)"); }
          else if (a.type === "open_strategy_add") { setOpen(false); router.push("/(tabs)/strategy"); }
          else if (a.type === "open_workspace_setting") { setOpen(false); router.push("/(tabs)/workspace"); }
        } catch (e: any) { Alert.alert("Failed", e?.message); }
      } },
    ]);
  };

  return (
    <>
      <View testID="ask-ananta-chip"
        style={[styles.chip, { bottom: insets.bottom + 78, backgroundColor: enabled ? colors.teal : colors.bgElevated, borderWidth: enabled ? 0 : 1, borderColor: colors.cardBorder }]}>
        <Pressable testID="ask-ananta-open" onPress={() => enabled && setOpen(true)} disabled={!enabled}
          style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Ionicons name="sparkles" size={18} color={enabled ? colors.bg : colors.textMuted} />
          <Text style={[styles.chipTxt, { color: enabled ? colors.bg : colors.textMuted }]}>Ask Ananta</Text>
        </Pressable>
        <Pressable testID="ask-ananta-switch" onPress={toggleEnabled} hitSlop={8}
          accessibilityRole="switch" accessibilityState={{ checked: enabled }}
          style={[styles.track, { backgroundColor: enabled ? "rgba(0,0,0,0.5)" : colors.cardBorder }]}>
          <View style={[styles.thumb, { left: enabled ? 16 : 2 }]} />
        </Pressable>
      </View>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={styles.wrap} testID="ask-ananta-panel">
          <View style={[styles.panel, { paddingBottom: insets.bottom + spacing.md }]}>
            <View style={styles.head}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Ionicons name="sparkles" size={18} color={colors.teal} />
                <Text style={type.h3}>Ask Ananta</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 14 }}>
                <Pressable testID="ask-ananta-switch-panel" onPress={toggleEnabled} hitSlop={8}
                  accessibilityRole="switch" accessibilityState={{ checked: enabled }}
                  style={[styles.track, { backgroundColor: enabled ? colors.teal : colors.cardBorder }]}>
                  <View style={[styles.thumb, { left: enabled ? 16 : 2 }]} />
                </Pressable>
                <Pressable testID="ask-ananta-close" onPress={() => setOpen(false)} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
              </View>
            </View>

            <ScrollView style={{ maxHeight: 360 }} contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.sm }}>
              {msgs.length === 0 ? (
                <View style={{ gap: spacing.xs }}>
                  <Text style={[type.small, { marginBottom: 2 }]}>Suggested for this tab:</Text>
                  {(SUGGESTIONS[tab] || SUGGESTIONS.cockpit).map((s) => (
                    <Pressable key={s} testID={`ananta-suggest-${s.slice(0, 8)}`} onPress={() => send(s)} style={styles.suggest}>
                      <Text style={[type.body, { color: colors.teal }]}>{s}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : msgs.map((m, i) => (
                <View key={i} style={[styles.bubble, m.role === "user" ? styles.bubbleUser : styles.bubbleAI]}>
                  <Text style={[type.body, { color: m.role === "user" ? colors.bg : colors.text, lineHeight: 21 }]}>{m.text}</Text>
                  {(m.actions || []).length > 0 && (
                    <View style={{ marginTop: spacing.sm, gap: 6 }}>
                      {m.actions!.map((a: any, j: number) => (
                        <Pressable key={j} testID={`ananta-action-${a.type}`} onPress={() => runAction(a)} style={styles.actionBtn}>
                          <Ionicons name="flash" size={13} color={colors.teal} />
                          <Text style={{ color: colors.teal, fontWeight: "700", fontSize: 13 }}>{a.label}</Text>
                        </Pressable>
                      ))}
                    </View>
                  )}
                </View>
              ))}
              {busy && <ActivityIndicator color={colors.teal} style={{ marginTop: spacing.sm }} />}
            </ScrollView>

            <View style={styles.inputRow}>
              <TextInput testID="ask-ananta-input" value={q} onChangeText={setQ} placeholder="Ask about your trading system…"
                placeholderTextColor={colors.textFaint} style={styles.input} onSubmitEditing={() => send(q)} />
              <Pressable testID="ask-ananta-send" onPress={() => send(q)} disabled={busy} style={styles.sendBtn}>
                <Ionicons name="arrow-up" size={20} color={colors.bg} />
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  chip: { position: "absolute", left: spacing.md, flexDirection: "row", alignItems: "center", gap: 10, borderRadius: radius.pill, paddingLeft: spacing.md, paddingRight: 8, paddingVertical: 8, elevation: 5 },
  chipTxt: { fontWeight: "800", fontSize: 13 },
  track: { width: 32, height: 18, borderRadius: 9, justifyContent: "center" },
  thumb: { position: "absolute", top: 2, width: 14, height: 14, borderRadius: 7, backgroundColor: "#fff" },
  wrap: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  panel: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  suggest: { borderWidth: 1, borderColor: colors.tealDim, borderRadius: radius.sm, paddingVertical: 10, paddingHorizontal: spacing.md },
  bubble: { borderRadius: radius.md, padding: spacing.md, maxWidth: "92%" },
  bubbleUser: { backgroundColor: colors.teal, alignSelf: "flex-end" },
  bubbleAI: { backgroundColor: colors.bgElevated, alignSelf: "flex-start", borderWidth: 1, borderColor: colors.cardBorder },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.tealDim, borderRadius: radius.sm, paddingVertical: 8, paddingHorizontal: spacing.sm, backgroundColor: colors.tealGlow },
  inputRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  input: { flex: 1, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.pill, color: colors.text, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 15 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center" },
});
