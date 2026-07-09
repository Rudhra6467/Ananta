import React, { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, RefreshControl, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
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
  const [portfolio, environment, tradesResp, pendingResp, settings] = await Promise.all([
    api.portfolio(), api.getEnvironment(), api.trades(80), api.pendingOrders(), api.settings(),
  ]);
  const trades = tradesResp?.items || tradesResp?.trades || (Array.isArray(tradesResp) ? tradesResp : []);
  const pending = pendingResp?.items || pendingResp?.orders || (Array.isArray(pendingResp) ? pendingResp : []);
  return { portfolio, environment, trades, pending, settings };
}

export default function Trade() {
  const insets = useSafeAreaInsets();
  const { isOwner } = useAuth();
  const { data, loading, error, refresh, refreshing } = useFetch(loadTrade, [], 15000);
  const [sub, setSub] = useState("positions");

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
  const mode = (data?.environment?.mode || "PAPER").toUpperCase();
  const modeKey = mode === "LIVE" ? "live" : "paper";
  const killed = !!data?.settings?.manual_kill_switch;

  return (
    <ScrollView style={styles.fill} contentContainerStyle={{ padding: spacing.md, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + 90 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.teal} />}>
      <PageHeader title="Trade" question="What am I trading right now?" />

      <Card testID="trade-mode-bar" style={{ marginBottom: spacing.md }}>
        <Text style={type.label}>EXECUTION MODE</Text>
        <View style={{ marginTop: spacing.sm }}>
          <Segmented options={[{ key: "paper", label: "PAPER" }, { key: "live", label: "LIVE" }]} value={modeKey} onChange={setMode} testIDPrefix="trade-mode" />
        </View>
        <Pressable testID="trade-kill-btn" onPress={toggleKill} style={[styles.kill, killed && styles.killOn]}>
          <Ionicons name="power" size={16} color={colors.red} />
          <Text style={styles.killTxt}>{killed ? "KILL ENGAGED · RELEASE" : "EMERGENCY STOP"}</Text>
        </Pressable>
      </Card>

      <View style={{ marginBottom: spacing.md }}>
        <Segmented testIDPrefix="trade-subtab"
          options={[{ key: "positions", label: `POSITIONS ${positions.length}` }, { key: "orders", label: `ORDERS ${pending.length}` }, { key: "history", label: "HISTORY" }]}
          value={sub} onChange={setSub} />
      </View>

      {sub === "positions" && (positions.length === 0 ? <Empty icon="layers" text="No open positions." /> :
        positions.map((p: any) => {
          const b = base(p.symbol), rowPnl = p.unrealized_pnl || 0;
          const rowPct = p.avg_cost > 0 ? ((p.last_price - p.avg_cost) / p.avg_cost) * 100 : 0;
          return (
            <Card key={p.symbol} testID={`holding-${b}`} style={{ marginBottom: spacing.sm }}>
              <View style={styles.rowBetween}>
                <Text style={[type.h3]}>{b}</Text>
                <Text style={[type.h3, { color: pnlColor(rowPnl) }]}>{signedUsd(rowPnl)}</Text>
              </View>
              <View style={styles.rowBetween}>
                <Text style={type.small}>{p.quantity} @ {price(p.avg_cost)} · LTP {price(p.last_price)}</Text>
                <Text style={[type.small, { color: pnlColor(rowPnl) }]}>{pct(rowPct)}</Text>
              </View>
              <Pressable testID={`close-${b}`} onPress={() => closePos(b)} style={styles.closeBtn}><Text style={styles.closeTxt}>CLOSE POSITION</Text></Pressable>
            </Card>
          );
        }))}

      {sub === "orders" && (pending.length === 0 ? <Empty icon="list" text="No resting orders." /> :
        pending.map((o: any, i: number) => (
          <Card key={o.id || i} style={{ marginBottom: spacing.sm }}>
            <View style={styles.rowBetween}>
              <Text style={type.h3}>{base(o.symbol)}</Text>
              <Text style={type.small}>{o.side} · {o.status || "PENDING"}</Text>
            </View>
            <Text style={type.small}>{o.quantity} @ {price(o.price || o.limit_price)}</Text>
          </Card>
        )))}

      {sub === "history" && (closed.length === 0 ? <Empty icon="archive" text="No closed trades yet." /> :
        closed.slice(0, 60).map((t: any) => (
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
        )))}
    </ScrollView>
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
  kill: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.md, borderWidth: 1, borderColor: colors.redDim, borderRadius: radius.md, paddingVertical: spacing.sm + 2 },
  killOn: { backgroundColor: colors.redGlow, borderColor: colors.red },
  killTxt: { color: colors.red, fontWeight: "800", letterSpacing: 1, fontSize: 12 },
  closeBtn: { marginTop: spacing.sm, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingVertical: spacing.sm, alignItems: "center" },
  closeTxt: { color: colors.textMuted, fontSize: 11, fontWeight: "700", letterSpacing: 1 },
});
