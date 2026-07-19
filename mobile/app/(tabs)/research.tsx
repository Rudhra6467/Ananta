import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Switch, ActivityIndicator, Linking, Alert, useWindowDimensions } from "react-native";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams } from "expo-router";
import { TabView, TabBar } from "react-native-tab-view";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Segmented } from "../../src/components/Segmented";
import { PageHeader } from "../../src/components/PageHeader";
import { colors, spacing, type, radius } from "../../src/theme";
import { base } from "../../src/format";

const PERIODS = [{ key: "1m", label: "1M" }, { key: "3m", label: "3M" }, { key: "6m", label: "6M" }, { key: "1y", label: "1Y" }];
const ROUTES = [
  { key: "validate", title: "Validate" },
  { key: "health", title: "Health" },
  { key: "ai", title: "AI Analysis" },
  { key: "closed", title: "Closed Trades" },
  { key: "reports", title: "Reports" },
  { key: "optimize", title: "Optimization" },
];

export default function Research() {
  const insets = useSafeAreaInsets();
  const layout = useWindowDimensions();
  const { isOwner } = useAuth();
  const params = useLocalSearchParams<{ sub?: string }>();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const i = ROUTES.findIndex((r) => r.key === params.sub);
    if (i >= 0) setIndex(i);
  }, [params.sub]);

  const renderScene = ({ route }: { route: { key: string } }) => {
    const pad = { padding: spacing.md, paddingBottom: insets.bottom + 100 };
    switch (route.key) {
      case "validate": return <ScrollView contentContainerStyle={pad}><Validate isOwner={isOwner} /></ScrollView>;
      case "health": return <ScrollView contentContainerStyle={pad}><Health isOwner={isOwner} /></ScrollView>;
      case "ai": return <ScrollView contentContainerStyle={pad}><Coach isOwner={isOwner} /></ScrollView>;
      case "closed": return <ScrollView contentContainerStyle={pad}><ClosedTrades isOwner={isOwner} /></ScrollView>;
      case "reports": return <ScrollView contentContainerStyle={pad}><Reports /></ScrollView>;
      case "optimize": return <ScrollView contentContainerStyle={pad}><Optimization isOwner={isOwner} /></ScrollView>;
      default: return null;
    }
  };

  return (
    <View style={styles.fill}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.md }}>
        <PageHeader title="Research Lab" question="Does my strategy actually work?" />
      </View>
      <TabView
        navigationState={{ index, routes: ROUTES }}
        renderScene={renderScene}
        onIndexChange={setIndex}
        initialLayout={{ width: layout.width }}
        lazy
        swipeEnabled
        renderTabBar={(props) => (
          <TabBar
            {...props}
            scrollEnabled
            options={{
              validate: { testID: "research-tab-validate" },
              health: { testID: "research-tab-health" },
              ai: { testID: "research-tab-ai" },
              closed: { testID: "research-tab-closed" },
              reports: { testID: "research-tab-reports" },
              optimize: { testID: "research-tab-optimize" },
            }}
            commonOptions={{ labelStyle: styles.tabLabel }}
            style={styles.tabBar}
            indicatorStyle={styles.indicator}
            tabStyle={{ width: "auto", paddingHorizontal: spacing.md }}
            activeColor={colors.teal}
            inactiveColor={colors.textMuted}
            pressColor={colors.tealGlow}
          />
        )}
      />
    </View>
  );
}

const EXIT_LABELS: Record<string, string> = { atr: "ATR Trailing", fixed: "Fixed Target" };

function Validate({ isOwner }: { isOwner: boolean }) {
  const [strategies, setStrategies] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<Record<string, any>>({});
  const [strat, setStrat] = useState("");
  const [period, setPeriod] = useState("1m");
  const [exitMethods, setExitMethods] = useState<string[]>(["atr"]);
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [runs, setRuns] = useState<{ method: string; label: string; result: any }[]>([]);

  useEffect(() => {
    api.strategyRegistry().then((d) => { setStrategies(d.strategies || []); }).catch(() => {});
    api.strategyMetrics().then((d: any) => setMetrics(d?.metrics || {})).catch(() => {});
  }, []);

  // Pre-select a strategy when arriving from a strategy detail's "Test this strategy".
  const params = useLocalSearchParams<{ strat?: string }>();
  useEffect(() => { if (params?.strat) setStrat(String(params.strat)); }, [params?.strat]);
  const selMetric = metrics[strat];
  const selOn = !!selMetric?.enabled && selMetric?.status !== "DISABLED" && selMetric?.status !== "ERROR";

  // At least one exit method must stay selected; default falls back to ATR.
  const toggleExit = (m: string) => setExitMethods((prev) => {
    const next = prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m];
    return next.length === 0 ? ["atr"] : next;
  });

  const pollRun = async (id: string) => {
    for (let i = 0; i < 200; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const d = await api.labRun(id);
      if (d.status === "DONE") return d.result;
      if (d.status === "ERROR" || d.status === "FAILED") throw new Error(d.error || "failed");
    }
    throw new Error("timed out");
  };

  const run = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    if (!strat) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      return Alert.alert("Select a strategy", "Pick an engine to research.");
    }
    const methods = exitMethods.length ? exitMethods : ["atr"];
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setPhase("running"); setRuns([]);
    try {
      const collected: { method: string; label: string; result: any }[] = [];
      for (const method of methods) {
        const { id } = await api.labCreateRun({ kind: "backtest", symbols: ["BTC/USD"], period, strategies: [strat], exit_method: method });
        const result = await pollRun(id);
        collected.push({ method, label: EXIT_LABELS[method] || method, result });
        setRuns([...collected]);
      }
      setPhase("done");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      Alert.alert("Research complete", "Your validation results are ready below.");
    } catch (e: any) { setPhase("error"); Alert.alert("Backtest failed", e?.message); }
  };

  return (
    <View>
      <Card style={{ marginBottom: spacing.md }} testID="research-wizard">
        <SectionLabel>1 · STRATEGY</SectionLabel>
        <View style={styles.chipWrap} testID="wiz-strat-grid">
          {strategies.map((s) => {
            const on = strat === s.key;
            return (
              <Pressable key={s.key} testID={`wiz-strat-${s.key}`} onPress={() => setStrat(s.key)}
                style={[styles.chip, on && styles.chipOn]}>
                <Text style={[styles.chipTxt, on && styles.chipTxtOn]} numberOfLines={1}>{s.name}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.statusLine} testID="research-strat-status">
          <View style={[styles.statusDot, { backgroundColor: selOn ? colors.teal : colors.textFaint }]} />
          <Text style={type.small}>Bot Status: <Text style={{ color: selOn ? colors.teal : colors.textMuted, fontWeight: "700" }}>{selOn ? "ON · live on engine" : "OFF"}</Text></Text>
        </View>
        <SectionLabel style={{ marginTop: spacing.md }}>2 · PERIOD (dataset: BTC)</SectionLabel>
        <Segmented testIDPrefix="wiz-period" options={PERIODS} value={period} onChange={setPeriod} />
        <SectionLabel style={{ marginTop: spacing.md }}>3 · EXIT STRATEGY</SectionLabel>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {[{ k: "atr", t: "ATR Trailing", d: "Volatility-adaptive (default)" }, { k: "fixed", t: "Fixed Target", d: "Fixed $ target / stop" }].map((em) => {
            const on = exitMethods.includes(em.k);
            return (
              <Pressable key={em.k} testID={`wiz-exit-${em.k}`} onPress={() => toggleExit(em.k)}
                style={[styles.exitCard, on && styles.exitCardOn]}>
                <View style={[styles.check, on && styles.checkOn]}>{on && <Ionicons name="checkmark" size={12} color={colors.bg} />}</View>
                <Text style={[type.body, { fontWeight: "700", fontSize: 13 }]}>{em.t}</Text>
                <Text style={[type.small, { fontSize: 10, marginTop: 2 }]}>{em.d}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={[type.small, { fontSize: 10, marginTop: 6 }]}>{exitMethods.length === 2 ? "Both selected — each exit is run & reported separately." : "Tick both to compare exits side-by-side."}</Text>
        <Pressable testID="wizard-run" onPress={run} disabled={phase === "running"} style={styles.runBtn}>
          {phase === "running" ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="rocket" size={16} color={colors.bg} /><Text style={styles.runTxt}>RUN VALIDATION</Text></>}
        </Pressable>
      </Card>
      {phase === "running" && <Card style={{ alignItems: "center", paddingVertical: spacing.lg }}><ActivityIndicator color={colors.teal} /><Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>Running backtest…</Text></Card>}
      {phase === "done" && (
        <View testID="wizard-results">
          {runs.length === 0 ? <Card><Text style={type.bodyMuted}>No results.</Text></Card> : runs.map((rn) => {
            const rows = Object.entries(rn.result?.per_symbol || {}).filter(([, m]: any) => !m.error);
            return (
              <View key={rn.method} testID={`wizard-result-block-${rn.method}`} style={{ marginBottom: spacing.md }}>
                {runs.length > 1 && <View style={styles.exitTag} testID={`wizard-result-exit-${rn.method}`}><Text style={styles.exitTagTxt}>{rn.label} Exit</Text></View>}
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
            );
          })}
        </View>
      )}
    </View>
  );
}


function Health({ isOwner }: { isOwner: boolean }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);

  const load = React.useCallback(() => {
    setLoading(true);
    api.labHealth().then((d) => setData(d?.ready ? d : { ready: false })).catch(() => setData({ error: true })).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const sweep = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setSweeping(true);
    try {
      await api.labHealthSweep();
      Alert.alert("Health sweep started", "Recomputing performance across timeframes. Pull to refresh in a moment.");
    } catch (e: any) { Alert.alert("Sweep failed", e?.message); }
    finally { setSweeping(false); }
  };

  if (loading && !data) return <Card style={{ alignItems: "center", paddingVertical: spacing.lg }}><ActivityIndicator color={colors.teal} /></Card>;
  if (data?.error) return <Card><Text style={type.bodyMuted}>Couldn&apos;t load strategy health.</Text></Card>;

  const strategies: any[] = data?.strategies || [];
  const recommended = strategies.filter((s) => s.recommendation?.tone === "positive").length;

  return (
    <View testID="health-panel">
      <Card style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View>
            <SectionLabel>DAILY STRATEGY HEALTH</SectionLabel>
            <Text style={[type.small, { marginTop: 4 }]}>
              {data?.ready ? `${recommended} recommended · ${strategies.length} analysed` : "No sweep yet — run one to precompute performance."}
            </Text>
          </View>
          <Pressable testID="health-run-sweep" onPress={sweep} disabled={sweeping || !isOwner} style={[styles.pdfBtn, { paddingHorizontal: 12 }, (!isOwner) && { opacity: 0.4 }]}>
            {sweeping ? <ActivityIndicator color={colors.teal} size="small" /> : <><Ionicons name="refresh" size={13} color={colors.teal} /><Text style={styles.pdfTxt}>RUN SWEEP</Text></>}
          </Pressable>
        </View>
      </Card>
      {strategies.length === 0 ? (
        <Card><Text style={type.bodyMuted}>No health data yet. Run a sweep to see per-strategy recommendations.</Text></Card>
      ) : strategies.map((s) => <HealthStrategyCard key={s.strategy} s={s} />)}
    </View>
  );
}

function HealthStrategyCard({ s }: { s: any }) {
  const rec = s.recommendation || {};
  const toneColor = rec.tone === "positive" ? colors.teal : rec.tone === "warning" ? colors.amber : colors.red;
  const h = s.headline || {};
  const pnl = Number(h.net_pnl ?? 0);
  return (
    <Card style={{ marginBottom: spacing.md }} testID={`health-strategy-${s.strategy}`}>
      <View style={styles.rowBetween}>
        <Text style={type.h3}>{s.name}</Text>
        <View style={[styles.exitTag, { borderColor: toneColor, backgroundColor: "transparent" }]} testID={`health-badge-${s.strategy}`}>
          <Text style={[styles.exitTagTxt, { color: toneColor }]}>{rec.badge || "—"}</Text>
        </View>
      </View>
      {rec.reason ? <Text style={[type.small, { marginTop: 4 }]}>{rec.reason}</Text> : null}
      <View style={styles.grid}>
        <Mini label="Net P&L" value={`${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`} color={pnl >= 0 ? colors.teal : colors.red} />
        <Mini label="Win Rate" value={`${(h.win_rate_pct ?? 0).toFixed(0)}%`} />
        <Mini label="Profit Factor" value={(h.profit_factor ?? 0).toFixed(2)} />
        <Mini label="Trades" value={String(h.trades ?? 0)} />
      </View>
      <View style={styles.healthMetaRow}>
        <HealthMeta label="Best Timeframe" value={s.best_timeframe || "—"} />
        <HealthMeta label="Best Exit" value={s.best_exit || "—"} />
      </View>
      <View style={styles.healthMetaRow}>
        <HealthMeta label="MFE Capture" value={`${(s.capture_rate_pct ?? 0).toFixed(0)}%`} />
        <HealthMeta label="Best Regime" value={s.best_regime || "—"} />
      </View>
      <Text style={[type.small, { fontSize: 10, marginTop: spacing.sm, color: colors.textFaint }]}>Based on the latest daily backtest sweep — not a live-trading result.</Text>
    </Card>
  );
}

function HealthMeta({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.healthMeta}>
      <Text style={[type.label, { fontSize: 9 }]}>{label}</Text>
      <Text style={[type.body, { fontSize: 13, fontWeight: "700", marginTop: 2 }]} numberOfLines={1}>{value}</Text>
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
            </View>
          )}
        </Card>
      ))}
    </View>
  );
}

const RUN_KIND_LABELS: Record<string, string> = { backtest: "Validation", grid_search: "Grid Search", sensitivity: "Sensitivity", walk_forward: "Walk-Forward" };
const RUN_EXIT_LABELS: Record<string, string> = { fixed: "Fixed % Target", atr: "ATR Trail", native: "Full Engine", engine: "Full Engine" };

function MyReports() {
  const [runs, setRuns] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = React.useCallback(() => {
    api.labRuns(50)
      .then((d: any) => { setRuns((d.runs || []).filter((r: any) => r.kind !== "health_sweep").slice(0, 30)); setErr(null); })
      .catch((e: any) => setErr(e?.status === 401 || e?.status === 403 ? "owner" : "load"));
  }, []);
  useEffect(() => { load(); }, [load]);

  const del = (r: any) => {
    Alert.alert("Delete report?", "This permanently removes the validation report.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api.deleteLabRun(r.id); setRuns((list) => (list || []).filter((x) => x.id !== r.id)); }
        catch (e: any) { Alert.alert("Delete failed", e?.message); }
      } },
    ]);
  };

  return (
    <Card style={{ marginBottom: spacing.md }} testID="my-reports-history">
      <SectionLabel>MY REPORTS HISTORY</SectionLabel>
      <Text style={[type.small, { marginVertical: spacing.sm }]}>Your past Research Lab validations — saved to your account across every device.</Text>
      {err === "owner" ? (
        <Text style={[type.small, { paddingVertical: spacing.sm }]} testID="reports-owner-gate">Owner login required to view your reports history.</Text>
      ) : err === "load" ? (
        <Pressable testID="reports-retry" onPress={load} style={styles.pdfBtn}><Ionicons name="refresh" size={13} color={colors.teal} /><Text style={styles.pdfTxt}>RETRY</Text></Pressable>
      ) : runs === null ? (
        <ActivityIndicator color={colors.teal} style={{ marginVertical: spacing.md }} />
      ) : runs.length === 0 ? (
        <Text style={[type.small, { paddingVertical: spacing.sm }]} testID="reports-empty">No reports yet. Complete a validation run and it&apos;ll appear here.</Text>
      ) : (
        runs.map((r) => {
          const done = r.status === "DONE";
          const running = r.status === "QUEUED" || r.status === "RUNNING";
          const statusColor = done ? colors.teal : running ? colors.amber : colors.red;
          const strat = r.kind === "health_sweep" ? "All" : (r.strategies || []).join(" + ") || "—";
          return (
            <View key={r.id} style={styles.reportRow} testID="report-row">
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[type.body, { fontSize: 13, fontWeight: "700" }]} numberOfLines={1}>{RUN_KIND_LABELS[r.kind] || r.kind} · {strat}</Text>
                <Text style={[type.small, { fontSize: 10, marginTop: 2 }]} numberOfLines={1}>
                  TF {r.timeframe || "1h"}{r.compare_timeframes ? " · MTF" : ""} · {RUN_EXIT_LABELS[r.exit_method] || r.exit_method || "—"} · {r.period || "—"}
                </Text>
                <Text style={[type.small, { fontSize: 10, color: statusColor, marginTop: 2 }]}>{r.status}</Text>
              </View>
              <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
                <Pressable testID={`report-open-${r.id}`} disabled={!done} onPress={() => Linking.openURL(api.labRunPdfUrl(r.id))} style={[styles.iconBtn, !done && { opacity: 0.3 }]}>
                  <Ionicons name="document-text-outline" size={16} color={colors.teal} />
                </Pressable>
                <Pressable testID={`report-delete-${r.id}`} disabled={running} onPress={() => del(r)} style={[styles.iconBtn, running && { opacity: 0.3 }]}>
                  <Ionicons name="trash-outline" size={16} color={colors.red} />
                </Pressable>
              </View>
            </View>
          );
        })
      )}
    </Card>
  );
}

function Reports() {
  return (
    <View testID="reports-panel">
      <MyReports />
      {["paper", "live"].map((mode) => (
        <Card key={mode} testID={`report-${mode}-box`} style={{ marginBottom: spacing.md }}>
          <SectionLabel>{mode === "paper" ? "PAPER TRADING REPORT" : "LIVE TRADING REPORT"}</SectionLabel>
          <Text style={[type.small, { marginVertical: spacing.sm }]}>A shareable PDF of every closed {mode} trade — entry/exit, P&L, exit reason and equity curve.</Text>
          <Pressable testID={`open-pdf-${mode}`} onPress={() => Linking.openURL(api.tradesPdfUrl(mode))} style={styles.pdfBtn}>
            <Ionicons name="document-text-outline" size={15} color={colors.teal} /><Text style={styles.pdfTxt}>OPEN {mode.toUpperCase()} PDF REPORT</Text>
          </Pressable>
        </Card>
      ))}
    </View>
  );
}

function Optimization({ isOwner }: { isOwner: boolean }) {
  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [res, setRes] = useState<any>(null);
  const run = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setPhase("running"); setRes(null);
    try {
      const { id } = await api.labCreateRun({ kind: "sensitivity", symbols: ["BTC/USD"], period: "3m",
        target: "min_confidence", values: [0.6, 0.65, 0.7, 0.75, 0.8] });
      let done = false;
      for (let i = 0; i < 60 && !done; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const d = await api.labRun(id);
        if (d.status === "DONE") { setRes(d.result); done = true; }
        else if (d.status === "ERROR") throw new Error(d.error || "failed");
      }
      if (!done) throw new Error("timed out");
      setPhase("done");
    } catch (e: any) { setPhase("error"); Alert.alert("Optimization failed", e?.message); }
  };
  const robust = res?.verdict?.startsWith("ROBUST");
  return (
    <View testID="optimization-panel">
      <Card style={{ marginBottom: spacing.md }}>
        <SectionLabel>PARAMETER SENSITIVITY</SectionLabel>
        <Text style={[type.small, { marginVertical: spacing.sm }]}>Sweeps min-confidence (0.60→0.80) on BTC to reveal whether the edge is a robust plateau or a fragile, curve-fit cliff.</Text>
        <Pressable testID="optimize-run" onPress={run} disabled={phase === "running"} style={styles.runBtn}>
          {phase === "running" ? <ActivityIndicator color={colors.bg} /> : <><Ionicons name="analytics" size={16} color={colors.bg} /><Text style={styles.runTxt}>RUN OPTIMIZATION</Text></>}
        </Pressable>
      </Card>
      {phase === "running" && <Card style={{ alignItems: "center", paddingVertical: spacing.lg }}><ActivityIndicator color={colors.teal} /><Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>Sweeping parameters…</Text></Card>}
      {phase === "done" && res && (
        <Card testID="optimize-results">
          <View style={[styles.verdict, { borderColor: robust ? colors.teal : colors.amber, backgroundColor: robust ? colors.tealGlow : "rgba(245,180,90,0.1)" }]}>
            <Ionicons name={robust ? "shield-checkmark" : "warning"} size={18} color={robust ? colors.teal : colors.amber} />
            <Text style={[type.body, { fontWeight: "700", color: robust ? colors.teal : colors.amber, flex: 1 }]}>{res.verdict}</Text>
          </View>
          <SectionLabel style={{ marginTop: spacing.md }}>SENSITIVITY CURVE</SectionLabel>
          {(res.curve || []).map((c: any) => (
            <View key={c.value} style={styles.curveRow}>
              <Text style={[type.body, { width: 60 }]}>{c.value}</Text>
              <Text style={[type.body, { flex: 1, color: (c.total_return_pct ?? 0) >= 0 ? colors.teal : colors.red }]}>{(c.total_return_pct ?? 0).toFixed(1)}%</Text>
              <Text style={type.small}>{c.trades} trades</Text>
            </View>
          ))}
        </Card>
      )}
    </View>
  );
}

function Mini({ label, value, color }: { label: string; value: string; color?: string }) {
  return <View style={{ minWidth: 70 }}><Text style={type.label}>{label}</Text><Text style={[type.h3, { fontSize: 15, color: color || colors.text, textTransform: "capitalize" }]}>{value || "—"}</Text></View>;
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  tabBar: { backgroundColor: colors.bg, boxShadow: "none", elevation: 0, borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  indicator: { backgroundColor: colors.teal, height: 2.5, borderRadius: 2 },
  tabLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 0.2, textTransform: "none" },
  runBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: spacing.sm + 2, marginTop: spacing.md },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.xs },
  chip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8, maxWidth: "100%" },
  chipOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 12 },
  chipTxtOn: { color: colors.teal },
  exitCard: { flex: 1, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.sm + 2 },
  exitCardOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  check: { width: 16, height: 16, borderRadius: 4, borderWidth: 1, borderColor: colors.textFaint, alignItems: "center", justifyContent: "center", marginBottom: 6 },
  checkOn: { backgroundColor: colors.teal, borderColor: colors.teal },
  exitTag: { alignSelf: "flex-start", borderWidth: 1, borderColor: colors.tealDim, backgroundColor: colors.tealGlow, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 3, marginBottom: spacing.sm },
  exitTagTxt: { color: colors.teal, fontWeight: "800", fontSize: 10, letterSpacing: 0.8, textTransform: "uppercase" },
  statusLine: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm },
  statusDot: { width: 8, height: 8, borderRadius: 4 },

  runTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 12 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  recBox: { backgroundColor: colors.tealGlow, borderRadius: radius.md, borderWidth: 1, borderColor: colors.tealDim, padding: spacing.md, marginTop: spacing.sm },
  pdfBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: colors.tealDim, borderRadius: radius.sm, paddingVertical: spacing.sm + 2 },
  pdfTxt: { color: colors.teal, fontWeight: "700", fontSize: 11, letterSpacing: 0.6 },
  verdict: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderRadius: radius.md, padding: spacing.md },
  curveRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  healthMetaRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  healthMeta: { flex: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.sm + 2, paddingVertical: spacing.sm },
  reportRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 10, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  iconBtn: { width: 34, height: 34, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center" },
});
