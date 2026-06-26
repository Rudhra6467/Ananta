import React, { useEffect, useState } from "react";
import { View, StyleSheet } from "react-native";
import { Stack, useRouter, useSegments } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { AuthProvider, useAuth } from "../src/auth";
import { registerForPushNotificationsAsync } from "../src/push";
import { LoadingView } from "../src/components/StateView";
import { LockScreen } from "../src/components/LockScreen";
import { colors } from "../src/theme";

function RootNav() {
  const { ready, isOwner, biometricEnabled } = useAuth();
  const router = useRouter();
  const segments = useSegments();
  const [unlocked, setUnlocked] = useState(false);

  useEffect(() => {
    if (!ready) return;
    const inAuth = segments[0] === "login";
    if (!isOwner && !inAuth) router.replace("/login");
    else if (isOwner && inAuth) router.replace("/(tabs)");
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
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="asset/[symbol]" options={{ presentation: "card", animation: "slide_from_right" }} />
        <Stack.Screen name="strategy/[id]" options={{ presentation: "card", animation: "slide_from_right" }} />
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
          <StatusBar style="light" />
          <RootNav />
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: colors.bg },
});
