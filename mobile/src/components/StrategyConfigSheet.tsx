import React, { useEffect, useState } from "react";
import { View, Text, Pressable, Modal, ScrollView, TextInput, ActivityIndicator, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { colors, spacing, type, radius } from "../theme";

const REGIME_LABELS: Record<string, string> = {
  TREND_UP: "Trend Up", TREND_DOWN: "Trend Down", COMPRESSION: "Compression",
  RANGE: "Range", REVERSAL: "Reversal", NEUTRAL: "Neutral",
};
const EXIT_LABELS: Record<string, string> = { atr: "ATR Trailing", fixed: "Fixed TP / SL", native: "Native" };

/**
 * Strategy Configuration sheet — allowed regimes + default exit method, the identity applied
 * across Live, Paper and the Research Lab. Apply Recommended / Reset / Manual.
 */
export function StrategyConfigSheet({ visible, onClose, strategyKey, strategyName, focus, isOwner, onSaved }: {
  visible: boolean; onClose: () => void; strategyKey: string; strategyName?: string;
  focus?: "regime" | "exit"; isOwner: boolean; onSaved?: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState<any>(null);
  const [enabled, setEnabled] = useState(true);
  const [regimes, setRegimes] = useState<string[]>([]);
  const [exitMethod, setExitMethod] = useState("native");
  const [params, setParams] = useState<any>({});

  useEffect(() => {
    if (!visible || !strategyKey) return;
    setLoading(true);
    api.strategyProfile(strategyKey)
      .then((d: any) => { setData(d); hydrate(d.profile); })
      .catch((e: any) => Alert.alert("Could not load profile", e?.message || ""))
      .finally(() => setLoading(false));
  }, [visible, strategyKey]);

  const hydrate = (p: any) => {
    setEnabled(p?.enabled !== false);
    setRegimes(p?.allowed_regimes || []);
    setExitMethod(p?.exit_method || "native");
    setParams(p?.exit_params || {});
  };

  const toggleRegime = (r: string) =>
    setRegimes((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));

  const statusLabel = !enabled ? "Disabled" : regimes.length === 0 ? "Disabled — no regimes" : "Enabled";

  const applyRecommended = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setSaving(true);
    try { const r = await api.strategyProfileApplyRecommended(strategyKey); hydrate(r.profile); }
    catch (e: any) { Alert.alert("Apply failed", e?.message || ""); } finally { setSaving(false); }
  };
  const resetDefaults = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setSaving(true);
    try { const r = await api.strategyProfileReset(strategyKey); hydrate(r.profile || { enabled: false, allowed_regimes: [], exit_method: "fixed", exit_params: {} }); onSaved?.(); }
    catch (e: any) { Alert.alert("Reset failed", e?.message || ""); } finally { setSaving(false); }
  };
  const save = async () => {
    if (!isOwner) return Alert.alert("Owner login required");
    setSaving(true);
    try {
      await api.strategyProfileSave(strategyKey, { enabled, allowed_regimes: regimes, exit_method: exitMethod, exit_params: params });
      onSaved?.(); onClose();
    } catch (e: any) { Alert.alert("Save failed", e?.message || ""); } finally { setSaving(false); }
  };

  const rec = data?.recommended;
  const setParam = (k: string, v: string) => setParams((cur: any) => ({ ...cur, [k]: v === "" ? undefined : Number(v) }));

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "flex-end" }}>
        <View testID="strategy-config-sheet" style={{ backgroundColor: colors.card, borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: "88%", padding: spacing.md }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
            <Text style={type.h2}>Strategy Configuration</Text>
            <Pressable testID="config-close" onPress={onClose} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
          </View>
          <Text style={[type.small, { marginBottom: spacing.sm }]}>{strategyName || strategyKey}</Text>

          {loading ? (
            <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={colors.teal} /></View>
          ) : (
            <ScrollView showsVerticalScrollIndicator={false}>
              {/* status + presets */}
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: spacing.sm }}>
                <View testID="config-status" style={{ flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: enabled ? colors.teal : colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6 }}>
                  <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: enabled ? colors.teal : colors.textMuted }} />
                  <Text style={[type.small, { color: enabled ? colors.teal : colors.textMuted, fontWeight: "700" }]}>{statusLabel}</Text>
                </View>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  {rec && <Pressable testID="config-apply-recommended" onPress={applyRecommended} disabled={saving || !isOwner} style={btn(colors.teal, true)}>
                    <Ionicons name="sparkles" size={12} color={colors.bg} /><Text style={[type.small, { color: colors.bg, fontWeight: "700" }]}>Recommended</Text></Pressable>}
                  <Pressable testID="config-reset" onPress={resetDefaults} disabled={saving || !isOwner} style={btn(colors.cardBorder, false)}>
                    <Ionicons name="refresh" size={12} color={colors.text} /><Text style={[type.small, { color: colors.text, fontWeight: "700" }]}>Reset</Text></Pressable>
                </View>
              </View>
              {rec?.note ? <Text style={[type.small, { color: colors.textMuted, marginBottom: spacing.sm }]}>Recommended: {(rec.allowed_regimes || []).join(", ") || "—"} · {EXIT_LABELS[rec.exit_method]} — {rec.note}</Text> : null}

              {/* enabled */}
              <Pressable testID="config-enabled-toggle" onPress={() => setEnabled((v) => !v)} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Text style={[type.body, { fontWeight: "700" }]}>Enabled</Text>
                  <Text style={[type.small, { color: colors.textMuted }]}>Off = benched; the engine never evaluates entries.</Text>
                </View>
                <View style={{ width: 44, height: 26, borderRadius: 13, backgroundColor: enabled ? colors.teal : colors.cardBorder, justifyContent: "center", padding: 2 }}>
                  <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: "#fff", alignSelf: enabled ? "flex-end" : "flex-start" }} />
                </View>
              </Pressable>

              {/* regimes */}
              <View style={{ opacity: enabled ? 1 : 0.4, marginBottom: spacing.md }} pointerEvents={enabled ? "auto" : "none"} testID="config-regimes">
                <Text style={[type.small, { color: colors.textMuted, fontWeight: "700", marginBottom: 6 }]}>REGIME FILTER {focus === "regime" ? "•" : ""}</Text>
                <Text style={[type.small, { color: colors.textMuted, marginBottom: 8 }]}>Market conditions this strategy may trade. None selected = disabled (benched).</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                  {(data?.regimes || []).map((r: string) => {
                    const on = regimes.includes(r);
                    return (
                      <Pressable key={r} testID={`config-regime-${r}`} onPress={() => toggleRegime(r)}
                        style={{ borderWidth: 1, borderColor: on ? colors.teal : colors.cardBorder, backgroundColor: on ? "rgba(45,212,191,0.1)" : "transparent", borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 8 }}>
                        <Text style={[type.small, { color: on ? colors.teal : colors.textMuted, fontWeight: "700" }]}>{REGIME_LABELS[r] || r}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              {/* exit */}
              <View style={{ opacity: enabled ? 1 : 0.4, marginBottom: spacing.md }} pointerEvents={enabled ? "auto" : "none"} testID="config-exit">
                <Text style={[type.small, { color: colors.textMuted, fontWeight: "700", marginBottom: 6 }]}>DEFAULT EXIT {focus === "exit" ? "•" : ""}</Text>
                <View style={{ flexDirection: "row", gap: 8, marginBottom: 8 }}>
                  {Object.keys(data?.exit_methods || EXIT_LABELS).map((m) => (
                    <Pressable key={m} testID={`config-exit-${m}`} onPress={() => setExitMethod(m)}
                      style={{ flex: 1, borderWidth: 1, borderColor: exitMethod === m ? colors.teal : colors.cardBorder, backgroundColor: exitMethod === m ? "rgba(45,212,191,0.1)" : "transparent", borderRadius: radius.sm, paddingVertical: 10, alignItems: "center" }}>
                      <Text style={[type.small, { color: exitMethod === m ? colors.teal : colors.textMuted, fontWeight: "700" }]}>{EXIT_LABELS[m] || m}</Text>
                    </Pressable>
                  ))}
                </View>
                {exitMethod === "atr" && <ParamInput label="ATR Multiplier" testID="config-atr-mult" value={params.atr_multiplier} onChange={(v) => setParam("atr_multiplier", v)} placeholder="2.5" />}
                {exitMethod === "fixed" && (
                  <View style={{ flexDirection: "row", gap: 8 }}>
                    <View style={{ flex: 1 }}><ParamInput label="Take Profit %" testID="config-tp" value={params.target_profit} onChange={(v) => setParam("target_profit", v)} placeholder="5.0" /></View>
                    <View style={{ flex: 1 }}><ParamInput label="Stop Loss %" testID="config-sl" value={params.target_loss} onChange={(v) => setParam("target_loss", v)} placeholder="4.0" /></View>
                  </View>
                )}
              </View>

              <Pressable testID="config-save" onPress={save} disabled={saving || !isOwner}
                style={{ backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 14, alignItems: "center", flexDirection: "row", justifyContent: "center", gap: 8, opacity: saving || !isOwner ? 0.5 : 1, marginBottom: spacing.lg }}>
                {saving ? <ActivityIndicator color={colors.bg} /> : <Ionicons name="shield-checkmark" size={16} color={colors.bg} />}
                <Text style={[type.body, { color: colors.bg, fontWeight: "700" }]}>Save Configuration</Text>
              </Pressable>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

function ParamInput({ label, value, onChange, placeholder, testID }: any) {
  return (
    <View style={{ marginTop: 4 }}>
      <Text style={[type.small, { color: colors.textMuted, marginBottom: 4 }]}>{label}</Text>
      <TextInput testID={testID} keyboardType="numeric" value={value != null ? String(value) : ""} placeholder={placeholder}
        placeholderTextColor={colors.textMuted} onChangeText={onChange}
        style={{ borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10, color: colors.text, backgroundColor: colors.bg }} />
    </View>
  );
}

const btn = (border: string, filled: boolean) => ({
  flexDirection: "row" as const, alignItems: "center" as const, gap: 4,
  borderWidth: 1, borderColor: border, backgroundColor: filled ? border : "transparent",
  borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6,
});
