import React, { useEffect, useMemo, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Polyline, Line, Circle } from "react-native-svg";
import api from "../src/api";
import { Card, SectionLabel } from "../src/components/Card";
import { colors, spacing, type, radius, pnlColor } from "../src/theme";
import { pct, signedUsd, duration } from "../src/format";

const CORE = ["hunter", "squeeze", "continuation"];

type Trade = { side?: string; pnl?: number | null; hold_seconds?: number | null; timestamp?: string; symbol?: string; exit_module?: string | null; exit_reason?: string | null };

function computeStats(trades: Trade[], startingBalance: number) {
  const closed = (trades || []).filter((t) => t.side === "SELL" && t.pnl != null);
  const wins = closed.filter((t) => (t.pnl || 0) > 0);
  const grossWin = wins.reduce((a, t) => a + (t.pnl || 0), 0);
  const grossLoss = Math.abs(closed.filter((t) => (t.pnl || 0) < 0).reduce((a, t) => a + (t.pnl || 0), 0));
  const netPnl = closed.reduce((a, t) => a + (t.pnl || 0), 0);
  const holds = closed.map((t) => t.hold_seconds || 0).filter((h) => h > 0);
  // equity curve (oldest -> newest), starting from starting balance
  const ordered = [...closed].reverse();
  let eq = startingBalance || 0;
  const curve: number[] = [eq];
  let peak = eq;
  let maxDd = 0;
  for (const t of ordered) {
    eq += t.pnl || 0;
    curve.push(eq);
    peak = Math.max(peak, eq);
    if (peak > 0) maxDd = Math.max(maxDd, (peak - eq) / peak * 100);
  }
  return {
    n: closed.length,
    winRate: closed.length ? (wins.length / closed.length) * 100 : 0,
    profitFactor: grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0,
    netPnl,
    totalReturnPct: startingBalance > 0 ? (netPnl / startingBalance) * 100 : 0,
    maxDrawdownPct: maxDd,
    avgHold: holds.length ? holds.reduce((a, h) => a + h, 0) / holds.length : 0,
    curve,
  };
}

function exitBreakdown(trades: Trade[]) {
  const closed = (trades || []).filter((t) => t.side === "SELL" && t.pnl != null);
  const map: Record<string, { key: string; n: number; pnl: number }> = {};
  for (const t of closed) {
    const key = t.exit_module ? `mod ${t.exit_module}` : (t.exit_reason || "OTHER");
    const g = map[key] || (map[key] = { key, n: 0, pnl: 0 });
    g.n += 1; g.pnl += t.pnl || 0;
  }
  return Object.values(map).sort((a, b) => b.n - a.n);
}

export default function Analytics() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [tfStrategy, setTfStrategy] = useState("hunter");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [t, h, p] = await Promise.all([
          api.trades(200).then((r: any) => (Array.isArray(r) ? r : (r.items || r.trades || []))).catch(() => []),
          api.labHealth().catch(() => null),
          api.portfolio().catch(() => null),
        ]);
        if (!alive) return;
        setTrades(t); setHealth(h); setPortfolio(p);
      } finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, []);

  const startingBalance = portfolio?.starting_balance ?? 1200;
  const stats = useMemo(() => computeStats(trades, startingBalance), [trades, startingBalance]);
  const exits = useMemo(() => exitBreakdown(trades), [trades]);
  const strategies: any[] = health?.strategies || [];
  const selected = strategies.find((s) => s.strategy === tfStrategy);
  const tfRows: any[] = selected?.timeframe_comparison || [];

  return (
    <View style={styles.fill}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="analytics-back" onPress={() => router.back()} hitSlop={10} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.teal} />
        </Pressable>
        <Text style={styles.title}>Analytics</Text>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.teal} style={{ marginTop: spacing.xl }} />
      ) : (
        <ScrollView testID="analytics-screen" contentContainerStyle={{ padding: spacing.md, paddingBottom: insets.bottom + 40 }}>
          {/* PORTFOLIO PERFORMANCE */}
          <Card testID="an-performance" style={{ marginBottom: spacing.md }}>
            <SectionLabel>PORTFOLIO PERFORMANCE</SectionLabel>
            <EquityCurve curve={stats.curve} />
            <View style={styles.statGrid}>
              <Stat label="Total Return" value={pct(stats.totalReturnPct, 2)} tone={stats.totalReturnPct} tid="an-total-return" />
              <Stat label="Net P&L" value={signedUsd(stats.netPnl)} tone={stats.netPnl} tid="an-net-pnl" />
              <Stat label="Win Rate" value={`${stats.winRate.toFixed(0)}%`} tid="an-win-rate" />
              <Stat label="Profit Factor" value={stats.profitFactor === Infinity ? "∞" : stats.profitFactor.toFixed(2)} tid="an-profit-factor" />
              <Stat label="Max Drawdown" value={`${stats.maxDrawdownPct.toFixed(1)}%`} tone={-stats.maxDrawdownPct} tid="an-max-dd" />
              <Stat label="Avg Hold" value={duration(stats.avgHold)} tid="an-avg-hold" />
            </View>
            <Text style={styles.footnote}>{stats.n} closed trade{stats.n === 1 ? "" : "s"} analysed</Text>
          </Card>

          {/* PER-STRATEGY */}
          <Card testID="an-strategies" style={{ marginBottom: spacing.md }}>
            <SectionLabel>STRATEGY PERFORMANCE</SectionLabel>
            {strategies.length === 0 ? (
              <Text style={[type.small, { marginTop: 4 }]}>No health sweep yet — run one in Research › Health.</Text>
            ) : strategies.map((s) => {
              const h = s.headline || {};
              return (
                <View key={s.strategy} style={styles.stratRow} testID={`an-strat-${s.strategy}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.stratName}>{s.name}</Text>
                    <Text style={[styles.badge, s.recommendation?.tone === "positive" ? styles.badgeGood : s.recommendation?.tone === "warning" ? styles.badgeWarn : styles.badgeBad]}>
                      {s.recommendation?.badge || "—"}
                    </Text>
                  </View>
                  <View style={styles.stratMetrics}>
                    <Text style={[styles.metricBig, { color: pnlColor(h.total_return_pct || 0) }]}>{pct(h.total_return_pct, 1)}</Text>
                    <Text style={styles.metricSub}>{(h.win_rate_pct ?? 0).toFixed(0)}% win · PF {h.profit_factor ?? "—"} · {h.trades ?? 0}t</Text>
                    <Text style={styles.metricSub}>Best TF: <Text style={{ color: colors.teal }}>{s.best_timeframe || "—"}</Text></Text>
                  </View>
                </View>
              );
            })}
          </Card>

          {/* MULTI-TIMEFRAME COMPARISON */}
          <Card testID="an-timeframes" style={{ marginBottom: spacing.md }}>
            <SectionLabel>MULTI-TIMEFRAME COMPARISON</SectionLabel>
            <View style={styles.chipWrap}>
              {CORE.map((k) => {
                const name = strategies.find((s) => s.strategy === k)?.name || k;
                return (
                  <Pressable key={k} testID={`an-tf-strat-${k}`} onPress={() => setTfStrategy(k)}
                    style={[styles.chip, tfStrategy === k && styles.chipActive]}>
                    <Text style={[styles.chipTxt, tfStrategy === k && { color: colors.teal }]}>{name}</Text>
                  </Pressable>
                );
              })}
            </View>
            {tfRows.length === 0 ? (
              <Text style={[type.small, { marginTop: spacing.sm }]}>No timeframe data yet — run a Health sweep to populate.</Text>
            ) : (
              <View style={{ marginTop: spacing.sm }}>
                <View style={[styles.tfRow, styles.tfHead]}>
                  <Text style={[styles.tfCell, styles.tfHeadTxt, { flex: 1.1 }]}>TF</Text>
                  <Text style={[styles.tfCell, styles.tfHeadTxt]}>Return</Text>
                  <Text style={[styles.tfCell, styles.tfHeadTxt]}>Win</Text>
                  <Text style={[styles.tfCell, styles.tfHeadTxt]}>Max DD</Text>
                  <Text style={[styles.tfCell, styles.tfHeadTxt]}>Trades</Text>
                </View>
                {tfRows.map((r) => {
                  const isBest = r.timeframe === selected?.best_timeframe;
                  return (
                    <View key={r.timeframe} style={[styles.tfRow, isBest && styles.tfRowBest]} testID={`an-tf-row-${r.timeframe}`}>
                      <Text style={[styles.tfCell, { flex: 1.1, color: isBest ? colors.teal : colors.text, fontWeight: "800" }]}>
                        {r.timeframe}{isBest ? " ★" : ""}
                      </Text>
                      <Text style={[styles.tfCell, { color: pnlColor(r.total_return_pct || 0) }]}>{pct(r.total_return_pct, 1)}</Text>
                      <Text style={styles.tfCell}>{(r.win_rate_pct ?? 0).toFixed(0)}%</Text>
                      <Text style={styles.tfCell}>{(r.max_drawdown_pct ?? 0).toFixed(1)}%</Text>
                      <Text style={styles.tfCell}>{r.trades ?? 0}</Text>
                    </View>
                  );
                })}
              </View>
            )}
          </Card>

          {/* EXIT BREAKDOWN */}
          <Card testID="an-exits">
            <SectionLabel>EXIT BREAKDOWN</SectionLabel>
            {exits.length === 0 ? (
              <Text style={[type.small, { marginTop: 4 }]}>No closed trades yet.</Text>
            ) : exits.map((e) => (
              <View key={e.key} style={styles.exitRow} testID={`an-exit-${e.key.replace(/\s+/g, "-")}`}>
                <Text style={[type.body, { flex: 1 }]} numberOfLines={1}>{e.key}</Text>
                <Text style={[styles.exitN]}>{e.n} trade{e.n === 1 ? "" : "s"}</Text>
                <Text style={[styles.exitPnl, { color: pnlColor(e.pnl) }]}>{signedUsd(e.pnl)}</Text>
              </View>
            ))}
          </Card>
        </ScrollView>
      )}
    </View>
  );
}

function Stat({ label, value, tone, tid }: { label: string; value: string; tone?: number; tid?: string }) {
  const color = tone === undefined ? colors.text : pnlColor(tone);
  return (
    <View style={styles.statCell} testID={tid}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, { color }]}>{value}</Text>
    </View>
  );
}

function EquityCurve({ curve }: { curve: number[] }) {
  const W = 300, H = 90, P = 4;
  if (!curve || curve.length < 2) {
    return <View style={styles.chartEmpty}><Text style={[type.small]}>Equity curve appears after trades close.</Text></View>;
  }
  const min = Math.min(...curve), max = Math.max(...curve);
  const range = max - min || 1;
  const stepX = (W - P * 2) / (curve.length - 1);
  const pts = curve.map((v, i) => {
    const x = P + i * stepX;
    const y = P + (H - P * 2) * (1 - (v - min) / range);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = curve[curve.length - 1];
  const up = last >= curve[0];
  const lastY = P + (H - P * 2) * (1 - (last - min) / range);
  return (
    <View style={styles.chartWrap}>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <Line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke={colors.cardBorder} strokeWidth={1} />
        <Polyline points={pts} fill="none" stroke={up ? colors.teal : colors.red} strokeWidth={2} strokeLinejoin="round" />
        <Circle cx={W - P} cy={lastY} r={3} fill={up ? colors.teal : colors.red} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  backBtn: { width: 22, alignItems: "flex-start" },
  title: { color: colors.text, fontSize: 20, fontWeight: "800" },
  chartWrap: { marginVertical: spacing.sm, backgroundColor: colors.bgElevated, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder, padding: spacing.sm },
  chartEmpty: { height: 90, alignItems: "center", justifyContent: "center", backgroundColor: colors.bgElevated, borderRadius: radius.md, borderWidth: 1, borderColor: colors.cardBorder, marginVertical: spacing.sm },
  statGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  statCell: { width: "47.5%", flexGrow: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  statLabel: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.5, textTransform: "uppercase" },
  statValue: { fontSize: 18, fontWeight: "800", marginTop: 3 },
  footnote: { color: colors.textFaint, fontSize: 11, marginTop: spacing.sm },
  stratRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  stratName: { color: colors.text, fontSize: 15, fontWeight: "700" },
  badge: { alignSelf: "flex-start", fontSize: 10, fontWeight: "800", marginTop: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  badgeGood: { color: colors.green, backgroundColor: colors.greenGlow },
  badgeWarn: { color: colors.amber, backgroundColor: "rgba(242,169,59,0.14)" },
  badgeBad: { color: colors.red, backgroundColor: colors.redGlow },
  stratMetrics: { alignItems: "flex-end", minWidth: 130 },
  metricBig: { fontSize: 18, fontWeight: "800" },
  metricSub: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  chip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingVertical: 6, paddingHorizontal: spacing.md },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 12 },
  tfRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  tfRowBest: { backgroundColor: colors.tealGlow, borderRadius: radius.sm },
  tfHead: { borderTopWidth: 0 },
  tfHeadTxt: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  tfCell: { flex: 1, textAlign: "right", color: colors.text, fontSize: 12, fontWeight: "600", fontVariant: ["tabular-nums"] },
  exitRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  exitN: { color: colors.textMuted, fontSize: 12, fontWeight: "600" },
  exitPnl: { fontSize: 13, fontWeight: "800", minWidth: 70, textAlign: "right", fontVariant: ["tabular-nums"] },
});
