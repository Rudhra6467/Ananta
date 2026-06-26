// Expo push notification registration. Works only on a physical device with a
// production/development build (NOT Expo Go / web preview). Safe no-op elsewhere.
import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import api from "./api";
import { getItem, setItem } from "./storage";

export const PUSH_TOKEN_KEY = "ananta_push_token";
const NOTIF_PREFS_KEY = "ananta_notif_prefs";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export async function registerForPushNotificationsAsync(): Promise<string | null> {
  try {
    if (Platform.OS === "web" || !Device.isDevice) return null;

    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;
    if (existing !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== "granted") return null;

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Ananta Alerts",
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#14E0C9",
      });
    }

    const projectId =
      Constants?.expoConfig?.extra?.eas?.projectId ??
      Constants?.easConfig?.projectId;

    const tokenResp = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined
    );
    const pushToken = tokenResp.data;
    if (pushToken) {
      await setItem(PUSH_TOKEN_KEY, pushToken);
      let prefs: Record<string, boolean> | undefined;
      try {
        const raw = await getItem(NOTIF_PREFS_KEY);
        if (raw) prefs = JSON.parse(raw);
      } catch {}
      await api.registerPushToken(pushToken, Platform.OS, prefs).catch(() => {});
    }
    return pushToken;
  } catch {
    // Push not available in this environment (Expo Go / preview / no build).
    return null;
  }
}
