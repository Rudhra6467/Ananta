import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Modal, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { useFetch } from "../../src/useFetch";
import { StrategyConfigSheet } from "../../src/components/StrategyConfigSheet";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { guideByKey } from "../../src/academy";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";

const STRATEGY_ICON: Record<string, any> = {
  hunter: "flame", squeeze: "contract", continuation: "trending-up",
  "ema-cross": "git-compare", "time-series-momentum": "pulse",
  "stochastic-momentum": "speedometer", supertrend: "trending-up",
  "donchian-breakout": "swap-vertical", "keltner-breakout": "resize",
  "atr-breakout": "flash", "rsi-momentum": "pulse", "macd-trend": "analytics",
  "bollinger-mr": "git-merge", "vwap-mr": "git-merge", turtle: "shield",
};

export default function StrategyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const key = id as string;
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const { data, loading, error, refresh } = useFetch(api.strategyMetrics, [], 0);

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  // Load the Strategy Profile → drives the Live/Off toggle (enabled flag).
  const loadProfile = () =>
    api.strategyProfile(key).then((d: any) => { setProfile(d.profile); setEnabled(d.profile?.enabled !== false); }).catch(() => {});
  useEffect(() => { if (key) loadProfile(); }, [key]);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const s = (data?.metrics || {})[key];
  if (!s) return <View style={styles.fill}><ErrorView message="Strategy not found" onRetry={refresh} /></View>;

  const guide = guideByKey(key);

  // Live/Off toggle → persist enabled flag on the profile (regimes/exit preserved).
  const setLive = async (live: boolean) => {
    if (!isOwner || saving || enabled === live) return;
    setEnabled(live); // optimistic
    setSaving(true);
    try {
      await api.strategyProfileSave(key, {
        enabled: live,
        allowed_regimes: profile?.allowed_regimes || [],
        exit_method: profile?.exit_method || "native",
        exit_params: profile?.exit_params || {},
      });
      await loadProfile();
    } catch {
      setEnabled(!live); // revert on failure
    } finally {
      setSaving(false);
    }
  };

  const pnlPct = s.roi;
  const metrics = [
    { label: "Win Rate", value: `${s.win_rate ?? 0}%`, tone: colors.text },
    { label: "Total P&L", value: `${pnlPct >= 0 ? "+" : ""}${pnlPct ?? 0}%`, tone: pnlColor(pnlPct ?? 0) },
    { label: "Max Drawdown", value: `${s.max_drawdown_pct ?? 0}%`, tone: colors.red },
    { label: "Profit Factor", value: s.profit_factor != null ? String(s.profit_factor) : "—", tone: colors.text },
  ];

  return (
    <View style={styles.fill}>
      {/* Top bar: back + name + Live/Off toggle */}
      <View style={[styles.topbar, { paddingTop: insets.top + 6 }]}>
        <Pressable testID="strategy-back" onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </Pressable>
        <Text style={styles.topName} numberOfLines={1}>{s.name}</Text>
        <LiveToggle live={enabled === true} disabled={!isOwner || saving} onChange={setLive} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.md, paddingBottom: insets.bottom + 96 }} showsVerticalScrollIndicator={false}>
        {/* Strategy hero card (no On/Off badge) */}
        <View style={styles.hero} testID="strategy-hero">
          <View style={styles.heroIcon}>
            <Ionicons name={STRATEGY_ICON[key] || "cube"} size={26} color={colors.teal} />
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.heroName}>{s.name}</Text>
            <Text style={styles.heroDesc} numberOfLines={2}>{guide.purpose}</Text>
          </View>
        </View>

        {/* Performance Metrics (2x2) */}
        <Text style={styles.section}>PERFORMANCE METRICS</Text>
        <View style={styles.grid}>
          {metrics.map((m) => (
            <View key={m.label} style={styles.metric} testID={`metric-${m.label.replace(/\s/g, "-").toLowerCase()}`}>
              <Text style={styles.metricLabel}>{m.label}</Text>
              <Text style={[styles.metricValue, { color: m.tone }]}>{m.value}</Text>
            </View>
          ))}
        </View>

        {/* How it Works */}
        <Text style={styles.section}>HOW IT WORKS</Text>
        <View style={styles.card}><Text style={styles.body}>{guide.how}</Text></View>

        {/* Best Used In */}
        <Text style={styles.section}>BEST USED IN</Text>
        <View style={styles.card}>
          <GuideRow icon="flag" label="Purpose" value={guide.purpose} />
          <GuideRow icon="checkmark-circle" label="Works Best" value={guide.worksBest} tone={colors.teal} />
          <GuideRow icon="close-circle" label="Avoid" value={guide.avoid} tone={colors.red} last />
        </View>
      </ScrollView>

      {/* Single primary action */}
      <View style={[styles.footer, { paddingBottom: insets.bottom + 10 }]}>
        <Pressable testID="edit-strategy-btn" onPress={() => setEditOpen(true)} style={styles.editBtn}>
          <Ionicons name="options-outline" size={18} color={colors.bg} />
          <Text style={styles.editTxt}>Edit Strategy</Text>
        </Pressable>
      </View>

      <StrategyConfigSheet
        visible={editOpen}
        onClose={() => setEditOpen(false)}
        strategyKey={key}
        strategyName={s.name}
        isOwner={isOwner}
        onSaved={() => { loadProfile(); refresh(); }}
      />
    </View>
  );
}

function LiveToggle({ live, disabled, onChange }: { live: boolean; disabled: boolean; onChange: (v: boolean) => void }) {
  const OPTS = [{ k: true, label: "Live" }, { k: false, label: "Off" }];
  return (
    <View style={[styles.toggle, disabled && { opacity: 0.6 }]} testID="strategy-live-toggle">
      {OPTS.map((o) => {
        const active = o.k === live;
        return (
          <Pressable key={String(o.k)} testID={`toggle-${o.label.toLowerCase()}`} onPress={() => onChange(o.k)} disabled={disabled}
            style={[styles.toggleOpt, active && (o.k ? styles.toggleLive : styles.toggleOff)]}>
            {active && o.k ? <View style={styles.liveDot} /> : null}
            <Text style={[styles.toggleTxt, active && { color: o.k ? colors.teal : colors.textMuted, fontWeight: "800" }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function GuideRow({ icon, label, value, tone, last }: { icon: any; label: string; value: string; tone?: string; last?: boolean }) {
  return (
    <View style={[styles.guideRow, !last && styles.guideRowBorder]}>
      <Ionicons name={icon} size={16} color={tone || colors.textMuted} style={{ marginTop: 2 }} />
      <View style={{ flex: 1 }}>
        <Text style={styles.guideLabel}>{label}</Text>
        <Text style={styles.guideValue}>{value}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  topbar: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.cardBorder, backgroundColor: colors.bg },
  backBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  topName: { flex: 1, color: colors.text, fontSize: 17, fontWeight: "800", letterSpacing: 0.2 },
  toggle: { flexDirection: "row", backgroundColor: colors.bgElevated, borderRadius: radius.pill, padding: 3, borderWidth: 1, borderColor: colors.cardBorder },
  toggleOpt: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 14, paddingVertical: 6, borderRadius: radius.pill },
  toggleLive: { backgroundColor: "rgba(45,212,191,0.14)", borderWidth: 1, borderColor: colors.teal },
  toggleOff: { backgroundColor: colors.card },
  toggleTxt: { color: colors.textFaint, fontSize: 13, fontWeight: "700" },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.teal },

  hero: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.lg },
  heroIcon: { width: 52, height: 52, borderRadius: radius.md, backgroundColor: "rgba(45,212,191,0.1)", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.tealDim },
  heroName: { color: colors.text, fontSize: 18, fontWeight: "800" },
  heroDesc: { color: colors.textMuted, fontSize: 13, marginTop: 3, lineHeight: 18 },

  section: { color: colors.textFaint, fontSize: 11, fontWeight: "800", letterSpacing: 1.2, marginBottom: spacing.sm, marginTop: 2 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  metric: { width: "48%", flexGrow: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md },
  metricLabel: { color: colors.textMuted, fontSize: 12, marginBottom: 6 },
  metricValue: { fontSize: 22, fontWeight: "800", letterSpacing: -0.5 },

  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.lg },
  body: { color: colors.textMuted, fontSize: 14, lineHeight: 21 },
  guideRow: { flexDirection: "row", gap: spacing.sm, paddingVertical: spacing.sm + 2 },
  guideRowBorder: { borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  guideLabel: { color: colors.textFaint, fontSize: 11, fontWeight: "700", letterSpacing: 0.5, textTransform: "uppercase" },
  guideValue: { color: colors.text, fontSize: 14, marginTop: 2, lineHeight: 19 },

  footer: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder, backgroundColor: colors.bg },
  editBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 15 },
  editTxt: { color: colors.bg, fontSize: 16, fontWeight: "800", letterSpacing: 0.3 },
});
