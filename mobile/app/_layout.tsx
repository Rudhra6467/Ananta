import React, { useEffect, useState } from "react";
import { View, StyleSheet } from "react-native";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { AuthProvider, useAuth } from "../src/auth";
import { AccessGateProvider } from "../src/access";
import { registerForPushNotificationsAsync } from "../src/push";
import { getItem } from "../src/storage";
import { LoadingView, ErrorView } from "../src/components/StateView";
import { LockScreen } from "../src/components/LockScreen";
import { colors } from "../src/theme";

function RootNav() {
  const { ready, isOwner, biometricEnabled } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const [unlocked, setUnlocked] = useState(false);

  useEffect(() => {
    if (!ready) return;
    (async () => {
      const inAuth = segments[0] === "login";
      const inOnboard = segments[0] === "onboarding";
      if (!isOwner) { if (!inAuth) router.replace("/login"); return; }
      const done = (await getItem("ananta_onboarded")) === "1";
      if (!done && !inOnboard) { router.replace("/onboarding"); return; }
      if (done && inAuth) router.replace("/(tabs)");
    })();
  }, [ready, isOwner, segments]);

  // Register for push once owner session is active (no-op on Expo Go / web).
  useEffect(() => {
    if (ready && isOwner) registerForPushNotificationsAsync();
  }, [ready, isOwner]);

  if (!ready) {
    return (
      <View style={styles.fill}>
        <LoadingView label="Ananta" />
      </View>
    );
  }

  const needsBiometric = isOwner && biometricEnabled && !unlocked;

  return (
    <View style={styles.fill}>
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.bg },
          animation: "fade",
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="login" />
        <Stack.Screen name="onboarding" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="asset/[symbol]" options={{ presentation: "card", animation: "slide_from_right" }} />
        <Stack.Screen name="strategy/[id]" options={{ presentation: "card", animation: "slide_from_right" }} />
        <Stack.Screen name="account" options={{ presentation: "modal", animation: "slide_from_bottom" }} />
      </Stack>
      {needsBiometric && <LockScreen onUnlock={() => setUnlocked(true)} />}
    </View>
  );
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.fill}>
      <SafeAreaProvider>
        <AuthProvider>
          <AccessGateProvider>
            <StatusBar style="light" />
            <RootNav />
          </AccessGateProvider>
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

// expo-router catches render/runtime errors in this segment and renders this
// branded fallback (with retry) instead of a red LogBox / blank screen.
export function ErrorBoundary({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <SafeAreaProvider>
      <View style={styles.fill} testID="app-error-boundary">
        <ErrorView message={error?.message || "An unexpected error occurred."} onRetry={retry} />
      </View>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
});
