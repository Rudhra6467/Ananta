import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, RefreshControl, Pressable, Modal, TextInput, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { PageHeader } from "../../src/components/PageHeader";
import { AddStrategySheet } from "../../src/components/AddStrategySheet";
import { Segmented } from "../../src/components/Segmented";
import { FirstVisitTip } from "../../src/components/FirstVisitTip";
import { colors, spacing, type, radius } from "../../src/theme";

const STATUS_TONE: Record<string, any> = { LIVE: "teal", PAPER: "amber", DISABLED: "muted", CATALOG: "neutral", WIRED: "teal" };
const GRADE_COLOR: Record<string, string> = { A: colors.teal, B: colors.teal, C: colors.amber, D: colors.amber, E: colors.red };

const CHIPS = [
  { id: "top_rated", label: "Top Rated", icon: "star" },
  { id: "top_internal", label: "Top Internal", icon: "hardware-chip" },
  { id: "healthiest", label: "Healthiest", icon: "heart" },
  { id: "trending", label: "Trending", icon: "flame" },
];
const FILTER_FIELDS = [
  { key: "market_regime", label: "Market Regime" },
  { key: "style", label: "Trading Style" },
  { key: "timeframe", label: "Timeframe" },
  { key: "risk", label: "Risk Level" },
  { key: "ai_grade", label: "AI Grade" },
  { key: "source", label: "Source" },
];

export default function StrategyLibrary() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [lib, setLib] = useState<any[] | null>(null);
  const [facets, setFacets] = useState<Record<string, string[]>>({});
  const [chip, setChip] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [favOnly, setFavOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [showFilter, setShowFilter] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sub, setSub] = useState("deployed");
  const [metrics, setMetrics] = useState<Record<string, any>>({});

  const activeCount = Object.values(filters).reduce((n, v) => n + v.length, 0) + (favOnly ? 1 : 0);

  const load = useCallback(() => {
    const params: Record<string, any> = {};
    if (chip) params.chip = chip;
    if (query.trim()) params.q = query.trim();
    if (favOnly) params.favorite = true;
    Object.entries(filters).forEach(([k, v]) => { if (v.length) params[k] = v.join(","); });
    return api.libraryList(params).then((d: any) => setLib(d.strategies || [])).catch(() => setLib([]));
  }, [chip, query, favOnly, filters]);

  useEffect(() => { api.libraryFacets().then(setFacets).catch(() => {}); }, []);
  useEffect(() => { api.strategyMetrics().then((d: any) => setMetrics(d.metrics || {})).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);

  const statusOf = (s: any) => metrics?.[s.engine_key]?.status || (s.internal ? "LIVE" : s.reference_only ? "CATALOG" : "DISABLED");

  const onRefresh = () => { setRefreshing(true); load().finally(() => setRefreshing(false)); };
  const toggleFilter = (field: string, val: string) => setFilters((f) => {
    const cur = f[field] || [];
    return { ...f, [field]: cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val] };
  });
  const clearFilters = () => { setFilters({}); setFavOnly(false); };

  const open = (s: any) => router.push(s.internal ? `/strategy/${s.engine_key}` : `/library/${s.id}`);

  return (
    <View style={styles.fill}>
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.teal} />}>
      <PageHeader title="Strategy Center" question="What do I own?" right={
        isOwner ? (
          <Pressable testID="strategy-add-btn" accessibilityLabel="Add Strategy" onPress={() => setAddOpen(true)} style={styles.addHeaderBtn}>
            <Ionicons name="add" size={24} color={colors.bg} />
          </Pressable>
        ) : undefined
      } />
      <FirstVisitTip tipKey="strategy" text="Tap + to import or build a strategy. Filter and sort the leaderboard to find an edge." />

      <View style={{ marginBottom: spacing.sm }}>
        <Segmented testIDPrefix="strategy-subtab"
          options={[{ key: "deployed", label: "DEPLOYED" }, { key: "edit", label: "EDIT" }]}
          value={sub} onChange={setSub} />
      </View>

      {sub === "edit" ? (
        <View testID="strategy-edit-grid">
          <Text style={[type.small, { marginBottom: spacing.sm }]}>Edit an existing strategy — pick one to open its details, then test it.</Text>
          {(lib || []).length > 0 && (
            <View style={styles.editExistingCard} testID="edit-existing-list">
              {(lib || []).map((s: any) => (
                <Pressable key={s.id} testID={`edit-existing-${s.id}`} onPress={() => open(s)} style={styles.editExistingRow}>
                  <Ionicons name="pulse-outline" size={16} color={colors.teal} />
                  <Text style={[type.body, { flex: 1 }]} numberOfLines={1}>{s.name}{s.internal ? "  · Live" : ""}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
                </Pressable>
              ))}
            </View>
          )}
          <Text style={[type.small, { marginBottom: spacing.md }]}>Or create a new strategy — import, write your own, or design one with AI. New strategies appear under Deployed once saved.</Text>
          {[{ id: "import", icon: "cloud-upload-outline", title: "Import Strategy", desc: "Pine · Freqtrade · Jesse · JSON" },
            { id: "write", icon: "code-slash-outline", title: "Write Strategy", desc: "Author rules in the builder" },
            { id: "ai", icon: "sparkles-outline", title: "Describe & Build (AI)", desc: "Design a strategy conversationally" }].map((t) => (
            <Pressable key={t.id} testID={`edit-tool-${t.id}`} onPress={() => setAddOpen(true)} style={styles.editTool}>
              <View style={styles.editToolIcon}><Ionicons name={t.icon as any} size={20} color={colors.teal} /></View>
              <View style={{ flex: 1 }}>
                <Text style={[type.body, { fontWeight: "700" }]}>{t.title}</Text>
                <Text style={type.small}>{t.desc}</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </Pressable>
          ))}
        </View>
      ) : (
        <>
      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.textFaint} />
        <TextInput testID="library-search" value={query} onChangeText={setQuery} placeholder="Search the library…"
          placeholderTextColor={colors.textFaint} style={styles.searchInput} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.sm }}>
        {CHIPS.map((c) => (
          <Pressable key={c.id} testID={`chip-${c.id}`} onPress={() => setChip(chip === c.id ? null : c.id)}
            style={[styles.chip, chip === c.id && styles.chipActive]}>
            <Ionicons name={c.icon as any} size={12} color={chip === c.id ? colors.teal : colors.textMuted} />
            <Text style={[styles.chipTxt, chip === c.id && { color: colors.teal }]}>{c.label}</Text>
          </Pressable>
        ))}
        <Pressable testID="filter-button" onPress={() => setShowFilter(true)} style={[styles.chip, activeCount > 0 && styles.chipActive]}>
          <Ionicons name="options" size={12} color={activeCount ? colors.teal : colors.textMuted} />
          <Text style={[styles.chipTxt, activeCount > 0 && { color: colors.teal }]}>Filter{activeCount ? ` · ${activeCount}` : ""}</Text>
        </Pressable>
      </ScrollView>

      <StrategyLeaderboard onOpen={open} />

      {lib === null ? (
        <Text style={[type.small, { marginTop: spacing.md }]}>Loading library…</Text>
      ) : lib.length === 0 ? (
        <Card style={{ marginTop: spacing.md, alignItems: "center" }}>
          <Text style={type.body}>No strategies match these filters.</Text>
          <Pressable onPress={clearFilters} testID="library-clear"><Text style={{ color: colors.teal, marginTop: 6, fontWeight: "700" }}>Clear filters</Text></Pressable>
        </Card>
      ) : lib.map((s: any) => (
        <StrategyCard key={s.id} s={s} status={statusOf(s)} isOwner={isOwner} onOpen={() => open(s)} onReload={load} />
      ))}
        </>
      )}

      <Modal visible={showFilter} transparent animationType="slide" onRequestClose={() => setShowFilter(false)}>
        <View style={styles.drawerWrap}>
          <View style={[styles.drawer, { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.md }]}>
            <View style={styles.rowBetween}>
              <Text style={type.h2}>Filters{activeCount ? ` · ${activeCount}` : ""}</Text>
              <Pressable testID="filter-close" onPress={() => setShowFilter(false)} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <ScrollView style={{ marginTop: spacing.md }} contentContainerStyle={{ gap: spacing.md }}>
              <Pressable testID="filter-favorites" onPress={() => setFavOnly((v) => !v)} style={[styles.favBtn, favOnly && styles.chipActive]}>
                <Ionicons name={favOnly ? "heart" : "heart-outline"} size={16} color={favOnly ? colors.teal : colors.textMuted} />
                <Text style={[styles.chipTxt, favOnly && { color: colors.teal }]}>Favorites only</Text>
              </Pressable>
              {FILTER_FIELDS.map(({ key, label }) => (
                <View key={key}>
                  <Text style={type.label}>{label.toUpperCase()}</Text>
                  <View style={styles.facetWrap}>
                    {(facets[key] || []).map((val) => {
                      const active = (filters[key] || []).includes(val);
                      return (
                        <Pressable key={val} testID={`filter-${key}-${val}`} onPress={() => toggleFilter(key, val)}
                          style={[styles.facetChip, active && styles.chipActive]}>
                          <Text style={[styles.facetTxt, active && { color: colors.teal }]}>{val}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
              ))}
            </ScrollView>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
              <Pressable testID="filter-clear" onPress={clearFilters} style={[styles.drawerBtn, { borderColor: colors.cardBorder }]}><Text style={{ color: colors.textMuted, fontWeight: "700" }}>Clear</Text></Pressable>
              <Pressable testID="filter-apply" onPress={() => setShowFilter(false)} style={[styles.drawerBtn, { backgroundColor: colors.teal, borderColor: colors.teal }]}><Text style={{ color: colors.bg, fontWeight: "800" }}>Show results</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
    <AddStrategySheet visible={addOpen} onClose={() => setAddOpen(false)} />
    </View>
  );
}

const LB_LABELS: Record<string, string> = {
  net_pnl: "Net P&L", roi: "ROI", win_rate: "Win Rate", ai_health_score: "AI Health",
  sharpe: "Sharpe", sortino: "Sortino", profit_factor: "Profit Factor",
  max_drawdown: "Max DD", avg_trade: "Avg Trade", trades: "Trades", rating: "Rating",
};

const CARD_ICON = (s: any): any => {
  const t = `${s.category || ""} ${s.style || ""}`.toLowerCase();
  if (t.includes("mean revers")) return "trending-up-outline";
  if (t.includes("breakout") || t.includes("volatil")) return "flash-outline";
  if (t.includes("momentum")) return "rocket-outline";
  if (t.includes("trend")) return "pulse-outline";
  if (t.includes("scalp")) return "timer-outline";
  return "stats-chart-outline";
};

function StrategyCard({ s, status, isOwner, onOpen, onReload }: { s: any; status: string; isOwner: boolean; onOpen: () => void; onReload: () => void }) {
  const [busy, setBusy] = useState(false);
  const grade = s.ai_grade || "C";
  const gColor = GRADE_COLOR[grade] || colors.amber;
  const active = status === "LIVE" || status === "PAPER";
  const deployable = !s.reference_only && (s.internal || (s.wireable && s.engine_key));

  const primary = async () => {
    if (active || s.internal) return onOpen();  // manage an active / live-engine strategy
    if (!isOwner) return Alert.alert("Owner login required", "Log in as the owner to deploy strategies.");
    setBusy(true);
    try {
      const n = await api.strategySetState(s.engine_key, "PAPER");
      Alert.alert("Deployed", `${s.name} → ${n?.status || "PAPER"} engine.`);
      onReload();
    } catch (e: any) { Alert.alert("Deploy failed", e?.response?.data?.detail || e?.message); }
    finally { setBusy(false); }
  };

  return (
    <Card testID={`library-card-${s.id}`} style={styles.sCard}>
      <View style={styles.rowBetween}>
        <View style={styles.cardIconBox}><Ionicons name={CARD_ICON(s)} size={18} color={colors.teal} /></View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={[styles.gradeCircle, { borderColor: gColor }]}><Text style={[styles.gradeTxt, { color: gColor }]}>{grade}</Text></View>
          <Pill label={status} tone={STATUS_TONE[status] || "muted"} />
        </View>
      </View>

      <Pressable onPress={onOpen}>
        <Text style={[type.h3, { marginTop: spacing.sm }]} numberOfLines={1}>{s.name}</Text>
        <Text style={[type.small, { marginTop: 2 }]} numberOfLines={1}>{s.style} · {s.source}</Text>
        <Text style={[type.body, { marginTop: 6, color: colors.textMuted }]} numberOfLines={1}>{s.description || s.ideal_market || "—"}</Text>
      </Pressable>

      {s.reference_only ? (
        <View testID={`library-reference-note-${s.id}`} style={styles.referenceNote}>
          <Text style={styles.referenceNoteTxt}>{s.reference_note || "Analysis only"}</Text>
        </View>
      ) : (
        <View style={[styles.rowBetween, styles.actionRow]}>
          <Pressable testID={`card-edit-${s.id}`} onPress={onOpen} style={styles.editBtn} hitSlop={8}>
            <Ionicons name="create-outline" size={15} color={colors.textMuted} />
            <Text style={styles.editTxt}>Edit</Text>
          </Pressable>
          {deployable && (
            <Pressable testID={`card-deploy-${s.id}`} onPress={primary} disabled={busy} style={[styles.primaryBtn, active && styles.primaryBtnGhost]}>
              {busy ? <ActivityIndicator color={colors.bg} size="small" /> : <Text style={[styles.primaryTxt, active && { color: colors.teal }]}>{active ? "MANAGE" : "DEPLOY"}</Text>}
            </Pressable>
          )}
        </View>
      )}
    </Card>
  );
}

function StrategyLeaderboard({ onOpen }: { onOpen: (r: any) => void }) {
  const [sort, setSort] = useState("ai_health_score");
  const [data, setData] = useState<any>(null);
  const [showAll, setShowAll] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  useEffect(() => { api.analyticsLeaderboard(sort).then(setData).catch(() => {}); }, [sort]);
  const opts = data?.sort_options || Object.keys(LB_LABELS);
  const all = data?.leaderboard || [];
  const rows = showAll ? all.slice(0, 8) : all.slice(0, 2);
  const more = Math.max(0, Math.min(8, all.length) - 2);
  const fmt = (k: string, v: any) => (k === "net_pnl" ? `$${(v || 0).toLocaleString()}` : ["roi", "win_rate", "max_drawdown"].includes(k) ? `${v}%` : String(v));
  return (
    <Card testID="strategy-leaderboard" style={{ marginBottom: spacing.sm }}>
      <View style={styles.rowBetween}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Ionicons name="podium-outline" size={15} color={colors.teal} />
          <Text style={type.label}>STRATEGY LEADERBOARD</Text>
        </View>
        <Pressable testID="leaderboard-sort" onPress={() => setSortOpen(true)} style={styles.sortDropdown}>
          <Text style={styles.sortDropTxt}>Sort: {LB_LABELS[sort] || sort}</Text>
          <Ionicons name="chevron-down" size={13} color={colors.textMuted} />
        </Pressable>
      </View>
      {rows.map((r: any) => (
        <Pressable key={r.key} testID={`leaderboard-row-${r.key}`} onPress={() => onOpen(r)} style={styles.lbRow}>
          <Text style={[type.small, { width: 30, color: colors.textFaint }]}>#{r.rank}</Text>
          <Text style={[type.body, { flex: 1, fontWeight: "600" }]} numberOfLines={1}>{r.name}</Text>
          <View style={[styles.gradeCircle, { borderColor: GRADE_COLOR[r.ai_grade] || colors.amber, marginRight: 10 }]}>
            <Text style={[styles.gradeTxt, { color: GRADE_COLOR[r.ai_grade] || colors.amber }]}>{r.ai_grade}</Text>
          </View>
          <Text style={[type.body, { fontWeight: "800", minWidth: 44, textAlign: "right" }]}>{fmt(sort, r[sort])}</Text>
        </Pressable>
      ))}
      {more > 0 && (
        <Pressable testID="leaderboard-showmore" onPress={() => setShowAll((v) => !v)} style={styles.showMore}>
          <Text style={styles.showMoreTxt}>{showAll ? "Show less" : `Show more (${more})`}</Text>
        </Pressable>
      )}

      <Modal visible={sortOpen} transparent animationType="fade" onRequestClose={() => setSortOpen(false)}>
        <Pressable style={styles.sortModalWrap} onPress={() => setSortOpen(false)}>
          <View style={styles.sortModalCard}>
            <Text style={[type.label, { marginBottom: spacing.sm }]}>SORT BY</Text>
            {opts.map((o: string) => (
              <Pressable key={o} testID={`leaderboard-sort-${o}`} onPress={() => { setSort(o); setSortOpen(false); }} style={styles.sortOpt}>
                <Text style={[type.body, { color: sort === o ? colors.teal : colors.text }]}>{LB_LABELS[o] || o}</Text>
                {sort === o && <Ionicons name="checkmark" size={16} color={colors.teal} />}
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10, marginBottom: 4 },
  searchInput: { flex: 1, color: colors.text, fontSize: 14, padding: 0 },
  chip: { flexDirection: "row", alignItems: "center", gap: 5, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm + 2, paddingVertical: 7 },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  importChip: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  chipTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  addHeaderBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center" },
  gradeBadge: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, minWidth: 22, alignItems: "center" },
  gradeCircle: { width: 24, height: 24, borderRadius: 12, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  sCard: { marginBottom: spacing.sm },
  cardIconBox: { width: 40, height: 40, borderRadius: radius.md, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center" },
  metricsBox: { marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  actionRow: { marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  editBtn: { flexDirection: "row", alignItems: "center", gap: 5 },
  editTxt: { color: colors.textMuted, fontSize: 13, fontWeight: "600" },
  detailsBtn: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.md, paddingVertical: 7 },
  detailsTxt: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  primaryBtn: { backgroundColor: colors.teal, borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 9, minWidth: 92, alignItems: "center", justifyContent: "center" },
  primaryBtnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.teal + "66" },
  primaryTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.6, fontSize: 13 },
  sortDropdown: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm + 2, paddingVertical: 6 },
  sortDropTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "700" },
  showMore: { alignItems: "center", paddingVertical: spacing.sm + 2, borderTopWidth: 1, borderTopColor: colors.cardBorder, marginTop: 2 },
  showMoreTxt: { color: colors.teal, fontSize: 12, fontWeight: "700" },
  sortModalWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "center", padding: spacing.xl },
  sortModalCard: { backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.lg },
  sortOpt: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 11 },
  referenceNote: { marginTop: spacing.sm, borderWidth: 1, borderStyle: "dashed", borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: 8, paddingHorizontal: 10, alignItems: "center" },
  referenceNoteTxt: { color: colors.textFaint, fontSize: 10, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5 },
  gradeTxt: { fontSize: 10, fontWeight: "800" },
  sortChip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm, paddingVertical: 5 },
  lbRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  facetWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  facetChip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm, paddingVertical: 5 },
  facetTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
  favBtn: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  drawerWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  drawer: { backgroundColor: colors.bg, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, maxHeight: "85%" },
  drawerBtn: { flex: 1, alignItems: "center", paddingVertical: 12, borderRadius: radius.sm, borderWidth: 1 },
  editTool: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  editToolIcon: { width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: colors.tealGlow, borderWidth: 1, borderColor: colors.tealDim },
  editExistingRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm + 2, paddingHorizontal: spacing.sm },
  editExistingCard: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.xs, marginBottom: spacing.md },
  deployBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: spacing.sm + 3, marginTop: spacing.md },
  deployBtnGhost: { backgroundColor: "transparent", borderWidth: 1, borderColor: colors.cardBorder },
  deployTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 0.8, fontSize: 13 },
});
