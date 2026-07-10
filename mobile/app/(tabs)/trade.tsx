import React, { useCallback, useMemo, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, RefreshControl, Alert, TextInput, Switch, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import api from "../../src/api";
import { useAuth } from "../../src/auth";
import { useFetch } from "../../src/useFetch";
import { Card } from "../../src/components/Card";
import { Segmented } from "../../src/components/Segmented";
import { LoadingView, ErrorView } from "../../src/components/StateView";
import { PageHeader } from "../../src/components/PageHeader";
import { colors, spacing, type, radius, pnlColor } from "../../src/theme";
import { usd, signedUsd, pct, price, base } from "../../src/format";

async function loadTrade() {
  const [portfolio, environment, tradesResp, pendingResp, settings, metrics] = await Promise.all([
    api.portfolio(), api.getEnvironment(), api.trades(80), api.pendingOrders(), api.settings(), api.strategyMetrics(),
  ]);
  const trades = tradesResp?.items || tradesResp?.trades || (Array.isArray(tradesResp) ? tradesResp : []);
  const pending = pendingResp?.items || pendingResp?.orders || (Array.isArray(pendingResp) ? pendingResp : []);
  const strategies = Object.values(metrics?.metrics || {});
  return { portfolio, environment, trades, pending, settings, strategies };
}

export default function Trade() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isOwner } = useAuth();
  const { data, loading, error, refresh, refreshing } = useFetch(loadTrade, [], 15000);
  const [sub, setSub] = useState("orders");
  const [coachOpen, setCoachOpen] = useState(false);

  const setMode = async (mode: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    try { await api.setEnvironment(mode.toUpperCase()); refresh(); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const toggleKill = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const killed = !!data?.settings?.manual_kill_switch;
    try { await api.updateSettings({ manual_kill_switch: !killed }); refresh(); } catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  const closePos = (b: string) => {
    if (!isOwner) return Alert.alert("Owner login required");
    Alert.alert("Close position", `Manually close ${b}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Close", style: "destructive", onPress: async () => { try { await api.closePosition(b); refresh(); } catch (e: any) { Alert.alert("Failed", e?.message); } } },
    ]);
  };

  if (loading && !data) return <View style={styles.fill}><LoadingView label="Trade" /></View>;
  if (error && !data) return <View style={styles.fill}><ErrorView message={error} onRetry={refresh} /></View>;

  const positions = (data?.portfolio?.positions || []).filter((p: any) => p.quantity > 0);
  const pending = data?.pending || [];
  const closed = (data?.trades || []).filter((t: any) => t.side === "SELL" && (t.status || "FILLED") === "FILLED" && t.pnl != null);
  const strategies = data?.strategies || [];
  const enabledSymbols: string[] = data?.settings?.enabled_symbols || [];
  const mode = (data?.environment?.mode || "PAPER").toUpperCase();
  const modeKey = mode === "LIVE" ? "live" : "paper";
  const killed = !!data?.settings?.manual_kill_switch;

  return (
    <View style={styles.fill}>
      <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.sm, paddingBottom: insets.bottom + 132 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}>
        <PageHeader title="Trade" question="What should I do?" />

        <Card testID="trade-mode-bar" style={{ marginBottom: spacing.sm }}>
          <View style={styles.rowBetween}>
            <Text style={type.label}>EXECUTION MODE</Text>
            <Pressable testID="trade-kill-btn" onPress={toggleKill} style={[styles.killMini, killed && styles.killOn]}>
              <Ionicons name="power" size={13} color={colors.red} />
              <Text style={styles.killTxt}>{killed ? "RELEASE" : "STOP"}</Text>
            </Pressable>
          </View>
          <View style={{ marginTop: spacing.sm }}>
            <Segmented options={[{ key: "paper", label: "PAPER" }, { key: "live", label: "LIVE" }]} value={modeKey} onChange={setMode} testIDPrefix="trade-mode" />
          </View>
        </Card>

        <View style={{ marginBottom: spacing.sm }}>
          <Segmented testIDPrefix="trade-subtab"
            options={[{ key: "orders", label: `ORDERS` }, { key: "positions", label: `POSITIONS ${positions.length}` }, { key: "history", label: "HISTORY" }]}
            value={sub} onChange={setSub} />
        </View>

        {sub === "orders" && (
          <>
            <ManualOrder isOwner={isOwner} symbols={enabledSymbols} onDone={refresh} />
            <ActiveStrategies isOwner={isOwner} strategies={strategies} onDone={refresh} />
            {pending.length > 0 && (
              <View style={{ marginTop: spacing.md }}>
                <Text style={[type.label, { marginBottom: spacing.sm }]}>RESTING ORDERS</Text>
                {pending.map((o: any, i: number) => (
                  <Card key={o.id || i} style={{ marginBottom: spacing.xs, paddingVertical: spacing.sm }}>
                    <View style={styles.rowBetween}>
                      <Text style={type.h3}>{base(o.symbol)}</Text>
                      <Text style={type.small}>{o.side} · {o.status || "RESTING"}</Text>
                    </View>
                    <Text style={type.small}>{o.quantity} @ {price(o.price || o.limit_price)}</Text>
                  </Card>
                ))}
              </View>
            )}
          </>
        )}

        {sub === "positions" && (positions.length === 0 ? <Empty icon="layers" text="No open positions." /> :
          positions.map((p: any) => {
            const b = base(p.symbol), rowPnl = p.unrealized_pnl || 0;
            const rowPct = p.avg_cost > 0 ? ((p.last_price - p.avg_cost) / p.avg_cost) * 100 : 0;
            return (
              <Card key={p.symbol} testID={`holding-${b}`} style={{ marginBottom: spacing.sm, paddingVertical: spacing.sm + 2 }}>
                <View style={styles.rowBetween}>
                  <Text style={[type.h3]}>{b}</Text>
                  <Text style={[type.h3, { color: pnlColor(rowPnl) }]}>{signedUsd(rowPnl)}</Text>
                </View>
                <View style={styles.rowBetween}>
                  <Text style={type.small}>{p.quantity} @ {price(p.avg_cost)} · LTP {price(p.last_price)}</Text>
                  <Text style={[type.small, { color: pnlColor(rowPnl) }]}>{pct(rowPct)}</Text>
                </View>
                <View style={[styles.rowBetween, { marginTop: spacing.xs }]}>
                  <Text style={type.small}>Invested {usd(p.avg_cost * p.quantity)}</Text>
                  <Pressable testID={`close-${b}`} onPress={() => closePos(b)} style={styles.closeBtn}><Text style={styles.closeTxt}>EXIT</Text></Pressable>
                </View>
              </Card>
            );
          }))}

        {sub === "history" && <History closed={closed} />}
      </ScrollView>

      {/* Sticky bottom actions — always visible */}
      <View style={[styles.stickyBar, { paddingBottom: insets.bottom + spacing.sm }]}>
        <Pressable testID="sticky-ai-coach" onPress={() => setCoachOpen(true)} style={[styles.stickyBtn, styles.stickyGhost]}>
          <Ionicons name="sparkles" size={16} color={colors.teal} />
          <Text style={styles.stickyGhostTxt}>AI Trade Coach</Text>
        </Pressable>
        <Pressable testID="sticky-add-strategy" onPress={() => router.push("/(tabs)/strategy")} style={[styles.stickyBtn, styles.stickyPrimary]}>
          <Ionicons name="add" size={18} color={colors.bg} />
          <Text style={styles.stickyPrimaryTxt}>Add Strategies</Text>
        </Pressable>
      </View>

      <AICoachSheet open={coachOpen} onClose={() => setCoachOpen(false)} mode={mode} />
    </View>
  );
}

function ManualOrder({ isOwner, symbols, onDone }: { isOwner: boolean; symbols: string[]; onDone: () => void }) {
  const [sym, setSym] = useState(symbols[0] || "BTC/USD");
  const [side, setSide] = useState("buy");
  const [otype, setOtype] = useState("market");
  const [notional, setNotional] = useState("100");
  const [fraction, setFraction] = useState("100");
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    const payload: any = { symbol: base(sym), side: side.toUpperCase(), order_type: otype.toUpperCase() };
    if (side === "buy") {
      const n = parseFloat(notional);
      if (!(n > 0)) return Alert.alert("Enter a valid USD amount");
      payload.notional_usd = n;
    } else {
      const f = parseFloat(fraction);
      if (!(f > 0)) return Alert.alert("Enter a valid % to sell");
      payload.fraction = Math.min(1, Math.max(0, f / 100));
    }
    if (otype === "limit") {
      const lp = parseFloat(limit);
      if (!(lp > 0)) return Alert.alert("Enter a valid limit price");
      payload.limit_price = lp;
    }
    Alert.alert("Confirm order", `${side.toUpperCase()} ${base(sym)} · ${otype.toUpperCase()}${side === "buy" ? ` · $${payload.notional_usd}` : ` · ${fraction}%`}`, [
      { text: "Cancel", style: "cancel" },
      { text: "Place", onPress: async () => {
        setBusy(true);
        try {
          const r = await api.manualOrder(payload);
          Alert.alert("Order placed", r?.resting ? "Limit order is resting until price is reached." : `${side.toUpperCase()} filled.`);
          onDone();
        } catch (e: any) { Alert.alert("Order failed", e?.message || "Error"); }
        finally { setBusy(false); }
      } },
    ]);
  };

  return (
    <Card testID="manual-order-card" style={{ marginBottom: spacing.sm }}>
      <Text style={type.label}>CREATE MANUAL ORDER</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.xs, marginTop: spacing.sm }}>
        {symbols.map((s) => (
          <Pressable key={s} testID={`manual-order-sym-${base(s)}`} onPress={() => setSym(s)} style={[styles.symPill, sym === s && styles.symPillOn]}>
            <Text style={[styles.symPillTxt, sym === s && { color: colors.bg }]}>{base(s)}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <View style={{ marginTop: spacing.sm, flexDirection: "row", gap: spacing.sm }}>
        <View style={{ flex: 1 }}>
          <Segmented testIDPrefix="manual-order-side" options={[{ key: "buy", label: "BUY" }, { key: "sell", label: "SELL" }]} value={side} onChange={setSide} />
        </View>
        <View style={{ flex: 1 }}>
          <Segmented testIDPrefix="manual-order-type" options={[{ key: "market", label: "MKT" }, { key: "limit", label: "LMT" }]} value={otype} onChange={setOtype} />
        </View>
      </View>
      <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
        {side === "buy" ? (
          <Field label="AMOUNT (USD)" testID="manual-order-notional" value={notional} onChange={setNotional} placeholder="100" />
        ) : (
          <Field label="SELL % OF POSITION" testID="manual-order-fraction" value={fraction} onChange={setFraction} placeholder="100" />
        )}
        {otype === "limit" && <Field label="LIMIT PRICE" testID="manual-order-limit" value={limit} onChange={setLimit} placeholder="0.00" />}
      </View>
      <Pressable testID="manual-order-submit" disabled={busy} onPress={submit} style={[styles.submitBtn, side === "sell" && styles.submitSell, busy && { opacity: 0.5 }]}>
        <Text style={[styles.submitTxt, { color: colors.bg }]}>{busy ? "PLACING…" : `${side.toUpperCase()} ${base(sym)}`}</Text>
      </Pressable>
    </Card>
  );
}

function Field({ label, value, onChange, placeholder, testID }: any) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={[type.small, { marginBottom: spacing.xs, fontSize: 11 }]}>{label}</Text>
      <TextInput testID={testID} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.textFaint}
        keyboardType="decimal-pad" style={styles.input} />
    </View>
  );
}

function ActiveStrategies({ isOwner, strategies, onDone }: { isOwner: boolean; strategies: any[]; onDone: () => void }) {
  const toggle = async (key: string, isOn: boolean) => {
    if (!isOwner) return Alert.alert("Owner login required");
    try { isOn ? await api.strategyDisable(key) : await api.strategyDeploy(key); onDone(); }
    catch (e: any) { Alert.alert("Failed", e?.message); }
  };
  if (strategies.length === 0) return null;
  return (
    <View style={{ marginTop: spacing.md }}>
      <Text style={[type.label, { marginBottom: spacing.sm }]}>ACTIVE STRATEGIES</Text>
      {strategies.map((s: any) => {
        const isOn = !!s.enabled && s.status !== "DISABLED" && s.status !== "ERROR";
        return (
          <Card key={s.key} style={{ marginBottom: spacing.xs, paddingVertical: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
            <View style={{ flex: 1, marginRight: spacing.sm }}>
              <Text style={[type.body, { fontWeight: "700" }]} numberOfLines={1}>{s.name}</Text>
              <Text style={type.small}>{s.status} · {s.trades} trades · WR {s.win_rate}%</Text>
            </View>
            <Switch testID={`strategy-toggle-${s.key}`} value={isOn} onValueChange={() => toggle(s.key, isOn)}
              trackColor={{ true: colors.tealDim, false: colors.cardBorder }} thumbColor={isOn ? colors.teal : colors.textFaint} />
          </Card>
        );
      })}
    </View>
  );
}

function History({ closed }: { closed: any[] }) {
  const [limit, setLimit] = useState(3);
  if (closed.length === 0) return <Empty icon="archive" text="No closed trades yet." />;
  const rows = closed.slice(0, limit);
  return (
    <View>
      <ScrollView style={limit > 15 ? { maxHeight: 520 } : undefined} nestedScrollEnabled>
        {rows.map((t: any) => (
          <Card key={t.id} testID={`closed-${t.id}`} style={{ marginBottom: spacing.xs, paddingVertical: spacing.sm }}>
            <View style={styles.rowBetween}>
              <Text style={[type.body, { fontWeight: "700" }]}>{base(t.symbol)}</Text>
              <Text style={[type.body, { color: pnlColor(t.pnl || 0), fontWeight: "700" }]}>{signedUsd(t.pnl || 0, 2)}</Text>
            </View>
            <View style={styles.rowBetween}>
              <Text style={type.small}>{t.exit_reason || "-"}</Text>
              <Text style={[type.small, { color: t.return_pct >= 0 ? colors.teal : colors.red }]}>{t.return_pct != null ? pct(t.return_pct) : "—"}</Text>
            </View>
          </Card>
        ))}
      </ScrollView>
      {limit < closed.length && (
        <Pressable testID="history-more" onPress={() => setLimit(limit === 3 ? 15 : closed.length)} style={styles.moreBtn}>
          <Text style={styles.moreTxt}>MORE ({closed.length - limit})</Text>
        </Pressable>
      )}
    </View>
  );
}

function AICoachSheet({ open, onClose, mode }: { open: boolean; onClose: () => void; mode: string }) {
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState("");
  const run = useCallback(async () => {
    setLoading(true); setText("");
    try { const r = await api.coachTradesReview(mode.toLowerCase()); setText(r?.review || r?.summary || r?.text || JSON.stringify(r)); }
    catch (e: any) { setText(`Coach unavailable: ${e?.message || "error"}`); }
    finally { setLoading(false); }
  }, [mode]);
  return (
    <Modal visible={open} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalWrap}>
        <View style={styles.modalCard}>
          <View style={styles.rowBetween}>
            <Text style={type.h3}>AI Trade Coach</Text>
            <Pressable testID="ai-coach-close" onPress={onClose}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          <ScrollView style={{ maxHeight: 340, marginTop: spacing.sm }}>
            <Text style={[type.bodyMuted, { lineHeight: 22 }]}>{text || "Get an AI review of your recent trades — patterns, mistakes, and what to adjust."}</Text>
          </ScrollView>
          <Pressable testID="ai-coach-run" disabled={loading} onPress={run} style={[styles.submitBtn, loading && { opacity: 0.5 }]}>
            <Text style={[styles.submitTxt, { color: colors.bg }]}>{loading ? "ANALYZING…" : "Review my trades"}</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

function Empty({ icon, text }: { icon: any; text: string }) {
  return (
    <Card style={{ alignItems: "center", paddingVertical: spacing.xl }}>
      <Ionicons name={icon} size={30} color={colors.textFaint} />
      <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>{text}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 3 },
  killMini: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderColor: colors.redDim, borderRadius: radius.sm, paddingVertical: 4, paddingHorizontal: spacing.sm },
  killOn: { backgroundColor: colors.redGlow, borderColor: colors.red },
  killTxt: { color: colors.red, fontWeight: "800", letterSpacing: 1, fontSize: 11 },
  closeBtn: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingVertical: 6, paddingHorizontal: spacing.md },
  closeTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  symPill: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.pill, paddingVertical: 6, paddingHorizontal: spacing.md },
  symPillOn: { backgroundColor: colors.teal, borderColor: colors.teal },
  symPillTxt: { color: colors.textMuted, fontSize: 12, fontWeight: "700" },
  input: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, color: colors.text, paddingVertical: 10, paddingHorizontal: spacing.sm, fontSize: 15 },
  submitBtn: { marginTop: spacing.md, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 13, alignItems: "center" },
  submitSell: { backgroundColor: colors.red },
  submitTxt: { fontWeight: "800", letterSpacing: 1, fontSize: 14 },
  moreBtn: { alignItems: "center", paddingVertical: spacing.sm, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, marginTop: spacing.xs },
  moreTxt: { color: colors.teal, fontSize: 12, fontWeight: "700", letterSpacing: 1 },
  stickyBar: { position: "absolute", left: 0, right: 0, bottom: 0, flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.md, paddingTop: spacing.sm, backgroundColor: colors.bgElevated, borderTopWidth: 1, borderTopColor: colors.cardBorder },
  stickyBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingVertical: 12, borderRadius: radius.md },
  stickyGhost: { borderWidth: 1, borderColor: colors.tealDim },
  stickyGhostTxt: { color: colors.teal, fontWeight: "700", fontSize: 13 },
  stickyPrimary: { backgroundColor: colors.teal },
  stickyPrimaryTxt: { color: colors.bg, fontWeight: "800", fontSize: 13 },
  modalWrap: { flex: 1, justifyContent: "flex-end", backgroundColor: colors.overlay },
  modalCard: { backgroundColor: colors.card, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.cardBorder },
});
