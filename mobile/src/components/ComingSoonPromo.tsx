import React, { useEffect, useState } from "react";
import { View, Text, Image, StyleSheet, Pressable, Modal, ScrollView, ActivityIndicator, Alert } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import api from "../api";
import { getItem, setItem } from "../storage";
import { colors, spacing, type, radius } from "../theme";

// "Coming Soon to Ananta" promo. variant="banner" shows only the first 3 app sessions and is
// dismissible; variant="section" is a permanent "What's Coming" card. Waitlist opt-in is
// persisted server-side; view-count/dismiss are a per-device UX nudge (AsyncStorage).

const KEY = "ananta_promo_coming_soon_v1";
const MAX_VIEWS = 3;
let _countedThisSession = false;

const PROMO_IMG = require("../../assets/promo/coming-soon.jpg");

const FEATURES = [
  { icon: "trophy-outline", title: "Weekly AI Trading Championship", desc: "Compete on a level field with a virtual balance. Climb risk-adjusted leaderboards and win real trading credits every week." },
  { icon: "storefront-outline", title: "Strategy Marketplace", desc: "Discover, follow and paper-trade community strategies with verified track records before you deploy a cent." },
  { icon: "document-text-outline", title: "Advanced AI Strategy Reports", desc: "Automated deep-dives — regime analysis, MFE capture, exit-module performance and What-If comparisons — so you always know what to fix." },
] as const;

export default function ComingSoonPromo({ variant = "section" }: { variant?: "banner" | "section" }) {
  const [visible, setVisible] = useState(variant === "section");
  const [ready, setReady] = useState(variant === "section");
  const [learnOpen, setLearnOpen] = useState(false);
  const [joined, setJoined] = useState(false);
  const [joining, setJoining] = useState(false);

  useEffect(() => { api.promoStatus().then((s: any) => setJoined(!!s?.waitlist_joined)).catch(() => {}); }, []);

  useEffect(() => {
    if (variant !== "banner") return;
    (async () => {
      let st = { views: 0, dismissed: false };
      try { const raw = await getItem(KEY); if (raw) st = JSON.parse(raw); } catch { /* ignore */ }
      if (st.dismissed || st.views >= MAX_VIEWS) { setVisible(false); setReady(true); return; }
      setVisible(true); setReady(true);
      if (!_countedThisSession) {
        _countedThisSession = true;
        try { await setItem(KEY, JSON.stringify({ ...st, views: st.views + 1 })); } catch { /* ignore */ }
      }
    })();
  }, [variant]);

  const dismiss = async () => {
    setVisible(false);
    try {
      const raw = await getItem(KEY);
      const st = raw ? JSON.parse(raw) : { views: 0, dismissed: false };
      await setItem(KEY, JSON.stringify({ ...st, dismissed: true }));
    } catch { /* ignore */ }
  };

  const join = async () => {
    setJoining(true);
    try { await api.promoJoinWaitlist(); setJoined(true); Alert.alert("You're on the waitlist!", "We'll notify you when these features go live."); }
    catch { Alert.alert("Could not join", "Please try again in a moment."); }
    finally { setJoining(false); }
  };

  if (!ready || !visible) return null;

  const Buttons = (
    <View style={styles.btnRow}>
      <Pressable testID="promo-join-waitlist" onPress={join} disabled={joining || joined} style={[styles.btn, styles.btnPrimary, (joining || joined) && { opacity: 0.75 }]}>
        {joining ? <ActivityIndicator color={colors.bg} size="small" /> : joined ? <Ionicons name="checkmark" size={15} color={colors.bg} /> : null}
        <Text style={styles.btnPrimaryTxt}>{joined ? " On the waitlist" : "Join Waitlist"}</Text>
      </Pressable>
      <Pressable testID="promo-learn-more" onPress={() => setLearnOpen(true)} style={[styles.btn, styles.btnGhost]}>
        <Text style={styles.btnGhostTxt}>Learn More</Text>
      </Pressable>
    </View>
  );

  return (
    <View testID={`promo-${variant}`} style={variant === "banner" ? styles.bannerWrap : { marginBottom: spacing.lg }}>
      {variant === "section" && (
        <View style={styles.sectionHead}>
          <Ionicons name="sparkles-outline" size={13} color={colors.teal} />
          <Text style={styles.sectionLabel}>{"WHAT'S COMING"}</Text>
        </View>
      )}
      <View style={styles.card}>
        <View style={styles.heroWrap}>
          <Image source={PROMO_IMG} style={styles.hero} resizeMode="cover" />
          {variant === "banner" && (
            <Pressable testID="promo-dismiss" onPress={dismiss} hitSlop={10} style={styles.closeBtn}>
              <Ionicons name="close" size={16} color={colors.text} />
            </Pressable>
          )}
        </View>
        {Buttons}
      </View>

      <Modal visible={learnOpen} transparent animationType="slide" onRequestClose={() => setLearnOpen(false)}>
        <View style={styles.modalWrap}>
          <View style={styles.modalCard} testID="promo-learn-modal">
            <View style={styles.modalHead}>
              <View style={{ flex: 1 }}>
                <Text style={type.h2}>Coming Soon to Ananta</Text>
                <Text style={[type.small, { color: colors.textMuted, marginTop: 2 }]}>Join the waitlist for early access.</Text>
              </View>
              <Pressable testID="promo-modal-close" onPress={() => setLearnOpen(false)} hitSlop={10}><Ionicons name="close" size={22} color={colors.textMuted} /></Pressable>
            </View>
            <ScrollView style={{ maxHeight: 420 }} showsVerticalScrollIndicator={false}>
              {FEATURES.map((f) => (
                <View key={f.title} style={styles.feature}>
                  <View style={styles.featIcon}><Ionicons name={f.icon as any} size={18} color={colors.teal} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.featTitle}>{f.title}</Text>
                    <Text style={[type.small, { color: colors.textMuted, marginTop: 3, lineHeight: 17 }]}>{f.desc}</Text>
                  </View>
                </View>
              ))}
            </ScrollView>
            <Pressable testID="promo-modal-join" onPress={join} disabled={joining || joined} style={[styles.btn, styles.btnPrimary, { marginTop: spacing.sm }, (joining || joined) && { opacity: 0.75 }]}>
              {joining ? <ActivityIndicator color={colors.bg} size="small" /> : joined ? <Ionicons name="checkmark" size={15} color={colors.bg} /> : null}
              <Text style={styles.btnPrimaryTxt}>{joined ? " On the waitlist" : "Join Waitlist"}</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  bannerWrap: { marginBottom: spacing.lg },
  sectionHead: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm, marginTop: spacing.sm },
  sectionLabel: { ...type.label },
  card: { backgroundColor: colors.card, borderWidth: 1, borderColor: colors.teal + "44", borderRadius: radius.lg, padding: spacing.sm, gap: spacing.sm },
  heroWrap: { position: "relative", borderRadius: radius.md, overflow: "hidden" },
  hero: { width: "100%", aspectRatio: 0.671, borderRadius: radius.md },
  closeBtn: { position: "absolute", top: 8, right: 8, width: 30, height: 30, borderRadius: 15, backgroundColor: colors.bg + "CC", borderWidth: 1, borderColor: colors.cardBorder, alignItems: "center", justifyContent: "center" },
  btnRow: { flexDirection: "row", gap: spacing.sm },
  btn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 11, borderRadius: radius.md },
  btnPrimary: { backgroundColor: colors.teal },
  btnPrimaryTxt: { color: colors.bg, fontWeight: "800", fontSize: 13 },
  btnGhost: { borderWidth: 1, borderColor: colors.teal + "66" },
  btnGhostTxt: { color: colors.teal, fontWeight: "800", fontSize: 13 },
  modalWrap: { flex: 1, backgroundColor: "#000000AA", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.bgElevated, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.cardBorder },
  modalHead: { flexDirection: "row", alignItems: "flex-start", marginBottom: spacing.md },
  feature: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  featIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.tealGlow, alignItems: "center", justifyContent: "center" },
  featTitle: { ...type.body, fontWeight: "700", fontSize: 14 },
});
