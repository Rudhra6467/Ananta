import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, RefreshControl, Pressable, Modal, TextInput } from "react-native";
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
import { pct } from "../../src/format";

const STATUS_TONE: Record<string, any> = { LIVE: "teal", PAPER: "amber", DISABLED: "muted", CATALOG: "neutral", WIRED: "teal" };
const GRADE_COLOR: Record<string, string> = { A: colors.teal, B: colors.teal, C: colors.amber, D: colors.amber, E: colors.red };
const healthColor = (v: number) => (v >= 60 ? colors.teal : v >= 35 ? colors.amber : colors.red);

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
  useEffect(() => { load(); }, [load]);

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
          <Text style={[type.small, { marginBottom: spacing.md }]}>Create a new strategy — import from another platform, write your own, or design one with AI. New strategies appear under Deployed once saved.</Text>
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
      ) : lib.map((s: any) => {
        const r = s.historical_results || {};
        const status = s.internal ? "LIVE" : (s.wireable ? "WIRED" : "CATALOG");
        return (
          <Card key={s.id} testID={`library-card-${s.id}`} onPress={() => open(s)} style={{ marginBottom: spacing.sm }}>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={type.h3} numberOfLines={1}>{s.name}</Text>
                <Text style={[type.small, { marginTop: 2 }]}>{s.style} · {s.source}</Text>
              </View>
              <View style={[styles.gradeBadge, { borderColor: GRADE_COLOR[s.ai_grade] || colors.amber }]}>
                <Text style={[styles.gradeTxt, { color: GRADE_COLOR[s.ai_grade] || colors.amber }]}>{s.ai_grade}</Text>
              </View>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 3, marginTop: 4 }}>
              {[1, 2, 3, 4, 5].map((n) => <Ionicons key={n} name={n <= s.rating ? "star" : "star-outline"} size={11} color={n <= s.rating ? colors.amber : colors.textFaint} />)}
              <View style={{ flex: 1 }} />
              <Pill label={s.internal ? "LIVE ENGINE" : status} tone={STATUS_TONE[status] || "muted"} />
            </View>
            <View style={[styles.rowBetween, { marginTop: spacing.sm }]}>
              <Stat label="ROI" value={pct(r.roi)} color={r.roi >= 0 ? colors.teal : colors.red} />
              <Stat label="HEALTH" value={String(s.ai_health_score)} color={healthColor(s.ai_health_score)} />
              <Stat label="WIN" value={`${r.win_rate}%`} />
              <Stat label="SHARPE" value={String(r.sharpe)} />
            </View>
          </Card>
        );
      })}
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

function StrategyLeaderboard({ onOpen }: { onOpen: (r: any) => void }) {
  const [sort, setSort] = useState("ai_health_score");
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.analyticsLeaderboard(sort).then(setData).catch(() => {}); }, [sort]);
  const opts = data?.sort_options || Object.keys(LB_LABELS);
  const rows = (data?.leaderboard || []).slice(0, 6);
  const fmt = (k: string, v: any) => (k === "net_pnl" ? `$${(v || 0).toLocaleString()}` : ["roi", "win_rate", "max_drawdown"].includes(k) ? `${v}%` : String(v));
  return (
    <Card testID="strategy-leaderboard" style={{ marginBottom: spacing.sm }}>
      <View style={styles.rowBetween}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Ionicons name="podium" size={15} color={colors.teal} />
          <Text style={type.label}>LEADERBOARD</Text>
        </View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: spacing.sm }}>
        {opts.map((o: string) => (
          <Pressable key={o} testID={`leaderboard-sort-${o}`} onPress={() => setSort(o)} style={[styles.sortChip, sort === o && styles.chipActive]}>
            <Text style={[styles.facetTxt, sort === o && { color: colors.teal }]}>{LB_LABELS[o] || o}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {rows.map((r: any) => (
        <Pressable key={r.key} testID={`leaderboard-row-${r.key}`} onPress={() => onOpen(r)} style={styles.lbRow}>
          <Text style={[type.small, { width: 24, color: colors.textFaint }]}>#{r.rank}</Text>
          <Text style={[type.body, { flex: 1, fontWeight: "600" }]} numberOfLines={1}>{r.name}</Text>
          <View style={[styles.gradeBadge, { borderColor: GRADE_COLOR[r.ai_grade] || colors.amber, marginRight: 8 }]}>
            <Text style={[styles.gradeTxt, { color: GRADE_COLOR[r.ai_grade] || colors.amber }]}>{r.ai_grade}</Text>
          </View>
          <Text style={[type.body, { fontWeight: "800", color: colors.teal, minWidth: 64, textAlign: "right" }]}>{fmt(sort, r[sort])}</Text>
        </Pressable>
      ))}
    </Card>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={{ alignItems: "flex-start" }}>
      <Text style={type.label}>{label}</Text>
      <Text style={[type.h3, { fontSize: 15, color: color || colors.text }]}>{value}</Text>
    </View>
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
});
