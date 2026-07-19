import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, Alert, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { Card, SectionLabel } from "../../src/components/Card";
import { Pill } from "../../src/components/Pill";
import { LoadingView } from "../../src/components/StateView";
import { colors, spacing, type, radius } from "../../src/theme";

const GRADE_COLOR: Record<string, string> = { A: colors.teal, B: colors.teal, C: colors.amber, D: colors.amber, E: colors.red };

export default function LibraryDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const [s, setS] = useState<any>(null);
  const [grading, setGrading] = useState(false);
  const [backtesting, setBacktesting] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [engineState, setEngineState] = useState<any>(null);
  const [renaming, setRenaming] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => api.libraryGet(id as string).then((d: any) => {
    if (d.internal && d.engine_key) { router.replace(`/strategy/${d.engine_key}`); return; }
    setS(d);
    if (d.wireable && d.engine_key) {
      api.strategyMetrics().then((m: any) => setEngineState(m?.metrics?.[d.engine_key] || null)).catch(() => {});
    }
  }).catch(() => setS(false));
  useEffect(() => { load(); }, [id]);

  const regrade = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setGrading(true);
    try { const g = await api.libraryAiGrade(id as string); Alert.alert("Re-graded", `${g.ai_grade} · ${g.ai_health_score}/100`); load(); }
    catch (e: any) { Alert.alert("AI grade failed", e?.response?.data?.detail || e?.message); }
    finally { setGrading(false); }
  };

  const runBacktest = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setBacktesting(true);
    try { const r = await api.libraryBacktest(id as string); Alert.alert("Backtest complete", `${r.historical_results.trade_count} trades · ROI ${r.historical_results.roi}% over ${r.days}d`); load(); }
    catch (e: any) { Alert.alert("Backtest failed", e?.response?.data?.detail || e?.message); }
    finally { setBacktesting(false); }
  };

  const toggleDeploy = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const on = !!engineState?.enabled;
    setDeploying(true);
    try {
      const next = on ? await api.strategyDisable(s.engine_key) : await api.strategyDeploy(s.engine_key);
      setEngineState((p: any) => ({ ...(p || {}), status: next.status, enabled: next.enabled }));
    } catch (e: any) { Alert.alert("Failed", e?.response?.data?.detail || e?.message); }
    finally { setDeploying(false); }
  };

  if (s === null) return <View style={styles.fill}><LoadingView /></View>;
  if (s === false) return <View style={styles.fill}><Text style={[type.body, { padding: spacing.lg }]}>Strategy not found.</Text></View>;
  const r = s.historical_results || {};
  const userAdded = !!(s.imported || s.origin === "clone");
  const deployed = !!engineState?.enabled;

  const saveRename = async () => {
    const name = nameInput.trim();
    if (!name || name === s.name) { setRenaming(false); return; }
    setSavingName(true);
    try { await api.libraryRename(id as string, name); setRenaming(false); load(); }
    catch (e: any) { Alert.alert("Rename failed", e?.response?.data?.detail || e?.message); }
    finally { setSavingName(false); }
  };

  const deleteStrategy = () => {
    if (deployed) return Alert.alert("Disable first", "This strategy is deployed. Disable it before deleting.");
    Alert.alert("Delete strategy?", `Delete "${s.name}" permanently? This removes the strategy and its saved parameters.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        setDeleting(true);
        try { await api.libraryDelete(id as string); router.back(); }
        catch (e: any) { Alert.alert("Delete failed", e?.response?.data?.detail || e?.message); setDeleting(false); }
      } },
    ]);
  };

  const testInLab = () => router.push(`/research?sub=validate&strat=${encodeURIComponent(s.engine_key)}`);

  return (
    <ScrollView style={styles.fill} testID="catalog-detail" contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}>
      <Pressable testID="catalog-back" onPress={() => router.back()} style={styles.back}>
        <Ionicons name="chevron-back" size={18} color={colors.teal} />
        <Text style={{ color: colors.teal, fontWeight: "700", fontSize: 12 }}>Library</Text>
      </Pressable>

      <Card style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View style={{ flex: 1, minWidth: 0 }}>
            {renaming ? (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <TextInput testID="catalog-rename-input" value={nameInput} onChangeText={setNameInput} autoFocus maxLength={80}
                  style={styles.renameInput} placeholderTextColor={colors.textFaint} />
                <Pressable testID="catalog-rename-save" onPress={saveRename} disabled={savingName} hitSlop={8}>
                  {savingName ? <ActivityIndicator size="small" color={colors.teal} /> : <Ionicons name="checkmark-circle" size={22} color={colors.teal} />}
                </Pressable>
                <Pressable testID="catalog-rename-cancel" onPress={() => setRenaming(false)} hitSlop={8}><Ionicons name="close-circle" size={22} color={colors.textMuted} /></Pressable>
              </View>
            ) : (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Text style={[type.h2, { flexShrink: 1 }]} numberOfLines={2}>{s.name}</Text>
                {userAdded && isOwner && (
                  <Pressable testID="catalog-rename-btn" onPress={() => { setNameInput(s.name || ""); setRenaming(true); }} hitSlop={8}>
                    <Ionicons name="pencil" size={15} color={colors.textMuted} />
                  </Pressable>
                )}
              </View>
            )}
            <Text style={[type.small, { marginTop: 2 }]}>{s.style} · {s.category} · {s.source}</Text>
          </View>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
            <View style={[styles.grade, { borderColor: GRADE_COLOR[s.ai_grade] || colors.amber }]}>
              <Text style={[styles.gradeTxt, { color: GRADE_COLOR[s.ai_grade] || colors.amber }]}>Grade {s.ai_grade}</Text>
            </View>
            <Pressable testID="catalog-favorite" onPress={() => api.libraryFavorite(id as string).then(load)} hitSlop={8}>
              <Ionicons name={s.favorite ? "heart" : "heart-outline"} size={22} color={s.favorite ? colors.teal : colors.textMuted} />
            </Pressable>
            {userAdded && isOwner && (
              <Pressable testID="catalog-delete-btn" onPress={deleteStrategy} disabled={deleting} hitSlop={8}>
                {deleting ? <ActivityIndicator size="small" color={colors.red} /> : <Ionicons name="trash-outline" size={20} color={colors.red} />}
              </Pressable>
            )}
          </View>
        </View>
        {s.origin === "clone" ? (
          <View testID="clone-badge" style={styles.importedBadge}>
            <Ionicons name="copy" size={11} color={colors.teal} />
            <Text style={{ color: colors.teal, fontSize: 10, fontWeight: "800" }}>COPY</Text>
          </View>
        ) : s.imported ? (
          <View testID="imported-badge" style={styles.importedBadge}>
            <Ionicons name="cloud-upload" size={11} color={colors.teal} />
            <Text style={{ color: colors.teal, fontSize: 10, fontWeight: "800" }}>IMPORTED · {s.source_label}</Text>
          </View>
        ) : null}
        <Text style={[type.body, { marginTop: spacing.sm, lineHeight: 20 }]}>{s.description}</Text>
        {s.wireable && s.engine_key && (
          <View style={styles.enginePanel}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <Ionicons name="flash" size={14} color={colors.teal} />
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: "600", flex: 1 }}>Live-executable in the paper engine</Text>
              <Pill label={engineState?.enabled ? (engineState.status || "PAPER") : "OFF"} tone={engineState?.enabled ? "teal" : "muted"} />
            </View>
            <View style={{ flexDirection: "row", gap: 8, marginTop: spacing.sm, flexWrap: "wrap" }}>
              <Pressable testID="catalog-deploy-toggle" onPress={toggleDeploy} disabled={!isOwner || deploying}
                style={[styles.engineBtn, engineState?.enabled ? { borderColor: colors.cardBorder } : { borderColor: colors.teal, backgroundColor: colors.tealGlow }, (!isOwner || deploying) && { opacity: 0.4 }]}>
                {deploying ? <ActivityIndicator size="small" color={colors.teal} /> : <Ionicons name="power" size={13} color={engineState?.enabled ? colors.textMuted : colors.teal} />}
                <Text style={[styles.engineBtnTxt, { color: engineState?.enabled ? colors.textMuted : colors.teal }]}>{engineState?.enabled ? "Disable" : "Deploy (Paper)"}</Text>
              </Pressable>
              <Pressable testID="catalog-backtest" onPress={runBacktest} disabled={!isOwner || backtesting}
                style={[styles.engineBtn, { borderColor: colors.cardBorder }, (!isOwner || backtesting) && { opacity: 0.4 }]}>
                {backtesting ? <ActivityIndicator size="small" color={colors.textMuted} /> : <Ionicons name="bar-chart" size={13} color={colors.textMuted} />}
                <Text style={[styles.engineBtnTxt, { color: colors.textMuted }]}>{backtesting ? "Backtesting…" : "Backtest"}</Text>
              </Pressable>
              <Pressable testID="catalog-test-lab" onPress={testInLab}
                style={[styles.engineBtn, { borderColor: colors.cardBorder }]}>
                <Ionicons name="shield-checkmark" size={13} color={colors.textMuted} />
                <Text style={[styles.engineBtnTxt, { color: colors.textMuted }]}>Test in Lab</Text>
              </Pressable>
              <Pressable testID="catalog-manage-engine" onPress={() => router.push(`/strategy/${s.engine_key}`)}
                style={[styles.engineBtn, { borderColor: colors.teal }]}>
                <Text style={[styles.engineBtnTxt, { color: colors.teal }]}>Manage →</Text>
              </Pressable>
            </View>
          </View>
        )}
        <View style={styles.tagWrap}>
          {(s.market_regimes || []).map((m: string) => <Pill key={m} label={m} tone="neutral" />)}
          <Pill label={s.risk} tone="neutral" />
          {(s.timeframes || []).map((t: string) => <Pill key={t} label={t} tone="neutral" />)}
        </View>
      </Card>

      <Card testID="catalog-ai" style={{ marginBottom: spacing.md }}>
        <View style={styles.rowBetween}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Ionicons name="sparkles" size={15} color={colors.teal} />
            <SectionLabel>AI ASSESSMENT</SectionLabel>
          </View>
          <Pressable testID="catalog-regrade" onPress={regrade} disabled={grading || !isOwner} style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: !isOwner ? 0.4 : 1 }}>
            {grading ? <ActivityIndicator color={colors.teal} size="small" /> : <Ionicons name="refresh" size={14} color={colors.teal} />}
            <Text style={{ color: colors.teal, fontSize: 11, fontWeight: "700" }}>Re-grade</Text>
          </Pressable>
        </View>
        <Text style={[type.body, { marginTop: spacing.sm, lineHeight: 20 }]}>{s.ai_summary}</Text>
        <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.sm }}>
          <Text style={type.small}>Health <Text style={{ color: colors.text, fontWeight: "800" }}>{s.ai_health_score}/100</Text></Text>
          <Text style={type.small}>Confidence <Text style={{ color: colors.text, fontWeight: "800" }}>{s.ai_confidence}%</Text></Text>
        </View>
      </Card>

      <Card style={{ marginBottom: spacing.md }}>
        <SectionLabel>BACKTEST PERFORMANCE</SectionLabel>
        {(r.roi === undefined || r.roi === null) ? (
          <Text style={[type.small, { marginTop: spacing.sm }]} testID="no-backtest">Not yet validated. Run a backtest or use Test in Lab to generate performance for this strategy.</Text>
        ) : (
          <>
            <Text style={[type.small, { marginBottom: spacing.sm }]}>Seeded — run a real backtest to validate.</Text>
            <View style={styles.perfGrid}>
              {[["ROI", `${r.roi}%`], ["Win Rate", `${r.win_rate}%`], ["Profit Factor", r.profit_factor], ["Sharpe", r.sharpe],
                ["Sortino", r.sortino], ["Max DD", `${r.max_drawdown}%`], ["Avg Trade", `${r.avg_trade}%`], ["Trades", r.trade_count]].map(([k, v]) => (
                <View key={String(k)} style={styles.perfCell}>
                  <Text style={type.label}>{String(k).toUpperCase()}</Text>
                  <Text style={[type.h3, { fontSize: 15 }]}>{String(v)}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </Card>

      <RuleList title="ENTRY RULES" items={s.entry_rules} tone={colors.teal} />
      <RuleList title="EXIT RULES" items={s.exit_rules} tone={colors.teal} />
      <RuleList title="IDEAL CONDITIONS" items={s.ideal_conditions} tone={colors.teal} />
      <RuleList title="AVOID CONDITIONS" items={s.avoid_conditions} tone={colors.red} />

      {s.imported && !!s.conversion_report && (
        <Card testID="catalog-import-meta" style={{ marginBottom: spacing.sm }}>
          <SectionLabel>IMPORT &amp; CONVERSION REPORT</SectionLabel>
          <Text style={[type.small, { marginTop: 4 }]}>{s.conversion_confidence}% conversion confidence</Text>
          <Text style={[type.body, { marginTop: 6, fontSize: 13, lineHeight: 19 }]}>{s.conversion_report}</Text>
        </Card>
      )}
      {s.imported && (s.indicators || []).length > 0 && (
        <Card style={{ marginBottom: spacing.sm }}>
          <SectionLabel>INDICATORS</SectionLabel>
          <View style={styles.tagWrap}>
            {s.indicators.map((ind: any, i: number) => (
              <View key={i} style={styles.indChip}>
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>
                  {ind.name}{ind.params && Object.keys(ind.params).length ? ` (${Object.entries(ind.params).map(([k, val]) => `${k}=${val}`).join(", ")})` : ""}
                </Text>
              </View>
            ))}
          </View>
        </Card>
      )}
      {s.imported && (s.strengths || []).length > 0 && <RuleList title="STRENGTHS" items={s.strengths} tone={colors.teal} />}
      {s.imported && (s.weaknesses || []).length > 0 && <RuleList title="WEAKNESSES" items={s.weaknesses} tone={colors.red} />}
    </ScrollView>
  );
}

function RuleList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <SectionLabel>{title}</SectionLabel>
      {(items || []).map((it, i) => (
        <View key={i} style={styles.ruleRow}>
          <View style={[styles.dot, { backgroundColor: tone }]} />
          <Text style={[type.body, { flex: 1, fontSize: 13 }]}>{it}</Text>
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  back: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.sm },
  grade: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 },
  renameInput: { flex: 1, minWidth: 0, color: colors.text, fontSize: 18, fontWeight: "700", borderWidth: 1, borderColor: colors.teal, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 4 },
  gradeTxt: { fontSize: 10, fontWeight: "800" },
  tagWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.sm },
  importedBadge: { flexDirection: "row", alignItems: "center", gap: 5, alignSelf: "flex-start", marginTop: spacing.sm, borderWidth: 1, borderColor: colors.teal, backgroundColor: colors.tealGlow, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 },
  manageBtn: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: spacing.sm, borderWidth: 1, borderColor: colors.teal, backgroundColor: colors.tealGlow, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 9 },
  enginePanel: { marginTop: spacing.sm, borderWidth: 1, borderColor: colors.teal, backgroundColor: colors.tealGlow, borderRadius: radius.sm, padding: spacing.sm + 2 },
  engineBtn: { flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 8 },
  engineBtnTxt: { fontSize: 11, fontWeight: "700" },
  indChip: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 5, backgroundColor: colors.bgElevated },
  perfGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  perfCell: { width: "47%", borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, padding: spacing.sm, backgroundColor: colors.bgElevated },
  ruleRow: { flexDirection: "row", alignItems: "flex-start", gap: 8, marginTop: 6 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
});
