import React from "react";
import { View, Text, StyleSheet, Pressable, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "../theme";

const OPTIONS = [
  { key: "import", icon: "cloud-upload", title: "Import Strategy", desc: "Paste JSON, Pine Script, Freqtrade or Jesse", route: "/library/import" },
  { key: "manual", icon: "construct", title: "Write Strategy", desc: "Build rules manually with the strategy builder", route: "/library/import" },
  { key: "ai", icon: "sparkles", title: "Describe & Build", desc: "Tell the AI Wizard what you want to trade", route: "/library/import" },
];

export function AddStrategySheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const go = (route: string) => { onClose(); router.push(route as any); };
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.wrap}>
        <View style={[styles.panel, { paddingBottom: insets.bottom + spacing.lg }]}>
          <View style={styles.head}>
            <Text style={type.h2}>Add Strategy</Text>
            <Pressable testID="add-menu-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          {OPTIONS.map((o) => (
            <Pressable key={o.key} testID={`add-menu-${o.key}`} onPress={() => go(o.route)} style={styles.row}>
              <View style={styles.iconBox}><Ionicons name={o.icon as any} size={20} color={colors.teal} /></View>
              <View style={{ flex: 1 }}>
                <Text style={[type.body, { fontWeight: "700" }]}>{o.title}</Text>
                <Text style={type.small}>{o.desc}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </Pressable>
          ))}
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
  iconBox: { width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: colors.tealGlow, borderWidth: 1, borderColor: colors.tealDim },
});
