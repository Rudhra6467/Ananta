import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Switch, ActivityIndicator, Linking, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Segmented } from "../../src/components/Segmented";
import { Pill } from "../../src/components/Pill";
import { PageHeader } from "../../src/components/PageHeader";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { signedUsd, base } from "../../src/format";

const PERIODS = [{ key: "1m", label: "1M" }, { key: "3m", label: "3M" }, { key: "6m", label: "6M" }, { key: "1y", label: "1Y" }];

export default function Research() {
  const insets = useSafeAreaInsets();
  const { isOwner } = useAuth();
  const params = useLocalSearchParams<{ sub?: string }>();
  const [sub, setSub] = useState<"validate" | "ai" | "closed">("validate");

  useEffect(() => {
    const s = params.sub;
    if (s === "validate" || s === "ai" || s === "closed") setSub(s);
  }, [params.sub]);

  return (
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
      <PageHeader title="Research Lab" question="Does my strategy actually work?" />
      <View style={{ marginBottom: spacing.md }}>
        <Segmented testIDPrefix="research-sub"
          options={[{ key: "validate", label: "VALIDATE" }, { key: "ai", label: "AI" }, { key: "closed", label: "CLOSED" }]}
          value={sub} onChange={(k) => setSub(k as any)} />
      </View>
      {sub === "validate" && <Validate isOwner={isOwner} />}
      {sub === "ai" && <Coach isOwner={isOwner} />}
      {sub === "closed" && <ClosedTrades isOwner={isOwner} />}
    </ScrollView>
  );
}

function Validate({ isOwner }: { isOwner: boolean }) {
  const [strategies, setStrategies] = useState<any[]>([]);
  const [strat, setStrat] = useState("hunter");
  const [period, setPeriod] = useState("1m");
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [result, setResult] = useState<any>(null);

  useEffect(() => { api.strategyRegistry().then((d) => { const l = d.strategies || []; setStrategies(l); if (l[0]) setStrat(l[0].key); }).catch(() => {}); }, []);

  const run = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setPhase("running"); setResult(null);
    try {
      const btc = "BTC/USD";
      const { id } = await api.labCreateRun({ kind: "backtest", symbols: [btc], period, strategies: [strat], exit_method: "fixed" });
      let done = false;
      for (let i = 0; i < 40 && !done; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const d = await api.labRun(id);
        if (d.status === "DONE") { setResult(d.result); done = true; }
        else if (d.status === "ERROR") throw new Error(d.error || "failed");
      }
      if (!done) throw new Error("timed out");
      setPhase("done");
    } catch (e: any) { setPhase("error"); Alert.alert("Backtest failed", e?.message); }
  };

  const per = result?.per_symbol || {};
  const rows = Object.entries(per).filter(([, m]: any) => !m.error);

  return (
    <View>
      <Card style={{ marginBottom: spacing.md }} testID="research-wizard">
        <SectionLabel>1 · STRATEGY</SectionLabel>
        <Segmented testIDPrefix="wiz-strat" options={strategies.map((s) => ({ key: s.key, label: s.name.split(" ")[0] }))} value={strat} onChange={setStrat} />
        <SectionLabel style={{ marginTop: spacing.md }}>2 · PERIOD (dataset: BTC)</SectionLabel>
        <Segmented testIDPrefix="wiz-period" options={PERIODS} value={period} onChange={setPeriod} />
        <Pressable testID="wizard-run" onPress={run} disabled={phase === "running"} style={styles.runBtn}>
          {phase === "running" ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="rocket" size={16} color={colors.bg} /><Text style={styles.runTxt}>RUN VALIDATION</Text></>}
        </Pressable>
      </Card>

      {phase === "running" && <Card style={{ alignItems: "center", paddingVertical: spacing.lg }}><ActivityIndicator color={colors.teal} /><Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>Running backtest…</Text></Card>}

      {phase === "done" && (
        <View testID="wizard-results">
          {rows.length === 0 ? <Card><Text style={type.bodyMuted}>No results.</Text></Card> : rows.map(([sym, m]: any) => (
            <Card key={sym} style={{ marginBottom: spacing.sm }}>
              <Text style={type.h3}>{base(sym)}</Text>
              <View style={styles.grid}>
                <Mini label="Return" value={`${(m.total_return_pct ?? 0).toFixed(1)}%`} color={(m.total_return_pct ?? 0) >= 0 ? colors.teal : colors.red} />
                <Mini label="Win Rate" value={`${(m.win_rate_pct ?? 0).toFixed(0)}%`} />
                <Mini label="Profit Factor" value={(m.profit_factor ?? 0).toFixed(2)} />
                <Mini label="Max DD" value={`${(m.max_drawdown_pct ?? 0).toFixed(1)}%`} color={colors.red} />
              </View>
            </Card>
          ))}
        </View>
      )}
    </View>
  );
}

function Coach({ isOwner }: { isOwner: boolean }) {
  const [aiOn, setAiOn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [review, setReview] = useState<any>(null);

  const generate = async () => {
    if (!isOwner || !aiOn) return;
    setLoading(true);
    try { setReview(await api.coachReview()); } catch (e: any) { Alert.alert("Coach unavailable", e?.message); } finally { setLoading(false); }
  };
  const apply = async () => {
    const rec = review?.recommendation; if (!rec?.applyable) return;
    try { await api.coachApply(rec.setting_key, rec.suggested_value); Alert.alert("Applied", `${rec.setting_key} → ${rec.suggested_value}`); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const rec = review?.recommendation;

  return (
    <Card testID="trading-coach">
      <View style={styles.rowBetween}>
        <SectionLabel>AI TRADING COACH</SectionLabel>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={[type.small, { fontSize: 10 }]}>USES CREDITS</Text>
          <Switch testID="coach-ai-switch" value={aiOn} onValueChange={setAiOn} disabled={!isOwner} trackColor={{ true: colors.tealDim, false: colors.cardBorder }} thumbColor={aiOn ? colors.teal : colors.textFaint} />
        </View>
      </View>
      {!review ? (
        <>
          <Text style={[type.small, { marginVertical: spacing.sm }]}>Get a 7-day performance review with one concrete, one-tap improvement.</Text>
          <Pressable testID="coach-generate-btn" onPress={generate} disabled={!aiOn || loading || !isOwner} style={[styles.runBtn, (!aiOn || !isOwner) && { opacity: 0.4 }]}>
            {loading ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="sparkles" size={16} color={colors.bg} /><Text style={styles.runTxt}>GENERATE WEEKLY REVIEW</Text></>}
          </Pressable>
        </>
      ) : (
        <View testID="coach-review">
          <Text style={[type.body, { marginVertical: spacing.sm }]}>{review.summary}</Text>
          <View style={styles.grid}>
            <Mini label="Best" value={review.best_strategy} color={colors.teal} />
            <Mini label="Worst" value={review.worst_strategy} color={colors.red} />
            <Mini label="Confidence" value={`${review.confidence}%`} color={colors.amber} />
          </View>
          {rec?.title && (
            <View style={styles.recBox} testID="coach-recommendation">
              <Text style={[type.h3, { fontSize: 15 }]}>{rec.title}</Text>
              <Text style={[type.small, { marginTop: 4 }]}>{rec.detail}</Text>
              {review.estimated_impact ? <Text style={[type.small, { color: colors.teal, marginTop: 4 }]}>Impact: {review.estimated_impact}</Text> : null}
              {rec.applyable && (
                <Pressable testID="coach-apply-btn" onPress={apply} style={[styles.runBtn, { marginTop: spacing.sm }]}>
                  <Ionicons name="flash" size={14} color={colors.bg} /><Text style={styles.runTxt}>APPLY: {rec.setting_key} → {rec.suggested_value}</Text>
                </Pressable>
              )}
            </View>
          )}
        </View>
      )}
    </Card>
  );
}

function ClosedTrades({ isOwner }: { isOwner: boolean }) {
  const [modal, setModal] = useState<string | null>(null);
  const [review, setReview] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const analyse = async (mode: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    setModal(mode); setReview(null); setLoading(true);
    try { setReview(await api.coachTradesReview(mode)); } catch (e: any) { setReview({ review: e?.message }); } finally { setLoading(false); }
  };

  return (
    <View testID="closed-trades-analysis">
      {["paper", "live"].map((mode) => (
        <Card key={mode} testID={`closed-${mode}-box`} style={{ marginBottom: spacing.md }}>
          <SectionLabel>{mode === "paper" ? "CLOSED PAPER TRADES" : "CLOSED LIVE TRADES"}</SectionLabel>
          <Pressable testID={`analyse-${mode}-btn`} onPress={() => analyse(mode)} disabled={!isOwner} style={[styles.runBtn, !isOwner && { opacity: 0.4 }]}>
            <Ionicons name="sparkles" size={14} color={colors.bg} /><Text style={styles.runTxt}>ANALYSE TRADES</Text>
          </Pressable>
          {modal === mode && (
            <View style={styles.recBox} testID="trades-report">
              {loading ? <ActivityIndicator color={colors.teal} /> : <Text style={type.body}>{review?.review}</Text>}
              <Pressable testID={`open-pdf-${mode}`} onPress={() => Linking.openURL(api.tradesPdfUrl(mode))} style={[styles.pdfBtn]}>
                <Ionicons name="open-outline" size={14} color={colors.teal} /><Text style={styles.pdfTxt}>OPEN PDF REPORT</Text>
              </Pressable>
            </View>
          )}
        </Card>
      ))}
    </View>
  );
}

function Mini({ label, value, color }: { label: string; value: string; color?: string }) {
  return <View style={{ minWidth: 70 }}><Text style={type.label}>{label}</Text><Text style={[type.h3, { fontSize: 15, color: color || colors.text, textTransform: "capitalize" }]}>{value || "—"}</Text></View>;
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  runBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: spacing.sm + 2, marginTop: spacing.md },
  runTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 12 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  recBox: { backgroundColor: colors.tealGlow, borderRadius: radius.md, borderWidth: 1, borderColor: colors.tealDim, padding: spacing.md, marginTop: spacing.sm },
  pdfBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: colors.tealDim, borderRadius: radius.sm, paddingVertical: spacing.sm, marginTop: spacing.sm },
  pdfTxt: { color: colors.teal, fontWeight: "700", fontSize: 11, letterSpacing: 0.6 },
});
