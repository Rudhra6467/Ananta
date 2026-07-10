import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { colors, spacing, type, radius } from "../theme";
import { Segmented } from "./Segmented";

export function TradingWizard({ visible, onClose, onLaunched }: { visible: boolean; onClose: () => void; onLaunched?: () => void }) {
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState("paper");
  const [strategies, setStrategies] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [method, setMethod] = useState("paper");
  const [split, setSplit] = useState("7030");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (!visible) return;
    setStep(0); setSelected([]); setResult(null);
    api.strategyMetrics().then((d: any) => setStrategies(Object.values(d?.metrics || {}))).catch(() => {});
  }, [visible]);

  const toggle = (k: string) => setSelected((s) => s.includes(k) ? s.filter((x) => x !== k) : (s.length >= 3 ? s : [...s, k]));

  const runBacktest = async () => {
    setBusy(true); setResult(null);
    try {
      const days = split === "100" ? 60 : 30;
      const r = await api.backtestRun({ symbols: ["BTC/USD", "ETH/USD", "SOL/USD"], days, starting_balance: 1200 });
      setResult(r);
    } catch (e: any) { Alert.alert("Backtest failed", e?.message); } finally { setBusy(false); }
  };

  const launch = async () => {
    if (selected.length === 0) return Alert.alert("Pick at least one strategy");
    setBusy(true);
    try {
      await api.setEnvironment(mode.toUpperCase());
      for (const k of selected) await api.strategyDeploy(k);
      Alert.alert("Launched", `${selected.length} strateg${selected.length > 1 ? "ies" : "y"} armed in ${mode.toUpperCase()} mode.`);
      onLaunched && onLaunched();
      onClose();
    } catch (e: any) { Alert.alert("Launch failed", e?.message); } finally { setBusy(false); }
  };

  const next = () => {
    if (step === 1 && selected.length === 0) return Alert.alert("Pick 1-3 strategies");
    setStep((s) => Math.min(3, s + 1));
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.wrap}>
        <View style={[styles.panel, { paddingBottom: insets.bottom + spacing.md }]}>
          <View style={styles.head}>
            <Text style={type.h2}>Trading Wizard</Text>
            <Pressable testID="wizard-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          <View style={styles.dots}>
            {[0, 1, 2].map((i) => <View key={i} style={[styles.dot, step >= i && styles.dotOn]} />)}
          </View>

          <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ gap: spacing.md, paddingVertical: spacing.sm }}>
            {step === 0 && (
              <View style={{ gap: spacing.sm }}>
                <Text style={type.label}>EXECUTION MODE</Text>
                <Segmented testIDPrefix="wizard-mode" options={[{ key: "paper", label: "PAPER" }, { key: "live", label: "LIVE" }]} value={mode} onChange={setMode} />
                <Text style={type.small}>Paper simulates fills with no real capital. Live routes real orders once the exchange gate is armed.</Text>
              </View>
            )}
            {step === 1 && (
              <View style={{ gap: spacing.xs }}>
                <Text style={type.label}>PICK 1-3 STRATEGIES ({selected.length}/3)</Text>
                {strategies.map((s) => {
                  const on = selected.includes(s.key);
                  return (
                    <Pressable key={s.key} testID={`wizard-strategy-${s.key}`} onPress={() => toggle(s.key)} style={[styles.pick, on && styles.pickOn]}>
                      <View style={{ flex: 1 }}>
                        <Text style={[type.body, { fontWeight: "700" }]}>{s.name}</Text>
                        <Text style={type.small}>{s.trades} trades · WR {s.win_rate}% · health {s.health}</Text>
                      </View>
                      <Ionicons name={on ? "checkmark-circle" : "ellipse-outline"} size={22} color={on ? colors.teal : colors.textFaint} />
                    </Pressable>
                  );
                })}
              </View>
            )}
            {step === 2 && (
              <View style={{ gap: spacing.sm }}>
                <Text style={type.label}>VALIDATION METHOD</Text>
                <Segmented testIDPrefix="wizard-method" options={[{ key: "paper", label: "PAPER FORWARD" }, { key: "backtest", label: "BACKTEST" }]} value={method} onChange={setMethod} />
                {method === "backtest" && (
                  <>
                    <Segmented testIDPrefix="wizard-split" options={[{ key: "7030", label: "70/30 SPLIT" }, { key: "100", label: "100% HIST" }]} value={split} onChange={setSplit} />
                    <Pressable testID="wizard-run-backtest" onPress={runBacktest} disabled={busy} style={styles.ghost}>
                      {busy ? <ActivityIndicator color={colors.teal} /> : <Text style={{ color: colors.teal, fontWeight: "700" }}>Run backtest preview</Text>}
                    </Pressable>
                    {result && (
                      <View style={styles.resultCard}>
                        <Text style={type.small}>Net P&L: <Text style={{ color: colors.teal, fontWeight: "800" }}>${(result?.total_pnl ?? result?.net_pnl ?? 0).toFixed?.(2) ?? "—"}</Text></Text>
                        <Text style={type.small}>Trades: {result?.total_trades ?? result?.trades ?? "—"} · Win rate: {result?.win_rate ?? "—"}%</Text>
                      </View>
                    )}
                  </>
                )}
                {method === "paper" && <Text style={type.small}>Arms your selected strategies in a live paper simulation immediately.</Text>}
              </View>
            )}
          </ScrollView>

          <View style={styles.footer}>
            {step > 0 && <Pressable testID="wizard-back" onPress={() => setStep((s) => s - 1)} style={[styles.btn, styles.btnGhost]}><Text style={styles.btnGhostTxt}>Back</Text></Pressable>}
            {step < 2 ? (
              <Pressable testID="wizard-next" onPress={next} style={[styles.btn, styles.btnPrimary]}><Text style={styles.btnPrimaryTxt}>Next</Text></Pressable>
            ) : (
              <Pressable testID="wizard-launch" onPress={launch} disabled={busy} style={[styles.btn, styles.btnPrimary]}>
                {busy ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.btnPrimaryTxt}>Launch</Text>}
              </Pressable>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  panel: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  head: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  dots: { flexDirection: "row", gap: 6, marginTop: spacing.sm },
  dot: { width: 24, height: 4, borderRadius: 2, backgroundColor: colors.cardBorder },
  dotOn: { backgroundColor: colors.teal },
  pick: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md },
  pickOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  ghost: { alignItems: "center", borderWidth: 1, borderColor: colors.tealDim, borderRadius: radius.sm, paddingVertical: 11 },
  resultCard: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, padding: spacing.md, gap: 4 },
  footer: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  btn: { flex: 1, alignItems: "center", justifyContent: "center", paddingVertical: 13, borderRadius: radius.md },
  btnPrimary: { backgroundColor: colors.teal },
  btnPrimaryTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
  btnGhost: { borderWidth: 1, borderColor: colors.cardBorder },
  btnGhostTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 14 },
});
