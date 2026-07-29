import React from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "../src/theme";

type Row = { icon: keyof typeof Ionicons.glyphMap; label: string; desc?: string; pill?: string; route?: string };

const ROWS: Row[] = [
  { icon: "person-circle-outline", label: "Account", desc: "Profile · email · password", route: "/account" },
  { icon: "shield-checkmark-outline", label: "Security", desc: "Login & data protection", pill: "JWT" },
  { icon: "notifications-outline", label: "Notifications", pill: "Soon" },
  { icon: "options-outline", label: "Preferences", pill: "Soon" },
  { icon: "card-outline", label: "Payment methods", pill: "Soon" },
  { icon: "help-buoy-outline", label: "Support", desc: "Get help & contact us", pill: "Soon" },
];

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="settings-back" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>Settings</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl }}>
        <View style={styles.card} testID="settings-list">
          {ROWS.map((r, i) => (
            <Pressable
              key={r.label}
              testID={`settings-${r.label.toLowerCase().replace(/\s+/g, "-")}`}
              disabled={!r.route}
              onPress={() => r.route && router.push(r.route as any)}
              style={({ pressed }) => [styles.row, i < ROWS.length - 1 && styles.rowBorder, pressed && styles.rowPressed]}
            >
              <View style={styles.rowLeft}>
                <View style={styles.iconWrap}><Ionicons name={r.icon} size={18} color={colors.textMuted} /></View>
                <View style={{ flexShrink: 1 }}>
                  <Text style={styles.rowLabel}>{r.label}</Text>
                  {!!r.desc && <Text style={styles.rowDesc}>{r.desc}</Text>}
                </View>
              </View>
              <View style={styles.rowRight}>
                {!!r.pill && <View style={styles.pill}><Text style={styles.pillTxt}>{r.pill}</Text></View>}
                {!!r.route && <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />}
              </View>
            </Pressable>
          ))}
        </View>
        <Text style={styles.footer}>Ananta.AI · Settings</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderColor: colors.cardBorder },
  iconBtn: { width: 24, alignItems: "flex-start" },
  title: { ...type.h3 },
  card: { backgroundColor: colors.bgElevated, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingVertical: 16 },
  rowBorder: { borderBottomWidth: 1, borderColor: colors.cardBorder },
  rowPressed: { backgroundColor: colors.bg },
  rowLeft: { flexDirection: "row", alignItems: "center", gap: spacing.md, flexShrink: 1 },
  iconWrap: { width: 34, height: 34, borderRadius: 17, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center" },
  rowLabel: { ...type.body, color: colors.text },
  rowDesc: { color: colors.textFaint, fontSize: 11, fontFamily: "monospace", marginTop: 2 },
  rowRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  pill: { backgroundColor: colors.bg, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 3 },
  pillTxt: { color: colors.textFaint, fontSize: 10, fontWeight: "700" },
  footer: { color: colors.textFaint, fontSize: 10, fontFamily: "monospace", textAlign: "center", marginTop: spacing.lg },
});
