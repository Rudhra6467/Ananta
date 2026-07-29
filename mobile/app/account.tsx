import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, Alert, Modal, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../src/auth";
import api from "../src/api";
import { deleteItem } from "../src/storage";
import ComingSoonPromo from "../src/components/ComingSoonPromo";
import { colors, spacing, type, radius } from "../src/theme";

// Account overlay — opened by tapping the Ananta logo. Mirrors the layout in the
// reference (Profile header · Features · Settings). Per the current sprint only the
// user's real login credentials are populated; feature/settings rows are visual
// placeholders ("Soon") to be wired up in a later sprint.

type RowProps = {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  pill?: string;
  pillTone?: "muted" | "accent";
  testID: string;
  onPress?: () => void;
};

function Row({ icon, label, pill, pillTone = "muted", testID, onPress }: RowProps) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      <View style={styles.rowLeft}>
        <View style={styles.iconWrap}>
          <Ionicons name={icon} size={18} color={colors.textMuted} />
        </View>
        <Text style={styles.rowLabel}>{label}</Text>
      </View>
      <View style={styles.rowRight}>
        {pill ? (
          <View style={[styles.pill, pillTone === "accent" && styles.pillAccent]}>
            <Text style={[styles.pillText, pillTone === "accent" && styles.pillTextAccent]}>{pill}</Text>
          </View>
        ) : null}
        <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
      </View>
    </Pressable>
  );
}

function HealthRow({ label, ok, okText, badText, neutral }: { label: string; ok?: boolean; okText: string; badText?: string; neutral?: boolean }) {
  const dot = neutral || ok == null ? colors.textFaint : ok ? colors.teal : colors.red;
  const txt = neutral || ok == null ? colors.textMuted : ok ? colors.teal : colors.red;
  const value = ok == null && !neutral ? "…" : ok === false ? (badText || okText) : okText;
  return (
    <View style={styles.credRow} testID={`account-health-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <Ionicons name="pulse" size={15} color={colors.textFaint} />
        <Text style={styles.credKey}>{label}</Text>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
        <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: dot }} />
        <Text style={[styles.credVal, { color: txt }]}>{value}</Text>
      </View>
    </View>
  );
}

function EditInput({ label, ...props }: any) {
  return (
    <View style={{ marginBottom: spacing.sm }}>
      <Text style={styles.editInputLabel}>{label}</Text>
      <TextInput
        {...props}
        placeholderTextColor={colors.textFaint}
        autoCapitalize="none"
        style={styles.editInput}
      />
    </View>
  );
}


export default function AccountOverlay() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { owner, logout, isOwner } = useAuth();

  const email = owner?.email || "—";
  const [profile, setProfile] = useState<any>(null);
  const displayName = profile?.display_name || owner?.name || (email !== "—" ? email.split("@")[0] : "Guest");
  const initials = ((profile?.display_name || email).replace(/@.*/, "") || "A").slice(0, 2).toUpperCase();
  const [health, setHealth] = useState<any>(null);
  const [promoOpen, setPromoOpen] = useState(false);
  const [edit, setEdit] = useState<null | { mode: "name" | "email" | "password" }>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOwner) api.getProfile().then(setProfile).catch(() => {});
  }, [isOwner]);

  const openEdit = (mode: "name" | "email" | "password") => {
    if (!isOwner) { Alert.alert("Owner login required"); return; }
    setForm(mode === "name" ? { display_name: profile?.display_name || "" } : {});
    setEdit({ mode });
  };
  const saveEdit = async () => {
    if (!edit) return;
    setSaving(true);
    try {
      if (edit.mode === "name") {
        const p = await api.updateProfile({ display_name: form.display_name || "" });
        setProfile(p);
      } else if (edit.mode === "email") {
        await api.changeEmail(form.current_password || "", form.new_email || "");
        Alert.alert("Email updated", "Please sign in again with your new email.");
        setEdit(null); setSaving(false); await logout(); router.replace("/login"); return;
      } else if (edit.mode === "password") {
        await api.changePassword(form.current_password || "", form.new_password || "");
        Alert.alert("Password changed");
      }
      setEdit(null);
    } catch (e: any) {
      Alert.alert("Update failed", e?.response?.data?.detail || e?.message || "Please try again.");
    } finally { setSaving(false); }
  };

  // Live platform status (moved here from Workspace › Engine & Risk).
  useEffect(() => {
    let active = true;
    const load = async () => {
      const h: any = {};
      try { await api.riskStatus(); h.backend = true; } catch { h.backend = false; }
      try { const e = await api.getEnvironment(); h.mode = e.mode; h.gate = e.ready_to_trade; } catch { h.mode = "—"; }
      if (active) setHealth(h);
    };
    load();
    const t = setInterval(load, 15000);
    return () => { active = false; clearInterval(t); };
  }, []);

  const onLogout = async () => {
    await logout();
    router.replace("/login");
  };

  const onResetPaper = () => {
    if (!isOwner) { Alert.alert("Owner login required", "Log in as the owner to reset paper trading."); return; }
    Alert.alert(
      "Reset Paper Trading?",
      "This permanently clears all open positions, closed trades, P&L and cached performance. The bot starts fresh on the current logic. This cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reset", style: "destructive", onPress: async () => {
            try {
              await api.portfolioReset();
              Alert.alert("Done", "Paper trading state has been reset. Ananta starts fresh with zero trades.");
            } catch (e: any) {
              Alert.alert("Reset failed", e?.response?.data?.detail || e?.message || "Please try again.");
            }
          },
        },
      ],
    );
  };

  return (
    <View style={styles.fill}>
      {/* header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Text style={styles.title}>Account</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
          {isOwner && (
            <Pressable testID="account-settings-gear" onPress={() => router.push("/settings")} hitSlop={12} style={styles.closeBtn}>
              <Ionicons name="settings-outline" size={20} color={colors.text} />
            </Pressable>
          )}
          <Pressable testID="account-close-btn" onPress={() => router.back()} hitSlop={12} style={styles.closeBtn}>
            <Ionicons name="close" size={22} color={colors.text} />
          </Pressable>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xxl }}
        showsVerticalScrollIndicator={false}
      >
        {/* profile header */}
        <Pressable testID="account-profile-header" onPress={() => openEdit("name")} style={({ pressed }) => [styles.profile, pressed && styles.rowPressed]}>
          <View>
            <View style={styles.avatar}>
              <Text style={styles.avatarText}>{initials}</Text>
            </View>
            {isOwner && (
              <View style={styles.avatarEdit}><Ionicons name="pencil" size={11} color={colors.bg} /></View>
            )}
          </View>
          <View style={styles.profileInfo}>
            <Text testID="account-display-name" style={styles.profileName} numberOfLines={1}>{displayName}</Text>
            <Text testID="account-email" style={styles.profileEmail} numberOfLines={1}>{email}</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
        </Pressable>

        {/* credentials — editable */}
        <Text style={styles.sectionLabel}>Login & Auth</Text>
        <View style={styles.card}>
          <View style={styles.credRow}>
            <Text style={styles.credKey}>Email</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10, flexShrink: 1 }}>
              <Text testID="account-cred-email" style={styles.credVal} numberOfLines={1}>{email}</Text>
              {isOwner && <Pressable testID="account-edit-email" onPress={() => openEdit("email")}><Text style={styles.editLink}>Edit</Text></Pressable>}
            </View>
          </View>
          <View style={styles.divider} />
          <View style={styles.credRow}>
            <Text style={styles.credKey}>Password</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
              <Text testID="account-cred-password" style={styles.credVal}>{"\u2022".repeat(10)}</Text>
              {isOwner && <Pressable testID="account-edit-password" onPress={() => openEdit("password")}><Text style={styles.editLink}>Change</Text></Pressable>}
            </View>
          </View>
        </View>

        {/* System Health (moved from Workspace › Engine & Risk) */}
        <Text style={styles.sectionLabel}>System Health</Text>
        <View style={styles.card} testID="account-system-health">
          <HealthRow label="Backend API" ok={health?.backend} okText="Online" badText="Unreachable" />
          <View style={styles.divider} />
          <HealthRow label="Trading Mode" neutral okText={(health?.mode || "—").toUpperCase()} />
          <View style={styles.divider} />
          <HealthRow label="Live Gate" ok={health?.gate} okText="Armed" badText="Closed" />
        </View>

        {/* Guided setup */}
        <Text style={styles.sectionLabel}>Guided Setup</Text>
        <View style={styles.card}>
          <Pressable testID="account-replay-onboarding" onPress={async () => { await deleteItem("ananta_onboarded"); router.replace("/onboarding"); }} style={styles.credRow}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name="play-circle-outline" size={17} color={colors.teal} />
              <Text style={styles.credKey}>Replay Onboarding</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
          </Pressable>
        </View>

        {/* invite / promo placeholder banner */}
        <View testID="account-invite-banner" style={styles.banner}>
          <View style={{ flex: 1 }}>
            <Text style={styles.bannerTitle}>Invite friends</Text>
            <Text style={styles.bannerSub}>Earn a bonus once they sign up and trade.</Text>
          </View>
          <View style={styles.bannerIcon}>
            <Ionicons name="gift" size={22} color={colors.gold} />
          </View>
        </View>

        {/* Features (placeholder rows) */}
        <Text style={styles.sectionLabel}>Features</Text>
        <View style={styles.card}>
          <Row icon="link-outline" label="Exchange Connection" pill="Kraken" testID="account-feature-exchange" />
          <View style={styles.divider} />
          <Row icon="person-add-outline" label="Referrals" pill="Soon" pillTone="accent" testID="account-feature-referrals" />
          <View style={styles.divider} />
          <Row icon="gift-outline" label="Offers" pill="Soon" testID="account-feature-offers" />
          <View style={styles.divider} />
          <Row icon="bar-chart-outline" label="Earn" pill="Soon" testID="account-feature-earn" />
          <View style={styles.divider} />
          <Row icon="document-text-outline" label="Tax reporting" pill="Soon" testID="account-feature-tax" />
        </View>

        {/* Settings (placeholder rows) */}
        <Text style={styles.sectionLabel}>Settings</Text>
        <View style={styles.card}>
          <Row icon="sparkles-outline" label="Coming Up" pill="New" pillTone="accent" testID="account-coming-up" onPress={() => setPromoOpen(true)} />
          <View style={styles.divider} />
          <Row icon="card-outline" label="Payment methods" pill="Soon" testID="account-setting-payments" />
          <View style={styles.divider} />
          <Row icon="notifications-outline" label="Notifications" pill="Soon" testID="account-setting-notifications" />
          <View style={styles.divider} />
          <Row icon="shield-checkmark-outline" label="Security" pill="Soon" testID="account-setting-security" />
        </View>

        {/* Paper Trading — fresh start */}
        <Text style={styles.sectionLabel}>Paper Trading</Text>
        <View style={styles.card}>
          <Pressable testID="account-reset-paper" onPress={onResetPaper} style={({ pressed }) => [styles.credRow, pressed && styles.rowPressed]}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
              <Ionicons name="refresh-circle-outline" size={18} color={colors.red} />
              <View>
                <Text style={[styles.credKey, { color: colors.red }]}>Reset Paper Trading State</Text>
                <Text style={styles.resetSub}>Clears positions, trades, P&L & cached performance</Text>
              </View>
            </View>
            <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
          </Pressable>
        </View>

        {/* Log out */}
        <Pressable testID="account-logout-btn" onPress={onLogout} style={({ pressed }) => [styles.logout, pressed && styles.rowPressed]}>
          <Ionicons name="log-out-outline" size={18} color={colors.red} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>

        <Text style={styles.footer}>Ananta.AI · Signed in as {email}</Text>
      </ScrollView>

      {/* edit profile / credentials modal */}
      <Modal visible={!!edit} transparent animationType="slide" onRequestClose={() => setEdit(null)}>
        <View style={styles.promoOverlay}>
          <View style={[styles.editSheet, { paddingBottom: insets.bottom + spacing.md }]} testID="account-edit-sheet">
            <View style={styles.promoHead}>
              <Text style={styles.promoHeadTitle}>
                {edit?.mode === "name" ? "Edit display name" : edit?.mode === "email" ? "Change email" : "Change password"}
              </Text>
              <Pressable testID="account-edit-close" onPress={() => setEdit(null)} hitSlop={12}>
                <Ionicons name="close" size={22} color={colors.text} />
              </Pressable>
            </View>
            {edit?.mode === "name" && (
              <EditInput label="Display name" testID="edit-display-name" value={form.display_name || ""} placeholder="e.g. Vamsi Madhav" onChangeText={(v) => setForm({ display_name: v })} />
            )}
            {edit?.mode === "email" && (<>
              <EditInput label="New email" testID="edit-new-email" value={form.new_email || ""} placeholder="you@example.com" keyboardType="email-address" onChangeText={(v) => setForm({ ...form, new_email: v })} />
              <EditInput label="Current password" testID="edit-email-current-pw" value={form.current_password || ""} secureTextEntry onChangeText={(v) => setForm({ ...form, current_password: v })} />
            </>)}
            {edit?.mode === "password" && (<>
              <EditInput label="Current password" testID="edit-current-pw" value={form.current_password || ""} secureTextEntry onChangeText={(v) => setForm({ ...form, current_password: v })} />
              <EditInput label="New password (min 8)" testID="edit-new-pw" value={form.new_password || ""} secureTextEntry onChangeText={(v) => setForm({ ...form, new_password: v })} />
            </>)}
            <Pressable testID="account-edit-save" onPress={saveEdit} disabled={saving} style={styles.saveBtn}>
              <Text style={styles.saveBtnTxt}>{saving ? "SAVING…" : "SAVE"}</Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      {/* Coming Up — reuses the Coming Soon promo (features + join waitlist) */}
      <Modal visible={promoOpen} transparent animationType="slide" onRequestClose={() => setPromoOpen(false)}>
        <View style={styles.promoOverlay}>
          <View style={[styles.promoSheet, { paddingBottom: insets.bottom + spacing.md }]} testID="account-coming-up-sheet">
            <View style={styles.promoHead}>
              <Text style={styles.promoHeadTitle}>Coming Up</Text>
              <Pressable testID="account-coming-up-close" onPress={() => setPromoOpen(false)} hitSlop={12}>
                <Ionicons name="close" size={22} color={colors.text} />
              </Pressable>
            </View>
            <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingTop: spacing.sm }}>
              <ComingSoonPromo variant="inline" />
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  title: { ...type.h2 },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  profile: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: radius.pill,
    backgroundColor: colors.cardPressed,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: colors.text, fontSize: 18, fontWeight: "800", letterSpacing: 1 },
  avatarEdit: { position: "absolute", bottom: -2, right: -2, width: 18, height: 18, borderRadius: 9, backgroundColor: colors.teal, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.bg },
  editLink: { color: colors.teal, fontSize: 12, fontWeight: "700" },
  editSheet: { backgroundColor: colors.bgElevated, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: spacing.lg, borderTopWidth: 1, borderColor: colors.cardBorder },
  editInputLabel: { color: colors.textFaint, fontSize: 10, fontWeight: "800", letterSpacing: 0.8, marginBottom: 6, textTransform: "uppercase" },
  editInput: { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.cardBorder, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, color: colors.text, fontSize: 15 },
  saveBtn: { marginTop: spacing.sm, backgroundColor: colors.teal, borderRadius: radius.md, paddingVertical: 14, alignItems: "center" },
  saveBtnTxt: { color: colors.bg, fontSize: 13, fontWeight: "800", letterSpacing: 1 },
  profileInfo: { flex: 1, marginLeft: spacing.md },
  profileName: { ...type.h3, marginBottom: 2 },
  profileEmail: { ...type.small, color: colors.textMuted },
  sectionLabel: { ...type.label, marginBottom: spacing.sm, marginTop: spacing.sm },
  card: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.lg,
    overflow: "hidden",
    marginBottom: spacing.lg,
  },
  credRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  credKey: { ...type.bodyMuted },
  resetSub: { ...type.small, fontSize: 11, color: colors.textFaint, marginTop: 1 },
  promoOverlay: { flex: 1, backgroundColor: "#000000AA", justifyContent: "flex-end" },
  promoSheet: { backgroundColor: colors.bg, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: colors.cardBorder, paddingHorizontal: spacing.lg, paddingTop: spacing.md, maxHeight: "90%" },
  promoHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.xs },
  promoHeadTitle: { color: colors.text, fontSize: 18, fontWeight: "800" },
  credVal: { ...type.body, fontWeight: "600", flexShrink: 1, marginLeft: spacing.md, textAlign: "right" },
  divider: { height: 1, backgroundColor: colors.cardBorder },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  bannerTitle: { ...type.h3, marginBottom: 2 },
  bannerSub: { ...type.small, color: colors.textMuted },
  bannerIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.card,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
  },
  rowPressed: { backgroundColor: colors.cardPressed },
  rowLeft: { flexDirection: "row", alignItems: "center", flex: 1 },
  iconWrap: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.cardPressed,
    marginRight: spacing.md,
  },
  rowLabel: { ...type.body, fontWeight: "600" },
  rowRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  pill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.cardPressed,
  },
  pillAccent: { backgroundColor: colors.tealGlow },
  pillText: { ...type.small, color: colors.textMuted, fontSize: 11 },
  pillTextAccent: { color: colors.teal },
  logout: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.lg,
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  logoutText: { ...type.body, color: colors.red, fontWeight: "700" },
  footer: { ...type.small, color: colors.textFaint, textAlign: "center", marginTop: spacing.lg },
});
