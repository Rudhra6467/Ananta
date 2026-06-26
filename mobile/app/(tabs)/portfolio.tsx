import React, { useMemo, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  RefreshControl,
  StyleSheet,
  Modal,
  Pressable,
  ActivityIndicator,
  useWindowDimensions,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { Segmented } from "../../src/components/Segmented";
import { PositionCard } from "../../src/components/PositionCard";
import { EquityCurve } from "../../src/components/charts";
import { LoadingView, ErrorView, EmptyView } from "../../src/components/StateView";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { usd, pct, base, duration, clockTime } from "../../src/format";

const TABS = [
  { key: "active", label: "Active" },
  { key: "closed", label: "Closed" },
  { key: "perf", label: "Performance" },
];

async function loadPortfolio() {
  const [portfolio, trades] = await Promise.all([api.portfolio(), api.trades(200)]);
  return { portfolio, trades };
}

function computePerf(closed: any[]) {
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0);
  const losses = closed.filter((t) => (t.pnl ?? 0) < 0);
  const grossWin = wins.reduce((a, t) => a + (t.pnl || 0), 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + (t.pnl || 0), 0));
  const n = closed.length;
  const winRate = n ? (wins.length / n) * 100 : 0;
  const avgWin = wins.length ? grossWin / wins.length : 0;
  const avgLoss = losses.length ? grossLoss / losses.length : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0;
  const wr = n ? wins.length / n : 0;
  const expectancy = n ? wr * avgWin - (1 - wr) * avgLoss : 0;
  const netPnl = closed.reduce((a, t) => a + (t.pnl || 0), 0);
  return { n, winRate, avgWin, avgLoss, profitFactor, expectancy, netPnl, grossWin, grossLoss };
}

export default function Portfolio() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [tab, setTab] = useState("active");
  const [target, setTarget] = useState<any>(null);
  const [closing, setClosing] = useState(false);
  const { data, loading, error, refreshing, refresh } = useFetch(loadPortfolio, [], 20000);

  const positions: any[] = data?.portfolio?.positions || [];
  const closed: any[] = useMemo(
    () => (data?.trades?.items || []).filter((t: any) => t.trade_result === "WIN" || t.trade_result === "LOSS"),
    [data]
  );
  const perf = useMemo(() => computePerf(closed), [closed]);
  const starting = data?.portfolio?.starting_balance ?? 1200;
  const equitySeries = useMemo(() => {
    const sorted = [...closed].sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
    let eq = starting;
    const out = [starting];
    sorted.forEach((t) => { eq += t.pnl || 0; out.push(eq); });
    return out;
  }, [closed, starting]);

  const doClose = async () => {
    if (!target) return;
    setClosing(true);
    try {
      await api.closePosition(base(target.symbol));
      setTarget(null);
      refresh();
    } catch (e: any) {
      // surface minimal; keep modal for retry awareness
    } finally {
      setClosing(false);
    }
  };

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  return (
    <View style={styles.fill}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.lg }}>
        <Text style={type.h1}>Portfolio</Text>
        <Text style={[type.bodyMuted, { marginTop: 2 }]}>
          {usd(data?.portfolio?.equity)} equity · {pct(data?.portfolio?.total_pnl_pct)} all-time
        </Text>
        <View style={{ marginTop: spacing.md }}>
          <Segmented options={TABS} value={tab} onChange={setTab} testIDPrefix="pf-tab" />
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}
      >
        {tab === "active" &&
          (positions.length === 0 ? (
            <EmptyView icon="trending-up-outline" title="No active positions" subtitle="Open trades will appear here as the engine executes." />
          ) : (
            positions.map((p) => <PositionCard key={p.symbol} p={p} onPress={() => setTarget(p)} />)
          ))}

        {tab === "closed" &&
          (closed.length === 0 ? (
            <EmptyView icon="time-outline" title="No closed trades yet" subtitle="Trade history will build up here over time." />
          ) : (
            closed.map((t) => <ClosedTradeCard key={t.id} t={t} />)
          ))}

        {tab === "perf" && (
          <PerformanceTab perf={perf} equity={equitySeries} width={width - spacing.lg * 2 - spacing.md * 2} />
        )}
      </ScrollView>

      {/* Manual close confirm */}
      <Modal transparent visible={!!target} animationType="fade" onRequestClose={() => setTarget(null)}>
        <Pressable style={styles.backdrop} onPress={() => !closing && setTarget(null)}>
          <Pressable style={styles.sheet}>
            <Ionicons name="alert-circle" size={36} color={colors.amber} style={{ alignSelf: "center" }} />
            <Text style={[type.h2, { textAlign: "center", marginTop: spacing.sm }]}>
              Close {target ? base(target.symbol) : ""}?
            </Text>
            <Text style={[type.bodyMuted, { textAlign: "center", marginTop: spacing.xs }]}>
              This liquidates the position immediately at market.
            </Text>
            <Pressable testID="confirm-close-btn" onPress={doClose} disabled={closing} style={styles.dangerBtn}>
              {closing ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.dangerText}>Close Position</Text>}
            </Pressable>
            <Pressable testID="cancel-close-btn" onPress={() => !closing && setTarget(null)} style={styles.cancelBtn}>
              <Text style={{ color: colors.textMuted, fontWeight: "700" }}>Cancel</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function ClosedTradeCard({ t }: { t: any }) {
  const win = (t.pnl ?? 0) >= 0;
  return (
    <Card testID={`closed-${t.id}`} style={{ marginBottom: spacing.sm }}>
      <View style={styles.closedTop}>
        <View>
          <Text style={styles.closedSym}>{base(t.symbol)}</Text>
          <Text style={styles.closedMeta}>{clockTime(t.timestamp)} · held {duration(t.hold_seconds)}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={[styles.closedPnl, { color: pnlColor(t.pnl ?? 0) }]}>
            {win ? "+" : ""}{usd(t.pnl)}
          </Text>
          <Text style={[styles.closedRet, { color: pnlColor(t.return_pct ?? 0) }]}>{pct(t.return_pct)}</Text>
        </View>
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, flexWrap: "wrap" }}>
        <Pill label={t.trade_result || (win ? "WIN" : "LOSS")} tone={win ? "teal" : "red"} dot />
        {t.exit_reason ? <Pill label={String(t.exit_reason).replace(/_/g, " ")} tone="muted" /> : null}
        {t.volatility_regime ? <Pill label={String(t.volatility_regime).replace(/_/g, " ")} tone="neutral" /> : null}
      </View>
    </Card>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={type.label}>{label}</Text>
      <Text style={[styles.metricVal, tone ? { color: tone } : null]}>{value}</Text>
    </View>
  );
}

function PerformanceTab({ perf, equity, width }: { perf: any; equity: number[]; width: number }) {
  if (perf.n === 0) {
    return <EmptyView icon="bar-chart-outline" title="No performance data yet" subtitle="Metrics populate after the first closed trade." />;
  }
  return (
    <View>
      <SectionLabel>Equity Curve</SectionLabel>
      <Card style={{ marginBottom: spacing.md }}>
        <EquityCurve data={equity} width={width} color={perf.netPnl >= 0 ? colors.teal : colors.red} />
        <Text style={[styles.closedMeta, { marginTop: spacing.sm }]}>
          Net P&L {perf.netPnl >= 0 ? "+" : ""}{usd(perf.netPnl)} across {perf.n} closed trades
        </Text>
      </Card>

      <SectionLabel>Statistics</SectionLabel>
      <Card>
        <View style={styles.metricGrid}>
          <Metric label="Win Rate" value={`${perf.winRate.toFixed(1)}%`} tone={perf.winRate >= 50 ? colors.teal : colors.red} />
          <Metric label="Profit Factor" value={perf.profitFactor === Infinity ? "∞" : perf.profitFactor.toFixed(2)} tone={perf.profitFactor >= 1 ? colors.teal : colors.red} />
          <Metric label="Avg Win" value={usd(perf.avgWin)} tone={colors.teal} />
          <Metric label="Avg Loss" value={usd(perf.avgLoss)} tone={colors.red} />
          <Metric label="Expectancy" value={`${perf.expectancy >= 0 ? "+" : ""}${usd(perf.expectancy)}`} tone={pnlColor(perf.expectancy)} />
          <Metric label="Trades" value={String(perf.n)} />
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  closedTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  closedSym: { color: colors.text, fontSize: 18, fontWeight: "800", letterSpacing: 0.5 },
  closedMeta: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  closedPnl: { fontSize: 17, fontWeight: "800" },
  closedRet: { fontSize: 13, fontWeight: "700", marginTop: 2 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap" },
  metric: { width: "50%", paddingVertical: spacing.sm },
  metricVal: { color: colors.text, fontSize: 22, fontWeight: "800", marginTop: 4 },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.card,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  dangerBtn: {
    backgroundColor: colors.red,
    borderRadius: radius.pill,
    paddingVertical: spacing.md,
    alignItems: "center",
    marginTop: spacing.lg,
  },
  dangerText: { color: colors.bg, fontWeight: "800", fontSize: 16 },
  cancelBtn: { alignItems: "center", paddingVertical: spacing.md, marginTop: spacing.xs },
});
