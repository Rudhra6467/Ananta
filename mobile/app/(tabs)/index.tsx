import React, { useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  RefreshControl,
  StyleSheet,
  Pressable,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { Logo } from "../../src/components/Logo";
import { AITimeline } from "../../src/components/AITimeline";
import { PositionCard } from "../../src/components/PositionCard";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { usd, pct, price, base } from "../../src/format";

const RAIL_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "AVAX/USD"];

async function loadCockpit() {
  const [portfolio, environment, market, risk, reasoning] = await Promise.all([
    api.portfolio(),
    api.getEnvironment(),
    api.marketSnapshots(),
    api.riskStatus(),
    api.reasoning(12),
  ]);
  return { portfolio, environment, market, risk, reasoning };
}

function botStatus(risk: any, positions: any[]) {
  if (risk?.manual_kill_switch) return { label: "EMERGENCY STOP", tone: "red", icon: "hand-left" };
  if (risk?.status && !risk.status.overall_safe) return { label: "HALTED", tone: "amber", icon: "pause-circle" };
  if ((positions || []).length > 0) return { label: "MANAGING POSITIONS", tone: "teal", icon: "pulse" };
  return { label: "SCANNING", tone: "teal", icon: "scan" };
}

export default function Cockpit() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { data, loading, error, refreshing, refresh } = useFetch(loadCockpit, [], 15000);

  const onRetry = useCallback(() => refresh(), [refresh]);

  if (loading && !data) return <View style={styles.fill}><LoadingView /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={onRetry} /></View>;

  const pf = data!.portfolio;
  const env = data!.environment;
  const snaps: any[] = data!.market?.snapshots || [];
  const positions: any[] = pf?.positions || [];
  const status = botStatus(data!.risk, positions);
  const isLive = env?.is_live;
  const dailyPnlPct = pf?.daily_pnl_pct ?? 0;
  const dayStart = pf?.day_start_equity ?? pf?.starting_balance ?? 0;
  const dailyPnlUsd = (pf?.equity ?? 0) - dayStart;

  const railMap = new Map(snaps.map((s) => [s.symbol, s]));
  const rail = RAIL_SYMBOLS.map((sym) => railMap.get(sym)).filter(Boolean);

  return (
    <ScrollView
      style={styles.fill}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing.xxl }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}
    >
      {/* Header */}
      <View style={styles.header}>
        <Pressable testID="account-logo-btn" onPress={() => router.push("/account")} hitSlop={10}>
          <Logo size={22} />
        </Pressable>
        <Pill
          label={isLive ? "LIVE" : "PAPER"}
          tone={isLive ? "red" : "teal"}
          dot
        />
      </View>

      {/* Portfolio hero */}
      <View style={styles.hero}>
        <Text style={type.label}>Portfolio Value</Text>
        <Text testID="cockpit-equity" style={styles.heroValue}>{usd(pf?.equity)}</Text>
        <View style={styles.heroRow}>
          <Ionicons
            name={dailyPnlUsd >= 0 ? "trending-up" : "trending-down"}
            size={16}
            color={pnlColor(dailyPnlUsd)}
          />
          <Text style={[styles.heroPnl, { color: pnlColor(dailyPnlUsd) }]}>
            {dailyPnlUsd >= 0 ? "+" : ""}{usd(dailyPnlUsd)} · {pct(dailyPnlPct)}
          </Text>
          <Text style={styles.heroToday}>today</Text>
        </View>
      </View>

      {/* Market rail */}
      <SectionLabel style={styles.sectionPad}>Market</SectionLabel>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.rail}
      >
        {rail.map((s: any) => {
          const up = (s.change_24h_pct ?? 0) >= 0;
          return (
            <Pressable
              key={s.symbol}
              testID={`market-${base(s.symbol)}`}
              onPress={() => router.push(`/asset/${base(s.symbol)}`)}
              style={({ pressed }) => [styles.railCard, pressed && { backgroundColor: colors.cardPressed }]}
            >
              <Text style={styles.railSym}>{base(s.symbol)}</Text>
              <Text style={styles.railPrice}>{price(s.price)}</Text>
              <Text style={[styles.railChange, { color: pnlColor(s.change_24h_pct ?? 0) }]}>
                {up ? "▲" : "▼"} {pct(s.change_24h_pct)}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {/* Bot status */}
      <View style={styles.sectionPad}>
        <Card testID="bot-status-card">
          <View style={styles.statusRow}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Ionicons name={status.icon as any} size={22} color={(colors as any)[status.tone] || colors.teal} />
              <View>
                <Text style={type.label}>Engine Status</Text>
                <Text style={[styles.statusLabel, { color: (colors as any)[status.tone] || colors.teal }]}>
                  {status.label}
                </Text>
              </View>
            </View>
            <Pill label={(env?.exchange || "kraken").toUpperCase()} tone="muted" />
          </View>
        </Card>
      </View>

      {/* AI timeline */}
      <View style={styles.sectionPad}>
        <View style={styles.sectionHead}>
          <SectionLabel>Recent AI Decisions</SectionLabel>
        </View>
        <Card>
          <AITimeline items={data!.reasoning?.items || []} max={6} />
        </Card>
      </View>

      {/* Open positions preview */}
      <View style={styles.sectionPad}>
        <View style={styles.sectionHead}>
          <SectionLabel>Open Positions</SectionLabel>
          {positions.length > 0 && (
            <Pressable testID="see-all-positions" onPress={() => router.push("/portfolio")}>
              <Text style={styles.link}>See all →</Text>
            </Pressable>
          )}
        </View>
        {positions.length === 0 ? (
          <Card>
            <Text style={styles.flat}>No open positions. The engine is hunting for setups.</Text>
          </Card>
        ) : (
          positions.slice(0, 3).map((p) => (
            <PositionCard key={p.symbol} p={p} onPress={() => router.push("/portfolio")} />
          ))
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.lg,
  },
  hero: { paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  heroValue: { color: colors.text, fontSize: 44, fontWeight: "800", letterSpacing: -1, marginTop: 4 },
  heroRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 },
  heroPnl: { fontSize: 15, fontWeight: "700" },
  heroToday: { color: colors.textFaint, fontSize: 13 },
  sectionPad: { paddingHorizontal: spacing.lg, marginTop: spacing.lg },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  link: { color: colors.teal, fontWeight: "700", fontSize: 13 },
  rail: { paddingHorizontal: spacing.lg, gap: spacing.sm, paddingVertical: 2 },
  railCard: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    minWidth: 104,
  },
  railSym: { color: colors.textMuted, fontSize: 12, fontWeight: "700", letterSpacing: 0.5 },
  railPrice: { color: colors.text, fontSize: 18, fontWeight: "800", marginTop: 6 },
  railChange: { fontSize: 13, fontWeight: "700", marginTop: 4 },
  statusRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  statusLabel: { fontSize: 17, fontWeight: "800", marginTop: 2 },
  flat: { color: colors.textMuted, fontSize: 14 },
});
