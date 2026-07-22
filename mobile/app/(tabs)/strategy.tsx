import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, RefreshControl, Pressable, Modal, TextInput, Alert, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Pill } from "../../src/components/Pill";
import { PageHeader } from "../../src/components/PageHeader";
import { AddStrategySheet } from "../../src/components/AddStrategySheet";
import { FirstVisitTip } from "../../src/components/FirstVisitTip";
import { colors, spacing, type, radius } from "../../src/theme";

// A strategy counts as "live" (running in paper or live) when enabled and not off/errored —
// same rule the Research tab uses.
const isLiveMetric = (m: any) => !!m && !!m.enabled && m.status !== "DISABLED" && m.status !== "ERROR";

const FILTER_FIELDS = [
  { key: "market_regime", label: "Market Regime" },
  { key: "style", label: "Trading Style" },
  { key: "timeframe", label: "Timeframe" },
  { key: "risk", label: "Risk Level" },
  { key: "ai_grade", label: "AI Grade" },
  { key: "source", label: "Source" },
];

const CATEGORY_ICON = (s: any): any => {
  const t = `${s.category || ""} ${s.style || ""}`.toLowerCase();
  if (s.engine_key === "hunter") return "trending-up";
  if (s.engine_key === "squeeze") return "flash";
  if (s.engine_key === "continuation") return "pulse";
  if (t.includes("mean revers")) return "swap-vertical-outline";
  if (t.includes("breakout") || t.includes("volatil")) return "flash-outline";
  if (t.includes("momentum")) return "rocket-outline";
  if (t.includes("trend")) return "trending-up-outline";
  if (t.includes("scalp")) return "timer-outline";
  return "cube-outline";
};

function timeAgo(ts: any): string | null {
  if (!ts) return null;
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (isNaN(d)) return null;
  if (d < 3600) return `${Math.max(1, Math.floor(d / 60))}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export default function StrategyLibrary() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [lib, setLib] = useState<any[] | null>(null);
  const [facets, setFacets] = useState<Record<string, string[]>>({});
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [favOnly, setFavOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [showFilter, setShowFilter] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [metrics, setMetrics] = useState<Record<string, any>>({});

  const activeCount = Object.values(filters).reduce((n, v) => n + v.length, 0) + (favOnly ? 1 : 0);

  const load = useCallback(() => {
    const params: Record<string, any> = {};
    if (query.trim()) params.q = query.trim();
    if (favOnly) params.favorite = true;
    Object.entries(filters).forEach(([k, v]) => { if (v.length) params[k] = v.join(","); });
    return api.libraryList(params).then((d: any) => setLib(d.strategies || [])).catch(() => setLib([]));
  }, [query, favOnly, filters]);

  const loadMetrics = useCallback(() => api.strategyMetrics().then((d: any) => setMetrics(d.metrics || {})).catch(() => {}), []);

  useEffect(() => { api.libraryFacets().then(setFacets).catch(() => {}); }, []);
  useEffect(() => { loadMetrics(); }, [loadMetrics]);
  useEffect(() => { load(); }, [load]);
  // Refetch when the tab regains focus so a state change made on the detail screen
  // (e.g. disabling a strategy) is reflected immediately — fixes the "disable twice" bug.
  useFocusEffect(useCallback(() => { load(); loadMetrics(); }, [load, loadMetrics]));

  const onRefresh = () => { setRefreshing(true); Promise.all([load(), loadMetrics()]).finally(() => setRefreshing(false)); };
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
      <FirstVisitTip tipKey="strategy" text="Tap a card to open a strategy. Use + to import, copy or build one. Filter to find an edge." />

      <View style={styles.searchRow}>
        <View style={styles.searchWrap}>
          <Ionicons name="search" size={16} color={colors.textFaint} />
          <TextInput testID="library-search" value={query} onChangeText={setQuery} placeholder="Search the library…"
            placeholderTextColor={colors.textFaint} style={styles.searchInput} />
          {query.length > 0 && (
            <Pressable testID="library-search-clear" onPress={() => setQuery("")} hitSlop={8}><Ionicons name="close-circle" size={16} color={colors.textFaint} /></Pressable>
          )}
        </View>
        <Pressable testID="filter-button" onPress={() => setShowFilter(true)} style={[styles.filterBtn, activeCount > 0 && styles.chipActive]}>
          <Ionicons name="options-outline" size={16} color={activeCount ? colors.teal : colors.textMuted} />
          {activeCount > 0 && <Text style={styles.filterCount}>{activeCount}</Text>}
        </Pressable>
      </View>

      {lib === null ? (
        <View style={styles.loadingBox} testID="strategy-center-loading">
          <ActivityIndicator color={colors.teal} />
          <Text style={[type.small, { marginTop: spacing.sm }]}>Loading library…</Text>
        </View>
      ) : lib.length === 0 ? (
        <View style={styles.emptyBox} testID="library-empty">
          <Text style={type.body}>No strategies match these filters.</Text>
          <Pressable onPress={clearFilters} testID="library-clear"><Text style={{ color: colors.teal, marginTop: 6, fontWeight: "700" }}>Clear filters</Text></Pressable>
        </View>
      ) : (
        (() => {
          const metricOf = (s: any) => (s.internal || s.wireable) ? metrics?.[s.engine_key] : null;
          const deployed = lib.filter((s: any) => isLiveMetric(metricOf(s)));
          const rest = lib.filter((s: any) => !isLiveMetric(metricOf(s)));
          const Section = ({ label, items }: { label: string; items: any[] }) => items.length === 0 ? null : (
            <View style={{ marginBottom: spacing.md }}>
              <Text style={styles.sectionHdr}>{label} · {items.length}</Text>
              <View style={styles.grid}>
                {items.map((s: any) => (
                  <StrategyCard key={s.id} s={s} metric={metricOf(s)} isOwner={isOwner} onOpen={() => open(s)} onReload={() => { load(); loadMetrics(); }} />
                ))}
              </View>
            </View>
          );
          return (
            <View testID="strategy-grid">
              <Section label="LIVE / PAPER" items={deployed} />
              <Section label="TEST & EDIT" items={rest} />
            </View>
          );
        })()
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
                <Text style={[styles.facetTxt, favOnly && { color: colors.teal }]}>Favorites only</Text>
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
    <AddStrategySheet visible={addOpen} onClose={() => setAddOpen(false)} onCloned={load} />
    </View>
  );
}

function StrategyCard({ s, metric, isOwner, onOpen, onReload }: { s: any; metric: any; isOwner: boolean; onOpen: () => void; onReload: () => void }) {
  const [busy, setBusy] = useState(false);
  const [localStatus, setLocalStatus] = useState<string | null>(null);
  const wired = !!(s.internal || (s.wireable && s.engine_key));
  const status = localStatus || (wired ? (metric?.status || "PAPER") : "CATALOG");
  const deployed = status === "PAPER" || status === "LIVE";
  // Binary "live" indicator matching the Research tab (enabled & not off/errored).
  const live = wired && (localStatus ? (localStatus === "PAPER" || localStatus === "LIVE") : isLiveMetric(metric));

  const last = metric?.last_trade ? timeAgo(metric.last_trade) : null;
  const activity = wired
    ? (metric?.trades ? `${metric.trades} trade${metric.trades === 1 ? "" : "s"}${last ? ` · last ${last}` : ""}` : "No trades yet")
    : (s.style || s.category || "Catalog");

  const deploy = async () => {
    if (deployed) return onOpen();
    if (!isOwner) return Alert.alert("Owner login required", "Log in as the owner to deploy strategies.");
    setBusy(true);
    try {
      const n = await api.strategySetState(s.engine_key, "PAPER");
      setLocalStatus(n?.status || "PAPER");
      onReload();
    } catch (e: any) { Alert.alert("Deploy failed", e?.response?.data?.detail || e?.message); }
    finally { setBusy(false); }
  };

  return (
    <Pressable testID={`library-card-${s.id}`} onPress={onOpen} style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}>
      <View style={styles.cardTop}>
        <View style={styles.cardIconBox}><Ionicons name={CATEGORY_ICON(s)} size={18} color={colors.teal} /></View>
        <View style={styles.cardTopRight}>
          {!s.reference_only && (
            <Pressable testID={`card-edit-${s.id}`} onPress={onOpen} hitSlop={8}>
              <Ionicons name="pencil" size={15} color={colors.textMuted} />
            </Pressable>
          )}
          {wired ? (
            <View testID={`card-status-${s.id}`}><Pill label={live ? "LIVE ON" : "LIVE OFF"} tone={live ? "teal" : "muted"} dot /></View>
          ) : null}
        </View>
      </View>

      <Text style={[type.h3, { fontSize: 16, marginTop: spacing.sm }]} numberOfLines={1}>{s.name}</Text>
      <Text style={styles.cardDesc} numberOfLines={2}>{s.description || s.ideal_market || "—"}</Text>
      <Text style={styles.cardActivity} numberOfLines={1}>{activity}</Text>

      {!wired && s.reference_only ? (
        <View testID={`card-reference-note-${s.id}`} style={styles.referenceNote}>
          <Text style={styles.referenceNoteTxt}>{s.reference_note || "Analysis only"}</Text>
        </View>
      ) : wired ? (
        <Pressable testID={`card-deploy-${s.id}`} onPress={deploy} disabled={busy}
          style={[styles.cardAction, deployed ? styles.cardActionGhost : styles.cardActionPrimary]}>
          {busy ? <ActivityIndicator color={deployed ? colors.teal : colors.bg} size="small" /> : (
            <>
              <Ionicons name="power" size={13} color={deployed ? colors.teal : colors.bg} />
              <Text style={[styles.cardActionTxt, { color: deployed ? colors.teal : colors.bg }]}>{deployed ? "MANAGE" : "DEPLOY"}</Text>
            </>
          )}
        </Pressable>
      ) : (
        <View style={[styles.cardAction, styles.cardActionGhost]}>
          <Text style={[styles.cardActionTxt, { color: colors.textMuted }]}>VIEW</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  sectionHdr: { color: colors.textMuted, fontSize: 11, fontWeight: "800", letterSpacing: 1, marginBottom: spacing.sm, textTransform: "uppercase" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  addHeaderBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center" },
  searchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },
  searchWrap: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 10 },
  searchInput: { flex: 1, color: colors.text, fontSize: 14, padding: 0 },
  filterBtn: { flexDirection: "row", alignItems: "center", gap: 5, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 11 },
  filterCount: { color: colors.teal, fontSize: 12, fontWeight: "800" },
  chipActive: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  loadingBox: { alignItems: "center", paddingVertical: spacing.xl },
  emptyBox: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  card: { width: "48%", flexGrow: 1, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.lg, padding: spacing.md, minHeight: 178 },
  cardPressed: { backgroundColor: colors.cardPressed, transform: [{ scale: 0.99 }] },
  cardTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  cardTopRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  cardIconBox: { width: 38, height: 38, borderRadius: radius.md, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center" },
  cardDesc: { color: colors.textMuted, fontSize: 12, lineHeight: 17, marginTop: 4, minHeight: 34 },
  cardActivity: { color: colors.textFaint, fontSize: 10, fontWeight: "600", marginTop: 6 },
  cardAction: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: radius.md, paddingVertical: 9, marginTop: spacing.sm },
  cardActionPrimary: { backgroundColor: colors.teal },
  cardActionGhost: { borderWidth: 1, borderColor: colors.cardBorder },
  cardActionTxt: { fontWeight: "800", letterSpacing: 0.6, fontSize: 11 },
  referenceNote: { marginTop: spacing.sm, borderWidth: 1, borderStyle: "dashed", borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: 8, paddingHorizontal: 10, alignItems: "center" },
  referenceNoteTxt: { color: colors.textFaint, fontSize: 9, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5 },
  facetWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  facetChip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: 999, paddingHorizontal: spacing.sm, paddingVertical: 5 },
  facetTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
  favBtn: { flexDirection: "row", alignItems: "center", gap: 8, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  drawerWrap: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" },
  drawer: { backgroundColor: colors.bg, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, maxHeight: "85%" },
  drawerBtn: { flex: 1, alignItems: "center", paddingVertical: 12, borderRadius: radius.sm, borderWidth: 1 },
});
