import React, { useEffect, useState } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../src/auth";
import api from "../src/api";
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

export default function AccountOverlay() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { owner, logout } = useAuth();

  const email = owner?.email || "—";
  const initials = (email.split("@")[0] || "A").slice(0, 2).toUpperCase();
  const [health, setHealth] = useState<any>(null);

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

  return (
    <View style={styles.fill}>
      {/* header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Text style={styles.title}>Account</Text>
        <Pressable testID="account-close-btn" onPress={() => router.back()} hitSlop={12} style={styles.closeBtn}>
          <Ionicons name="close" size={22} color={colors.text} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: insets.bottom + spacing.xxl }}
        showsVerticalScrollIndicator={false}
      >
        {/* profile header */}
        <Pressable testID="account-profile-header" style={({ pressed }) => [styles.profile, pressed && styles.rowPressed]}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{initials}</Text>
          </View>
          <View style={styles.profileInfo}>
            <Text style={styles.profileName} numberOfLines={1}>Ananta Owner</Text>
            <Text testID="account-email" style={styles.profileEmail} numberOfLines={1}>{email}</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
        </Pressable>

        {/* credentials (only real data this sprint) */}
        <Text style={styles.sectionLabel}>Login Credentials</Text>
        <View style={styles.card}>
          <View style={styles.credRow}>
            <Text style={styles.credKey}>Email</Text>
            <Text testID="account-cred-email" style={styles.credVal} numberOfLines={1}>{email}</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.credRow}>
            <Text style={styles.credKey}>Password</Text>
            <Text testID="account-cred-password" style={styles.credVal}>{"\u2022".repeat(10)}</Text>
          </View>
          <View style={styles.divider} />
          <View style={styles.credRow}>
            <Text style={styles.credKey}>Authentication</Text>
            <Text style={styles.credVal}>Secure token (JWT)</Text>
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
          <Row icon="card-outline" label="Payment methods" pill="Soon" testID="account-setting-payments" />
          <View style={styles.divider} />
          <Row icon="notifications-outline" label="Notifications" pill="Soon" testID="account-setting-notifications" />
          <View style={styles.divider} />
          <Row icon="shield-checkmark-outline" label="Security" pill="Soon" testID="account-setting-security" />
        </View>

        {/* Log out */}
        <Pressable testID="account-logout-btn" onPress={onLogout} style={({ pressed }) => [styles.logout, pressed && styles.rowPressed]}>
          <Ionicons name="log-out-outline" size={18} color={colors.red} />
          <Text style={styles.logoutText}>Log out</Text>
        </Pressable>

        <Text style={styles.footer}>Ananta.AI · Signed in as {email}</Text>
      </ScrollView>
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
