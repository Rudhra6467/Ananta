import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { useAuth } from "../auth";
import { colors, spacing, type, radius } from "../theme";

// Compact system health chip — a small pill that opens a bottom sheet with detail.
// Low-footprint by design so it never crowds the Cockpit.
export function SystemHealthChip() {
  const insets = useSafeAreaInsets();
  const { isOwner } = useAuth();
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState(false);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const d = await api.healthSelfcheck();
        if (active) { setData(d); setErr(false); }
      } catch {
        if (active) setErr(true);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { active = false; clearInterval(t); };
  }, []);

  const rows = [
    { key: "backend", label: "Backend API", ok: !err && !!data?.backend?.ok, note: err ? "Unreachable" : "Online" },
    { key: "database", label: "Database", ok: !!data?.database?.ok, note: data?.database?.latency_ms != null ? `${data.database.latency_ms} ms` : (data?.database?.ok ? "OK" : "Down") },
    { key: "market", label: "Market Data", ok: !!data?.market_data?.ok, note: data?.market_data?.freshest_age_s != null ? `${data.market_data.cached_symbols} feeds` : "No feed" },
    { key: "engine", label: "Trading Engine", ok: !!data?.engine?.running, note: data?.engine?.running ? "active" : "stopped" },
    { key: "session", label: "Session", ok: isOwner, note: isOwner ? "Owner" : "Read-only", neutral: !isOwner },
  ];
  const allOk = !err && !loading && rows.filter((r) => !r.neutral).every((r) => r.ok);
  const dotColor = loading ? colors.textFaint : err || !allOk ? colors.red : colors.teal;
  const label = loading ? "Checking…" : err ? "Systems degraded" : allOk ? "All systems OK" : "Attention needed";

  return (
    <>
      <Pressable testID="system-health-chip" onPress={() => setOpen(true)} style={styles.chip} hitSlop={6}>
        <View style={[styles.dot, { backgroundColor: dotColor }]} />
        <Ionicons name="pulse" size={13} color={colors.textMuted} />
        <Text style={styles.chipTxt}>{label}</Text>
        <Ionicons name="chevron-down" size={12} color={colors.textFaint} />
      </Pressable>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.overlay} onPress={() => setOpen(false)}>
          <Pressable style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]} onPress={() => {}}>
            <View style={styles.head}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Ionicons name="pulse" size={18} color={colors.teal} />
                <Text style={type.h3}>System Health</Text>
              </View>
              <Pressable testID="system-health-close" onPress={() => setOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.textMuted} />
              </Pressable>
            </View>
            <View style={{ gap: 8, marginTop: spacing.md }}>
              {rows.map((r) => (
                <View key={r.key} testID={`health-row-${r.key}`} style={styles.row}>
                  <Text style={[type.body, { color: colors.textMuted }]}>{r.label}</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Ionicons
                      name={r.neutral ? "remove-circle" : r.ok ? "checkmark-circle" : "close-circle"}
                      size={16}
                      color={r.neutral ? colors.textFaint : r.ok ? colors.teal : colors.red}
                    />
                    <Text style={{ fontSize: 12, color: r.neutral ? colors.textFaint : r.ok ? colors.teal : colors.red, fontWeight: "600" }}>{r.note}</Text>
                  </View>
                </View>
              ))}
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  chip: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-end", borderWidth: 1, borderColor: colors.cardBorder, backgroundColor: colors.bgElevated, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 5 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  chipTxt: { fontSize: 11, color: colors.textMuted, fontWeight: "600" },
  overlay: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  sheet: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingVertical: 10, paddingHorizontal: spacing.md },
});
