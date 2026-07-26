// Auth context: owner JWT + Google (Emergent OAuth) session_token in SecureStore,
// plus biometric (FaceID/fingerprint) unlock. The Bearer token (JWT or Google
// session_token) is stored under the same key — the shared backend accepts both.
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import api, { TOKEN_KEY } from "./api";
import { resetWelcomeGate } from "./components/ComingSoonPromo";
import { getItem, setItem, deleteItem } from "./storage";

const BIO_FLAG = "ananta_biometric_enabled";
const AUTH_BASE = "https://auth.emergentagent.com/";

type Owner = { email: string; role: string; name?: string; picture?: string } | null;

type AuthCtx = {
  owner: Owner;
  isOwner: boolean;
  ready: boolean;
  biometricEnabled: boolean;
  biometricAvailable: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  setBiometricEnabled: (v: boolean) => Promise<void>;
  authenticateBiometric: () => Promise<boolean>;
};

const Ctx = createContext<AuthCtx | null>(null);

function parseSessionId(url: string | null | undefined): string | null {
  if (!url) return null;
  const m = url.match(/[#?&]session_id=([^&]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [owner, setOwner] = useState<Owner>(null);
  const [ready, setReady] = useState(false);
  const [biometricEnabled, setBioEnabled] = useState(false);
  const [biometricAvailable, setBioAvailable] = useState(false);

  const finishGoogle = useCallback(async (sessionId: string) => {
    const res = await api.googleSession(sessionId);
    await setItem(TOKEN_KEY, res.session_token);
    resetWelcomeGate();
    setOwner(res.user);
  }, []);

  useEffect(() => {
    (async () => {
      // detect biometric hardware (native only)
      if (Platform.OS !== "web") {
        try {
          const hasHw = await LocalAuthentication.hasHardwareAsync();
          const enrolled = await LocalAuthentication.isEnrolledAsync();
          setBioAvailable(hasHw && enrolled);
        } catch { setBioAvailable(false); }
      }
      const bio = await getItem(BIO_FLAG);
      setBioEnabled(bio === "1");

      // 1. Returning from Google OAuth?
      //   web preview → session_id in window.location; native cold start → initial URL.
      try {
        let sid: string | null = null;
        if (Platform.OS === "web") {
          sid = parseSessionId(typeof window !== "undefined" ? window.location.href : null);
          if (sid && typeof window !== "undefined") {
            window.history.replaceState(null, "", window.location.pathname);
          }
        } else {
          sid = parseSessionId(await Linking.getInitialURL());
        }
        if (sid) {
          await finishGoogle(sid);
          setReady(true);
          return;
        }
      } catch { /* fall through to token check */ }

      // 2. Existing stored session token.
      const token = await getItem(TOKEN_KEY);
      if (token) {
        try {
          const me = await api.me();
          setOwner(me);
        } catch (e: any) {
          if (e?.status === 401 || e?.status === 403) {
            await deleteItem(TOKEN_KEY);
          }
          setOwner(null);
        }
      }
      setReady(true);
    })();
  }, [finishGoogle]);

  // Native hot deep-link listener (app already running when redirect fires).
  useEffect(() => {
    if (Platform.OS === "web") return undefined;
    const sub = Linking.addEventListener("url", ({ url }) => {
      const sid = parseSessionId(url);
      if (sid) finishGoogle(sid).catch(() => {});
    });
    return () => sub.remove();
  }, [finishGoogle]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    await setItem(TOKEN_KEY, res.token);
    resetWelcomeGate();
    setOwner({ email: res.email, role: res.role });
  }, []);

  const loginWithGoogle = useCallback(async () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    if (Platform.OS === "web") {
      const redirectUrl = window.location.origin + "/";
      window.location.href = `${AUTH_BASE}?redirect=${encodeURIComponent(redirectUrl)}`;
      return;
    }
    const redirectUrl = Linking.createURL("auth");
    const authUrl = `${AUTH_BASE}?redirect=${encodeURIComponent(redirectUrl)}`;
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    if (result.type === "success") {
      const sid = parseSessionId(result.url);
      if (sid) await finishGoogle(sid);
    }
  }, [finishGoogle]);

  const logout = useCallback(async () => {
    try { await api.logout?.(); } catch { /* best effort */ }
    await deleteItem(TOKEN_KEY);
    await deleteItem(BIO_FLAG);
    setBioEnabled(false);
    setOwner(null);
  }, []);

  const setBiometricEnabled = useCallback(async (v: boolean) => {
    await setItem(BIO_FLAG, v ? "1" : "0");
    setBioEnabled(v);
  }, []);

  const authenticateBiometric = useCallback(async (): Promise<boolean> => {
    if (Platform.OS === "web") return true;
    try {
      const r = await LocalAuthentication.authenticateAsync({
        promptMessage: "Unlock Ananta",
        fallbackLabel: "Use passcode",
      });
      return r.success;
    } catch {
      return false;
    }
  }, []);

  return (
    <Ctx.Provider
      value={{
        owner,
        isOwner: !!owner,
        ready,
        biometricEnabled,
        biometricAvailable,
        login,
        loginWithGoogle,
        logout,
        setBiometricEnabled,
        authenticateBiometric,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
