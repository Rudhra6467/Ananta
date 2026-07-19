import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ScrollView, TextInput, ActivityIndicator, Alert } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { getItem, setItem } from "../storage";
import { colors, spacing, type, radius } from "../theme";

// "Coming Soon to Ananta" promo — pure RN (no static image), crisp text.
//  - variant "sheet"  : first-login welcome modal on the Cockpit. Non-owner: first 3 launches.
//                       Owner: every login (gate reset in auth.login via resetWelcomeGate()).
//  - variant "inline" : embeddable card (default).
// Waitlist opt-in (+ email) persists server-side.

const KEY = "ananta_promo_coming_soon_v1";
const MAX_VIEWS = 3;
let _welcomeShownThisRun = false;
let _sheetOpen = false; // persists open state across Cockpit loading->loaded remounts
export function resetWelcomeGate() { _welcomeShownThisRun = false; _sheetOpen = false; }

const FEATURES = [
  { icon: "trophy-outline", title: "Weekly AI Trading Championship", bullets: ["$100k virtual balance", "Real prizes in trading credits", "Risk-adjusted leaderboards"] },
  { icon: "storefront-outline", title: "Strategy Marketplace", bullets: ["Discover & follow community strategies", "Paper-trade before you deploy", "Verified badges — battle-tested"] },
  { icon: "document-text-outline", title: "Advanced AI Strategy Reports", bullets: ["Deep performance breakdown", "MFE capture & regime analysis", "What-If comparisons"] },
] as const;

function PromoCard() {
  return (
    <View style={styles.card} testID="promo-card">
      <View style={styles.cardHead}>
        <View style={styles.headIcon}><Ionicons name="trending-up" size={22} color={colors.bg} /></View>
        <Text style={styles.title}>Coming Soon to Ananta</Text>
        <Text style={styles.subtitle}>Three big upgrades on the roadmap</Text>
      </View>
      {FEATURES.map((f) => (
        <View key={f.title} style={styles.feature}>
          <View style={styles.featIcon}><Ionicons name={f.icon as any} size={18} color={colors.teal} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.featTitle}>{f.title}</Text>
            {f.bullets.map((b) => (
              <View key={b} style={styles.bulletRow}>
                <Text style={styles.bulletDot}>•</Text>
                <Text style={styles.bulletTxt}>{b}</Text>
              </View>
            ))}
          </View>
        </View>
      ))}
      <View style={styles.strip}><Text style={styles.stripTxt}>Stay Tuned — Major Updates Coming Soon</Text></View>
    </View>
  );
}

function Waitlist() {
  const [joined, setJoined] = useState(false);
  const [joining, setJoining] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => { api.promoStatus().then((s: any) => setJoined(!!s?.waitlist_joined)).catch(() => {}); }, []);

  const join = async () => {
    const value = email.trim();
    if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) { Alert.alert("Invalid email", "Enter a valid email to join the waitlist."); return; }
    setJoining(true);
    try { await api.promoJoinWaitlist(value); setJoined(true); Alert.alert("You're on the waitlist!", "We'll notify you when these features go live."); }
    catch { Alert.alert("Could not join", "Please try again in a moment."); }
    finally { setJoining(false); }
  };

  if (joined) {
    return (
      <View testID="promo-joined" style={styles.joined}>
        <Ionicons name="checkmark-circle" size={16} color={colors.teal} />
        <Text style={styles.joinedTxt}>You&apos;re on the early-access waitlist</Text>
      </View>
    );
  }
  return (
    <View style={styles.waitRow}>
      <TextInput
        testID="promo-email-input" value={email} onChangeText={setEmail} placeholder="you@email.com"
        placeholderTextColor={colors.textFaint} keyboardType="email-address" autoCapitalize="none" autoCorrect={false}
        style={styles.input}
      />
      <Pressable testID="promo-join-waitlist" onPress={join} disabled={joining} style={[styles.joinBtn, joining && { opacity: 0.7 }]}>
        {joining ? <ActivityIndicator color={colors.bg} size="small" /> : <Text style={styles.joinTxt}>Join Waitlist</Text>}
      </Pressable>
    </View>
  );
}

export default function ComingSoonPromo({ variant = "inline", isOwner = false }: { variant?: "sheet" | "inline"; isOwner?: boolean }) {
  const insets = useSafeAreaInsets();
  const [sheetOpen, _setOpen] = useState(_sheetOpen);
  const setSheetOpen = (v: boolean) => { _sheetOpen = v; _setOpen(v); };

  useEffect(() => {
    if (variant !== "sheet") return;
    if (_welcomeShownThisRun) return;
    (async () => {
      let st = { views: 0, dismissed: false };
      try { const raw = await getItem(KEY); if (raw) st = JSON.parse(raw); } catch { /* ignore */ }
      const show = isOwner ? true : (!st.dismissed && st.views < MAX_VIEWS);
      if (!show) return;
      _welcomeShownThisRun = true;
      if (!isOwner) { try { await setItem(KEY, JSON.stringify({ ...st, views: st.views + 1 })); } catch { /* ignore */ } }
      setSheetOpen(true);
    })();
  }, [variant, isOwner]);

  if (variant === "sheet") {
    return (
      <Modal visible={sheetOpen} transparent animationType="slide" onRequestClose={() => setSheetOpen(false)}>
        <View style={styles.overlay}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.md }]} testID="cockpit-welcome-sheet">
            <View style={styles.grabber} />
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.sm }}>
              <PromoCard />
              <Waitlist />
              <Pressable testID="welcome-sheet-continue" onPress={() => setSheetOpen(false)} style={styles.continueBtn}>
                <Text style={styles.continueTxt}>Continue to Cockpit</Text>
              </Pressable>
            </ScrollView>
          </View>
        </View>
      </Modal>
    );
  }

  return (
    <View testID="promo-inline" style={{ gap: spacing.md, marginBottom: spacing.lg }}>
      <PromoCard />
      <Waitlist />
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.teal + "40", borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm },
  cardHead: { alignItems: "center", gap: 4, marginBottom: spacing.xs },
  headIcon: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  title: { fontSize: 22, fontWeight: "300", color: colors.text },
  subtitle: { ...type.small, color: colors.textFaint },
  feature: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md },
  featIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: colors.tealGlow, alignItems: "center", justifyContent: "center" },
  featTitle: { ...type.body, fontWeight: "700", fontSize: 14, marginBottom: 6 },
  bulletRow: { flexDirection: "row", gap: 6, marginTop: 2 },
  bulletDot: { color: colors.teal, fontSize: 12, lineHeight: 17 },
  bulletTxt: { flex: 1, color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  strip: { borderWidth: 1, borderColor: colors.teal + "33", backgroundColor: colors.tealGlow, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" },
  stripTxt: { color: colors.teal, fontWeight: "800", fontSize: 12, letterSpacing: 0.3 },
  waitRow: { flexDirection: "row", gap: spacing.sm },
  input: { flex: 1, backgroundColor: colors.bgElevated, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, color: colors.text, fontSize: 14 },
  joinBtn: { backgroundColor: colors.teal, borderRadius: radius.md, paddingHorizontal: spacing.md, alignItems: "center", justifyContent: "center", minWidth: 120 },
  joinTxt: { color: colors.bg, fontWeight: "800", fontSize: 13 },
  joined: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.tealGlow, borderWidth: 1, borderColor: colors.teal + "4D", borderRadius: radius.md, paddingVertical: 12 },
  joinedTxt: { color: colors.teal, fontWeight: "700", fontSize: 13 },
  overlay: { flex: 1, backgroundColor: "#000000AA", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.bg, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.md, paddingTop: spacing.sm, maxHeight: "90%" },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.cardBorder, marginBottom: spacing.md },
  continueBtn: { borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingVertical: 13, alignItems: "center" },
  continueTxt: { color: colors.textMuted, fontWeight: "700", fontSize: 14 },
});
