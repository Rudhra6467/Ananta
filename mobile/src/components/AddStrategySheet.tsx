import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView, ActivityIndicator, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { useAuth } from "../auth";
import { colors, spacing, type, radius } from "../theme";

const OPTIONS = [
  { key: "manual", icon: "construct", title: "Create New Strategy", desc: "Build rules step-by-step in the builder", route: "/library/import" },
  { key: "clone", icon: "copy", title: "Copy Existing", desc: "Duplicate a rule-based strategy, then tweak it", route: "" },
  { key: "import", icon: "cloud-upload", title: "Import JSON", desc: "Paste JSON, Pine Script, Freqtrade or Jesse", route: "/library/import" },
];

export function AddStrategySheet({ visible, onClose, onCloned }: { visible: boolean; onClose: () => void; onCloned?: () => void }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [mode, setMode] = useState<"menu" | "clone">("menu");
  const [lib, setLib] = useState<any[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => { if (!visible) { setMode("menu"); setBusy(null); } }, [visible]);
  useEffect(() => {
    if (mode === "clone" && lib === null) {
      api.libraryList({}).then((d: any) => setLib(d.strategies || [])).catch(() => setLib([]));
    }
  }, [mode, lib]);

  const go = (o: any) => {
    if (o.key === "clone") { setMode("clone"); return; }
    onClose();
    router.push(o.route as any);
  };

  const cloneable = (lib || []).filter((s: any) => s.wireable && !s.internal && !s.reference_only);

  const doClone = async (s: any) => {
    if (!isOwner) return Alert.alert("Owner login required");
    setBusy(s.id);
    try {
      const res = await api.libraryClone(s.id);
      onClose();
      onCloned?.();
      Alert.alert("Copied", `"${res?.strategy?.name || s.name}" added to your library. Open it to tune & deploy.`);
    } catch (e: any) {
      Alert.alert("Copy failed", e?.response?.data?.detail || e?.message || "Couldn't copy that strategy");
    } finally { setBusy(null); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.wrap}>
        <View style={[styles.panel, { paddingBottom: insets.bottom + spacing.lg }]}>
          <View style={styles.head}>
            {mode === "clone" ? (
              <Pressable testID="clone-back" onPress={() => setMode("menu")} hitSlop={10} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <Ionicons name="chevron-back" size={20} color={colors.teal} />
                <Text style={type.h2}>Copy a strategy</Text>
              </Pressable>
            ) : <Text style={type.h2}>Add Strategy</Text>}
            <Pressable testID="add-menu-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>

          {mode === "menu" ? (
            OPTIONS.map((o) => (
              <Pressable key={o.key} testID={`add-menu-${o.key}`} onPress={() => go(o)} style={[styles.row, o.key === "manual" && styles.rowPrimary]}>
                <View style={styles.iconBox}><Ionicons name={o.icon as any} size={20} color={colors.teal} /></View>
                <View style={{ flex: 1 }}>
                  <Text style={[type.body, { fontWeight: "700" }]}>{o.title}</Text>
                  <Text style={type.small}>{o.desc}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
              </Pressable>
            ))
          ) : (
            <ScrollView style={{ maxHeight: 380 }} contentContainerStyle={{ gap: spacing.sm }}>
              <Text style={[type.small, { marginBottom: 2 }]}>Pick a rule-based strategy to duplicate. Core engine strategies use built-in logic and can&apos;t be copied.</Text>
              {lib === null ? (
                <ActivityIndicator color={colors.teal} style={{ marginVertical: spacing.lg }} />
              ) : cloneable.length === 0 ? (
                <Text style={[type.small, { paddingVertical: spacing.md }]} testID="clone-empty">No rule-based strategies available to copy yet.</Text>
              ) : cloneable.map((s: any) => (
                <Pressable key={s.id} testID={`clone-option-${s.id}`} onPress={() => doClone(s)} disabled={!!busy} style={styles.row}>
                  <View style={styles.iconBox}><Ionicons name="copy-outline" size={18} color={colors.teal} /></View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={[type.body, { fontWeight: "700" }]} numberOfLines={1}>{s.name}</Text>
                    <Text style={type.small} numberOfLines={1}>{s.style || s.category || "Rule-based"}</Text>
                  </View>
                  {busy === s.id ? <ActivityIndicator size="small" color={colors.teal} /> : <Ionicons name="copy" size={16} color={colors.textFaint} />}
                </Pressable>
              ))}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  panel: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: spacing.sm },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md },
  rowPrimary: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  iconBox: { width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: colors.tealGlow, borderWidth: 1, borderColor: colors.tealDim },
});
