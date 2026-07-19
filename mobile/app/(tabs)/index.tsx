import React, { useCallback, useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  RefreshControl,
  StyleSheet,
  Pressable,
  Modal,
  TextInput,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useFetch } from "../../src/useFetch";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { Logo } from "../../src/components/Logo";
import { AITimeline } from "../../src/components/AITimeline";
import { PositionCard } from "../../src/components/PositionCard";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { TradingWizard } from "../../src/components/TradingWizard";
import { AskAnanta } from "../../src/components/AskAnanta";
import { SystemHealthChip } from "../../src/components/SystemHealthChip";
import { StrategyHealthCard } from "../../src/components/StrategyHealthCard";
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
  const { isOwner } = useAuth();
  const [addOpen, setAddOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [weeklyOpen, setWeeklyOpen] = useState(false);
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
  const rail = snaps.length ? snaps : RAIL_SYMBOLS.map((sym) => railMap.get(sym)).filter(Boolean);

  return (
    <View style={styles.fill}>
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

      {/* AI Coach headline banner (credit-free) */}
      <CoachBanner />

      <View style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.sm }}>
        <SystemHealthChip />
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

      {/* Action hub — dual control row directly beneath Account Value */}
      <View style={styles.sectionPad}>
        <View style={styles.dualRow}>
          <Pressable testID="cockpit-start-trading" onPress={() => (isOwner ? setWizardOpen(true) : Alert.alert("Owner login required"))} style={[styles.halfBtn, styles.halfPrimary]}>
            <Ionicons name="rocket" size={16} color={colors.bg} />
            <Text style={styles.halfPrimaryTxt}>Start Trading</Text>
          </Pressable>
          <Pressable testID="cockpit-weekly-review" onPress={() => setWeeklyOpen(true)} style={[styles.halfBtn, styles.halfGhost]}>
            <Ionicons name="sparkles" size={16} color={colors.teal} />
            <Text style={styles.halfGhostTxt}>Weekly AI Review</Text>
          </Pressable>
        </View>

        {/* Strategy Health — top recommended strategies from the daily sweep */}
        <View style={{ marginTop: spacing.md }}>
          <StrategyHealthCard />
        </View>
      </View>

      {/* Active Watchlist rail */}
      <View style={[styles.sectionPad, { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }]}>
        <SectionLabel>Active Watchlist</SectionLabel>
        <Pressable testID="watchlist-add-asset" onPress={() => (isOwner ? setAddOpen(true) : Alert.alert("Owner login required"))} hitSlop={8}
          style={styles.addBtn}>
          <Ionicons name="add" size={18} color={colors.teal} />
        </Pressable>
      </View>
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
            <Pressable testID="see-all-positions" onPress={() => router.push("/trade")}>
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
            <PositionCard key={p.symbol} p={p} onPress={() => router.push("/trade")} />
          ))
        )}
      </View>
      <AddAssetModal visible={addOpen} onClose={() => setAddOpen(false)} onAdded={() => { setAddOpen(false); refresh(); }} />
    </ScrollView>
    <TradingWizard visible={wizardOpen} onClose={() => setWizardOpen(false)} onLaunched={refresh} />
    <WeeklyReviewModal visible={weeklyOpen} onClose={() => setWeeklyOpen(false)} />
    <AskAnanta tab="cockpit" routeName="index" />
    </View>
  );
}

function WeeklyReviewModal({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [review, setReview] = useState<any>(null);
  useEffect(() => {
    if (!visible) return;
    setLoading(true); setReview(null);
    api.coachReview().then(setReview).catch(() => setReview({ error: true })).finally(() => setLoading(false));
  }, [visible]);
  const rec = review?.recommendation;
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalWrap}>
        <View style={styles.modalCard}>
          <View style={styles.statusRow}>
            <Text style={type.h2}>Weekly AI Review</Text>
            <Pressable testID="weekly-review-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          {loading ? <ActivityIndicator color={colors.teal} style={{ marginVertical: spacing.lg }} /> : (
            <ScrollView style={{ maxHeight: 380, marginTop: spacing.sm }}>
              {review?.error ? <Text style={type.bodyMuted}>Coach review is unavailable right now.</Text> : (
                <>
                  <Text style={[type.body, { lineHeight: 22 }]}>{review?.summary || review?.headline || "No review available yet — trade more to unlock coaching."}</Text>
                  {rec?.text ? <Text style={[type.bodyMuted, { marginTop: spacing.sm, lineHeight: 21 }]}>{rec.text}</Text> : null}
                </>
              )}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

function AddAssetModal({ visible, onClose, onAdded }: { visible: boolean; onClose: () => void; onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [busy, setBusy] = useState("");
  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(() => { api.watchlistSearch(q).then((d: any) => setResults(d.results || [])).catch(() => setResults([])); }, 180);
    return () => clearTimeout(t);
  }, [q, visible]);
  const add = async (sym: string) => {
    setBusy(sym);
    try { await api.watchlistAdd(sym); onAdded(); setQ(""); }
    catch (e: any) { Alert.alert("Add failed", e?.response?.data?.detail || e?.message); setBusy(""); }
  };
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.addWrap} testID="add-asset-modal">
        <View style={styles.addCard}>
          <View style={styles.addHeader}>
            <Text style={type.h3}>Add to Active Watchlist</Text>
            <Pressable testID="add-asset-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          <View style={styles.addSearch}>
            <Ionicons name="search" size={15} color={colors.textFaint} />
            <TextInput testID="add-asset-search" value={q} onChangeText={setQ} autoFocus placeholder="Search any crypto — BTC, DOGE, SUI…"
              placeholderTextColor={colors.textFaint} style={{ flex: 1, color: colors.text, fontSize: 14, padding: 0 }} />
          </View>
          <ScrollView style={{ maxHeight: 320 }}>
            {results.length === 0 ? <Text style={[type.small, { padding: spacing.md }]}>No matches.</Text> : results.map((r) => (
              <Pressable key={r.symbol} testID={`add-asset-option-${r.symbol.replace("/", "-")}`} onPress={() => add(r.symbol)} disabled={!!busy} style={styles.addRow}>
                <Text style={[type.body, { fontWeight: "700" }]}>{r.symbol} <Text style={{ color: colors.textMuted, fontWeight: "400" }}>· {r.name}</Text></Text>
                {busy === r.symbol ? <ActivityIndicator color={colors.teal} size="small" /> : <Ionicons name="add" size={16} color={colors.teal} />}
              </Pressable>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
function CoachBanner() {
  const router = useRouter();
  const [h, setH] = useState<any>(null);
  useEffect(() => { api.coachHeadline().then(setH).catch(() => {}); }, []);
  if (!h) return null;
  return (
    <View style={styles.sectionPad}>
      <Pressable
        testID="coach-banner"
        onPress={() => router.push("/research?sub=ai")}
        style={({ pressed }) => [styles.coachCard, pressed && { borderColor: colors.teal }]}
      >
        <View style={styles.coachIcon}>
          <Ionicons name="sparkles" size={16} color={colors.teal} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.coachTag}>AI TRADING COACH</Text>
          <Text style={styles.coachHeadline} numberOfLines={2}>
            {h.headline}
            {h.impact ? <Text style={{ color: colors.teal }}>{`  ·  ${h.impact}`}</Text> : null}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  coachCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.tealGlow,
    borderWidth: 1,
    borderColor: "rgba(20,224,201,0.3)",
    borderRadius: radius.md,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
  },
  coachIcon: {
    width: 30,
    height: 30,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(20,224,201,0.15)",
  },
  coachTag: { color: colors.teal, fontSize: 9, fontWeight: "800", letterSpacing: 1 },
  coachHeadline: { color: colors.text, fontSize: 13, fontWeight: "600", marginTop: 2 },
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
  addBtn: { width: 30, height: 30, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center" },
  addWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  addCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingBottom: 30 },
  addHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.cardBorder },
  addSearch: { flexDirection: "row", alignItems: "center", gap: 8, margin: spacing.md, paddingHorizontal: spacing.md, paddingVertical: 10, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, backgroundColor: colors.bgElevated },
  addRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: 12, borderTopWidth: 1, borderTopColor: colors.cardBorder },
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
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  metricCell: { width: "48%", flexGrow: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md },
  metricValue: { color: colors.text, fontSize: 22, fontWeight: "800", marginTop: 2 },
  regimeCell: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.md, marginTop: spacing.sm },
  dualRow: { flexDirection: "row", gap: spacing.sm },
  halfBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: radius.md, paddingVertical: 13 },
  halfPrimary: { backgroundColor: colors.teal },
  halfPrimaryTxt: { color: colors.bg, fontWeight: "800", fontSize: 14 },
  halfGhost: { borderWidth: 1, borderColor: colors.tealDim },
  halfGhostTxt: { color: colors.teal, fontWeight: "700", fontSize: 13 },
  modalWrap: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, padding: spacing.lg },
});
