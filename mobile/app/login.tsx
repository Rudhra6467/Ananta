import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../src/auth";
import { useAccessGate } from "../src/access";
import { Logo } from "../src/components/Logo";
import { colors, spacing, radius, type } from "../src/theme";

export default function Login() {
  const { login } = useAuth();
  const { gate } = useAccessGate();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!email || !password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (e: any) {
      setError(e?.message || "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.fill}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View style={[styles.container, { paddingTop: insets.top + spacing.xxl }]}>
        <View style={styles.brand}>
          <Logo size={56} showWord color="#D2D6DC" />
          <Text style={[type.bodyMuted, { marginTop: spacing.md, textAlign: "center" }]}>
            The operator&apos;s cockpit. Monitor the algorithm, manage positions, stay in control.
          </Text>
        </View>

        <View style={styles.form}>
          <Text style={type.label}>Email</Text>
          <TextInput
            testID="login-email-input"
            value={email}
            onChangeText={setEmail}
            placeholder="owner@ananta.ai"
            placeholderTextColor={colors.textFaint}
            autoCapitalize="none"
            keyboardType="email-address"
            autoCorrect={false}
            style={styles.input}
          />

          <Text style={[type.label, { marginTop: spacing.md }]}>Password</Text>
          <View style={styles.pwRow}>
            <TextInput
              testID="login-password-input"
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={colors.textFaint}
              secureTextEntry={!showPw}
              autoCapitalize="none"
              style={[styles.input, { flex: 1, marginBottom: 0 }]}
              onSubmitEditing={submit}
            />
            <Pressable testID="toggle-password-btn" onPress={() => setShowPw((s) => !s)} style={styles.eye}>
              <Ionicons name={showPw ? "eye-off-outline" : "eye-outline"} size={20} color={colors.textMuted} />
            </Pressable>
          </View>

          {error ? (
            <Text testID="login-error" style={styles.error}>
              {error}
            </Text>
          ) : null}

          <Pressable
            testID="login-submit-btn"
            onPress={submit}
            disabled={busy}
            style={({ pressed }) => [styles.submit, (busy || pressed) && { opacity: 0.85 }]}
          >
            {busy ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.submitText}>Sign in</Text>
            )}
          </Pressable>
        </View>

        <Text style={[type.small, { textAlign: "center", marginTop: spacing.xl }]}>
          Single-operator access · sessions secured on-device
        </Text>

        <Pressable testID="request-access-btn" onPress={() => gate("Full Ananta access")} style={styles.requestBtn}>
          <Ionicons name="mail-outline" size={15} color={colors.teal} />
          <Text style={styles.requestTxt}>Not the owner? Request early access</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
  container: { flex: 1, paddingHorizontal: spacing.lg },
  brand: { alignItems: "center", marginBottom: spacing.xxl },
  form: { marginTop: spacing.md },
  input: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.text,
    fontSize: 16,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  pwRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  eye: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  error: { color: colors.red, marginTop: spacing.md, fontWeight: "600" },
  submit: {
    backgroundColor: colors.teal,
    borderRadius: radius.pill,
    paddingVertical: spacing.md + 2,
    alignItems: "center",
    marginTop: spacing.lg,
  },
  submitText: { color: colors.bg, fontWeight: "800", fontSize: 16 },
  requestBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: spacing.lg, paddingVertical: spacing.sm },
  requestTxt: { color: colors.teal, fontWeight: "700", fontSize: 13 },
});
