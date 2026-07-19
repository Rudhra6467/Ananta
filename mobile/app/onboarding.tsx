import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput, ActivityIndicator, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { setItem } from "../src/storage";
import { Logo } from "../src/components/Logo";
import { ProvisioningPipeline } from "../src/components/ProvisioningPipeline";
import api from "../src/api";
import { colors, spacing, type, radius } from "../src/theme";

type Step = "welcome" | "research" | "capital" | "alloc" | "strategies" | "summary";

const CAPITAL_PRESETS = [10000, 25000, 50000, 100000];
const FIXED_PRESETS = [500, 1000, 2500];
const PCT_PRESETS = [5, 10];

const money = (n: number) => `$${Number(n).toLocaleString()}`;

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [step, setStep] = useState<Step>("welcome");

  const [capital, setCapital] = useState(25000);
  const [customCap, setCustomCap] = useState("");
  const [allocType, setAllocType] = useState<"fixed" | "percent">("fixed");
  const [allocValue, setAllocValue] = useState(1000);
  const [customAlloc, setCustomAlloc] = useState("");

  const [builtIn, setBuiltIn] = useState<any[]>([]);
  const [mine, setMine] = useState<any[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loadingStrats, setLoadingStrats] = useState(false);
  const [starting, setStarting] = useState(false);
  const [provisioning, setProvisioning] = useState(false);

  // (re)load strategies whenever this screen is focused — so a strategy created
  // mid-flow (via /library/import) shows up instantly on return.
  const loadStrategies = useCallback(async () => {
    setLoadingStrats(true);
    try {
      const reg = await api.strategyRegistry();
      const all = reg.strategies || [];
      setBuiltIn(all.filter((s: any) => s.internal !== false));
      let lib: any[] = [];
      try { const d = await api.libraryList({}); lib = (d.strategies || []).filter((s: any) => !s.internal && s.engine_key); } catch { /* noop */ }
      setMine(lib);
      // auto-select any brand-new custom strategy on return
      setSelected((prev) => {
        const newest = lib.find((s: any) => !prev.includes(s.engine_key));
        return newest && prev.length < builtIn.length + lib.length && !prev.includes(newest.engine_key) && prev.length > 0
          ? [...prev, newest.engine_key] : prev;
      });
    } finally { setLoadingStrats(false); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useFocusEffect(useCallback(() => { if (step === "strategies") loadStrategies(); }, [step, loadStrategies]));

  const finishOnboarding = async () => {
    await setItem("ananta_onboarded", "1");
    router.replace("/(tabs)");
  };

  const toggle = (key: string) => setSelected((p) => (p.includes(key) ? p.filter((x) => x !== key) : [...p, key]));

  const startPaper = async () => {
    setStarting(true);
    try {
      await api.onboardingPaperSetup({ capital, allocation_type: allocType, allocation_value: allocValue, strategies: selected });
      await setItem("ananta_onboarded", "1");
      setStarting(false);
      setProvisioning(true);
    } catch (e: any) {
      setStarting(false);
      Alert.alert("Setup failed", e?.message || "Could not start paper trading.");
    }
  };

  return (
    <View style={[styles.fill, { paddingTop: insets.top }]} testID={`onboarding-${step}`}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing.xl, flexGrow: 1 }}>
        <View style={styles.logoRow}><Logo size={44} showWord={false} color="#D2D6DC" /><Text style={styles.brand}>Ananta</Text></View>

        {step === "welcome" && (
          <Hero
            icon="sparkles" kicker="WELCOME"
            title="Welcome to Ananta"
            body="Trade with evidence, not assumptions. Research every strategy before risking real capital — build confidence through testing, validation, and paper trading."
            cta="Start Exploring" ctaTestID="onboarding-start-exploring" onCta={() => setStep("research")}
          />
        )}

        {step === "research" && (
          <Hero
            icon="flask" kicker="RESEARCH FIRST"
            title="Start with Paper Trading"
            body="The safest way to begin is by testing strategies in a simulated environment. Paper Trading lets you run your strategies against live market conditions without risking real money — configure your virtual capital, choose strategies, and build confidence before going live."
            cta="Start Paper Trading" ctaTestID="onboarding-start-paper" onCta={() => setStep("capital")}
            secondary="Skip for Now" secondaryTestID="onboarding-skip" onSecondary={finishOnboarding}
          />
        )}

        {step === "capital" && (
          <StepShell num={1} of={3} title="Allocate Virtual Capital" hint="How much virtual capital would you like to start with? You can change this anytime.">
            <View style={styles.grid}>
              {CAPITAL_PRESETS.map((v) => (
                <Choice key={v} testID={`cap-${v}`} label={money(v)} active={!customCap && capital === v} onPress={() => { setCustomCap(""); setCapital(v); }} />
              ))}
            </View>
            <Text style={styles.fieldLabel}>Custom amount</Text>
            <TextInput testID="cap-custom" value={customCap} onChangeText={(t) => { setCustomCap(t.replace(/[^0-9]/g, "")); const n = parseInt(t.replace(/[^0-9]/g, ""), 10); if (n) setCapital(n); }}
              placeholder="e.g. 30000" placeholderTextColor={colors.textFaint} keyboardType="number-pad" style={styles.input} />
            <PrimaryBtn testID="onboarding-continue" label="Continue" disabled={capital < 100} onPress={() => setStep("alloc")} />
          </StepShell>
        )}

        {step === "alloc" && (
          <StepShell num={2} of={3} title="Per Trade Allocation" hint="How much capital should be allocated to each trade? This caps the maximum size of any single position.">
            <View style={styles.segRow}>
              <Seg testID="alloc-type-fixed" label="Fixed $" active={allocType === "fixed"} onPress={() => { setAllocType("fixed"); setAllocValue(1000); setCustomAlloc(""); }} />
              <Seg testID="alloc-type-percent" label="% of Portfolio" active={allocType === "percent"} onPress={() => { setAllocType("percent"); setAllocValue(5); setCustomAlloc(""); }} />
            </View>
            <View style={styles.grid}>
              {(allocType === "fixed" ? FIXED_PRESETS : PCT_PRESETS).map((v) => (
                <Choice key={v} testID={`alloc-${v}`} label={allocType === "fixed" ? money(v) : `${v}%`} active={!customAlloc && allocValue === v} onPress={() => { setCustomAlloc(""); setAllocValue(v); }} />
              ))}
            </View>
            <Text style={styles.fieldLabel}>Custom {allocType === "fixed" ? "amount ($)" : "percent (%)"}</Text>
            <TextInput testID="alloc-custom" value={customAlloc} onChangeText={(t) => { const c = t.replace(/[^0-9.]/g, ""); setCustomAlloc(c); const n = parseFloat(c); if (n) setAllocValue(n); }}
              placeholder={allocType === "fixed" ? "e.g. 750" : "e.g. 7.5"} placeholderTextColor={colors.textFaint} keyboardType="decimal-pad" style={styles.input} />
            <PrimaryBtn testID="onboarding-continue" label="Continue" disabled={allocValue <= 0} onPress={() => setStep("strategies")} />
          </StepShell>
        )}

        {step === "strategies" && (
          <StepShell num={3} of={3} title="Select Trading Strategies" hint="Choose the strategies Ananta should run in your paper session.">
            {loadingStrats && builtIn.length === 0 ? (
              <ActivityIndicator color={colors.teal} style={{ marginVertical: spacing.lg }} />
            ) : (
              <>
                <Text style={styles.sectionLabel}>BUILT-IN STRATEGIES</Text>
                {builtIn.map((s) => (
                  <StratRow key={s.key} testID={`strat-${s.key}`} name={s.name} on={selected.includes(s.key)} onPress={() => toggle(s.key)} />
                ))}

                <Text style={[styles.sectionLabel, { marginTop: spacing.md }]}>MY STRATEGIES</Text>
                {mine.length === 0 ? (
                  <Text style={[type.small, { marginBottom: spacing.sm }]}>You haven&apos;t created any custom strategies yet.</Text>
                ) : (
                  mine.map((s) => (
                    <StratRow key={s.engine_key} testID={`strat-${s.engine_key}`} name={s.name} on={selected.includes(s.engine_key)} onPress={() => toggle(s.engine_key)} />
                  ))
                )}
                <Pressable testID="onboarding-create-strategy" onPress={() => router.push("/library/import")} style={styles.createBtn}>
                  <Ionicons name="add" size={18} color={colors.teal} />
                  <Text style={styles.createTxt}>Create Strategy</Text>
                </Pressable>
              </>
            )}
            <PrimaryBtn testID="onboarding-continue" label="Continue" disabled={selected.length === 0} onPress={() => setStep("summary")} />
          </StepShell>
        )}

        {step === "summary" && (
          <StepShell title="Review & Start" hint="Confirm your paper trading setup. You can change any of this later in Workspace.">
            <View style={styles.summaryCard}>
              <SummaryRow label="Virtual Capital" value={money(capital)} />
              <SummaryRow label="Per Trade Allocation" value={allocType === "fixed" ? money(allocValue) : `${allocValue}%`} />
              <View style={{ paddingTop: spacing.sm }}>
                <Text style={styles.summaryKey}>Strategies</Text>
                {selected.map((k) => {
                  const s = [...builtIn, ...mine].find((x) => (x.key || x.engine_key) === k);
                  return <Text key={k} style={styles.summaryStrat}>• {s?.name || k}</Text>;
                })}
              </View>
            </View>
            <PrimaryBtn testID="onboarding-finish" label={starting ? "STARTING…" : "Start Paper Trading"} disabled={starting} onPress={startPaper} loading={starting} />
            <Pressable testID="onboarding-back" onPress={() => setStep("strategies")} style={{ paddingVertical: spacing.sm, alignItems: "center" }}>
              <Text style={[type.small, { color: colors.textMuted }]}>← Back</Text>
            </Pressable>
          </StepShell>
        )}
      </ScrollView>
      <ProvisioningPipeline visible={provisioning} onDone={() => router.replace("/(tabs)")} />
    </View>
  );
}

function Hero({ icon, kicker, title, body, cta, ctaTestID, onCta, secondary, secondaryTestID, onSecondary }: any) {
  return (
    <View style={{ flex: 1, justifyContent: "center", paddingVertical: spacing.xl }}>
      <View style={styles.heroIcon}><Ionicons name={icon} size={26} color={colors.teal} /></View>
      <Text style={styles.kicker}>{kicker}</Text>
      <Text style={styles.heroTitle}>{title}</Text>
      <Text style={styles.heroBody}>{body}</Text>
      <PrimaryBtn testID={ctaTestID} label={cta} onPress={onCta} />
      {secondary && (
        <Pressable testID={secondaryTestID} onPress={onSecondary} style={{ paddingVertical: spacing.sm, alignItems: "center" }}>
          <Text style={[type.small, { color: colors.textMuted }]}>{secondary}</Text>
        </Pressable>
      )}
    </View>
  );
}

function StepShell({ num, of, title, hint, children }: any) {
  return (
    <View style={{ marginTop: spacing.md }}>
      {num ? <Text style={styles.kicker}>STEP {num} OF {of}</Text> : null}
      <Text style={styles.heroTitle}>{title}</Text>
      <Text style={[styles.heroBody, { marginBottom: spacing.md }]}>{hint}</Text>
      {children}
    </View>
  );
}

function Choice({ testID, label, active, onPress }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.choice, active && styles.choiceOn]}>
      <Text style={[styles.choiceTxt, active && { color: colors.teal }]}>{label}</Text>
    </Pressable>
  );
}
function Seg({ testID, label, active, onPress }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.seg, active && styles.segOn]}>
      <Text style={[styles.segTxt, active && { color: colors.bg }]}>{label}</Text>
    </Pressable>
  );
}
function StratRow({ testID, name, on, onPress }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.stratRow, on && styles.stratRowOn]}>
      <View style={[styles.check, on && styles.checkOn]}>{on && <Ionicons name="checkmark" size={13} color={colors.bg} />}</View>
      <Text style={[type.body, { flex: 1 }]} numberOfLines={1}>{name}</Text>
    </Pressable>
  );
}
function PrimaryBtn({ testID, label, onPress, disabled, loading }: any) {
  return (
    <Pressable testID={testID} onPress={onPress} disabled={disabled} style={[styles.primary, disabled && { opacity: 0.4 }]}>
      {loading ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.primaryTxt}>{label}</Text>}
    </Pressable>
  );
}
function SummaryRow({ label, value }: any) {
  return (
    <View style={styles.summaryRow}>
      <Text style={styles.summaryKey}>{label}</Text>
      <Text style={styles.summaryVal}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  logoRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  brand: { ...type.h3, color: colors.text },
  heroIcon: { width: 52, height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: colors.tealGlow, borderWidth: 1, borderColor: colors.tealDim, marginBottom: spacing.md },
  kicker: { ...type.small, color: colors.teal, letterSpacing: 2, fontWeight: "800", marginBottom: 6 },
  heroTitle: { fontSize: 28, fontWeight: "300", color: colors.text, letterSpacing: -0.5, marginBottom: spacing.sm },
  heroBody: { ...type.body, color: colors.textMuted, lineHeight: 21, marginBottom: spacing.lg },
  primary: { backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 15, alignItems: "center", marginTop: spacing.md },
  primaryTxt: { color: colors.bg, fontWeight: "800", letterSpacing: 1, fontSize: 14 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  choice: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: 18, paddingVertical: 13, minWidth: "47%", alignItems: "center", flexGrow: 1 },
  choiceOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  choiceTxt: { ...type.body, fontWeight: "700", color: colors.text },
  fieldLabel: { ...type.small, color: colors.textMuted, marginTop: spacing.md, marginBottom: 6 },
  input: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 13, color: colors.text, fontSize: 15 },
  segRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  seg: { flex: 1, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: 12, alignItems: "center" },
  segOn: { backgroundColor: colors.teal, borderColor: colors.teal },
  segTxt: { ...type.body, fontWeight: "700", color: colors.textMuted },
  sectionLabel: { ...type.small, color: colors.textMuted, letterSpacing: 1.5, fontWeight: "800", marginBottom: spacing.sm },
  stratRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  stratRowOn: { borderColor: colors.teal, backgroundColor: colors.tealGlow },
  check: { width: 20, height: 20, borderRadius: 5, borderWidth: 1, borderColor: colors.textFaint, alignItems: "center", justifyContent: "center" },
  checkOn: { backgroundColor: colors.teal, borderColor: colors.teal },
  createBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderWidth: 1, borderColor: colors.tealDim, borderStyle: "dashed", borderRadius: radius.md, paddingVertical: 13, marginTop: spacing.xs },
  createTxt: { color: colors.teal, fontWeight: "800", letterSpacing: 0.5, fontSize: 13 },
  summaryCard: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, gap: spacing.xs },
  summaryRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  summaryKey: { ...type.small, color: colors.textMuted },
  summaryVal: { ...type.body, color: colors.text, fontWeight: "700" },
  summaryStrat: { ...type.body, color: colors.teal, marginTop: 2 },
});
