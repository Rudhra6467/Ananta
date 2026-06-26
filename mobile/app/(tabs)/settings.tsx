import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  Switch,
  Pressable,
  Alert,
  Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { Segmented } from "../../src/components/Segmented";
import { LoadingView } from "../../src/components/StateView";
import { getItem, setItem } from "../../src/storage";
import { colors, spacing, type, radius } from "../../src/theme";

const NOTIF_KEY = "ananta_notif_prefs";
const NOTIF_OPTIONS = [
  { key: "trade_opened", label: "Trade opened" },
  { key: "trade_closed", label: "Trade closed" },
  { key: "stop_loss", label: "Stop-loss hit" },
  { key: "trailing_stop", label: "Trailing stop armed" },
  { key: "kill_switch", label: "Kill switch triggered" },
  { key: "system_offline", label: "System offline" },
];

export default function Settings() {
  const insets = useSafeAreaInsets();
  const { owner, logout, biometricEnabled, biometricAvailable, setBiometricEnabled } = useAuth();
  const { data, loading, refresh } = useFetch(api.settings, [], 0);
  const [saving, setSaving] = useState(false);
  const [notif, setNotif] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      const raw = await getItem(NOTIF_KEY);
      if (raw) setNotif(JSON.parse(raw));
      else setNotif(Object.fromEntries(NOTIF_OPTIONS.map((o) => [o.key, true])));
    })();
  }, []);

  const s = data || {};

  const patch = async (body: Record<string, any>) => {
    setSaving(true);
    try {
      await api.updateSettings(body);
      refresh();
    } catch (e: any) {
      Alert.alert("Update failed", e?.message || "Could not save setting");
    } finally {
      setSaving(false);
    }
  };

  const setEnv = async (mode: string) => {
    setSaving(true);
    try {
      await api.setEnvironment(mode);
      refresh();
    } catch (e: any) {
      Alert.alert("Mode change failed", e?.message || "Could not change environment");
    } finally {
      setSaving(false);
    }
  };

  const toggleNotif = async (key: string, v: boolean) => {
    const next = { ...notif, [key]: v };
    setNotif(next);
    await setItem(NOTIF_KEY, JSON.stringify(next));
  };

  const toggleBiometric = async (v: boolean) => {
    if (v && !biometricAvailable) {
      Alert.alert("Not available", "No fingerprint/Face ID is enrolled on this device.");
      return;
    }
    await setBiometricEnabled(v);
  };

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;

  return (
    <ScrollView
      style={styles.fill}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing.xxl }}
    >
      <View style={{ paddingHorizontal: spacing.lg }}>
        <Text style={type.h1}>Settings</Text>
        <Text style={[type.bodyMuted, { marginTop: 2 }]}>{owner?.email}</Text>
      </View>

      {/* Trading */}
      <Section title="Trading">
        <Text style={[type.label, { marginBottom: spacing.sm }]}>Environment</Text>
        <Segmented
          options={[{ key: "paper", label: "PAPER" }, { key: "live", label: "LIVE" }]}
          value={s.trading_mode === "LIVE" ? "live" : "paper"}
          onChange={setEnv}
          testIDPrefix="env"
        />
        <View style={{ height: spacing.md }} />
        <Row
          label="Manual kill switch"
          sub="Halt all new entries immediately"
          right={
            <Switch
              testID="kill-switch-toggle"
              value={!!s.manual_kill_switch}
              onValueChange={(v) => patch({ manual_kill_switch: v })}
              trackColor={{ true: colors.red, false: colors.cardBorder }}
              thumbColor="#fff"
              disabled={saving}
            />
          }
        />
      </Section>

      {/* Risk (read-only monitoring) */}
      <Section title="Risk">
        <ReadRow label="Per-trade lot" value={`$${s.normal_lot_usd ?? "—"}`} />
        <ReadRow label="Stop loss" value={`${s.stop_loss_pct ?? "—"}%`} />
        <ReadRow label="Max daily loss" value={`${s.max_daily_loss_pct ?? "—"}%`} />
        <ReadRow label="Max concurrent positions" value={`${s.max_concurrent_positions ?? "—"}`} />
        <ReadRow label="Trail distance" value={`${s.trail_distance_pct ?? "—"}%`} last />
        <Text style={styles.hint}>Edit risk parameters in the web research lab.</Text>
      </Section>

      {/* Strategies */}
      <Section title="Strategies">
        <StrategyRow id="hunter" name="Hunter — buys fear" mode="EXECUTE" />
        <StrategyRow id="vcp" name="Volatility Squeeze — buys expansion" mode={s.__squeeze_active ? "EXECUTE" : "SHADOW"} />
        <StrategyRow id="trend_rider" name="Relative Strength" mode="SHADOW" />
        <StrategyRow id="bear_breakdown" name="Bear Breakdown" mode="SHADOW" />
        <StrategyRow id="neutral_crab" name="Neutral Crab" mode="SHADOW" last />
      </Section>

      {/* Notifications */}
      <Section title="Notifications">
        {NOTIF_OPTIONS.map((o, i) => (
          <Row
            key={o.key}
            label={o.label}
            last={i === NOTIF_OPTIONS.length - 1}
            right={
              <Switch
                testID={`notif-${o.key}`}
                value={!!notif[o.key]}
                onValueChange={(v) => toggleNotif(o.key, v)}
                trackColor={{ true: colors.teal, false: colors.cardBorder }}
                thumbColor="#fff"
              />
            }
          />
        ))}
        <Text style={styles.hint}>Push alerts activate on a published build with Firebase configured.</Text>
      </Section>

      {/* Account */}
      <Section title="Account">
        <Row
          label="Biometric unlock"
          sub={biometricAvailable ? "Face ID / fingerprint" : "Not enrolled on this device"}
          right={
            <Switch
              testID="biometric-toggle"
              value={biometricEnabled}
              onValueChange={toggleBiometric}
              trackColor={{ true: colors.teal, false: colors.cardBorder }}
              thumbColor="#fff"
            />
          }
        />
        <Pressable testID="sign-out-btn" onPress={logout} style={styles.signOut}>
          <Ionicons name="log-out-outline" size={18} color={colors.red} />
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </Section>

      {/* Developer */}
      <Section title="Developer">
        <ReadRow label="Exchange" value={(s.trading_mode ? "kraken" : "—").toUpperCase()} />
        <ReadRow label="App version" value="1.0.0" />
        <ReadRow label="Platform" value={Platform.OS} last />
      </Section>
    </ScrollView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg }}>
      <SectionLabel>{title}</SectionLabel>
      <Card style={{ paddingVertical: spacing.xs }}>{children}</Card>
    </View>
  );
}

function Row({ label, sub, right, last }: { label: string; sub?: string; right: React.ReactNode; last?: boolean }) {
  return (
    <View style={[styles.row, !last && styles.divider]}>
      <View style={{ flex: 1, paddingRight: spacing.md }}>
        <Text style={styles.rowLabel}>{label}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      {right}
    </View>
  );
}

function ReadRow({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <View style={[styles.row, !last && styles.divider]}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

function StrategyRow({ id, name, mode, last }: { id: string; name: string; mode: string; last?: boolean }) {
  return (
    <View style={[styles.row, !last && styles.divider]} testID={`setting-strategy-${id}`}>
      <Text style={[styles.rowLabel, { flex: 1, paddingRight: spacing.sm }]} numberOfLines={1}>{name}</Text>
      <Pill label={mode === "EXECUTE" ? "ACTIVE" : "SHADOW"} tone={mode === "EXECUTE" ? "teal" : "muted"} dot={mode === "EXECUTE"} />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.md, paddingHorizontal: spacing.xs },
  divider: { borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  rowLabel: { color: colors.text, fontSize: 15, fontWeight: "600" },
  rowSub: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  rowValue: { color: colors.textMuted, fontSize: 15, fontWeight: "700" },
  hint: { color: colors.textFaint, fontSize: 12, marginTop: spacing.sm, paddingHorizontal: spacing.xs, fontStyle: "italic" },
  signOut: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: spacing.md, marginTop: spacing.xs },
  signOutText: { color: colors.red, fontWeight: "700", fontSize: 15 },
});
