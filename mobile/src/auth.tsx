// Auth context: owner JWT bearer token in SecureStore + biometric (FaceID/fingerprint) unlock.
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import api, { TOKEN_KEY } from "./api";
import { resetWelcomeGate } from "./components/ComingSoonPromo";
import { getItem, setItem, deleteItem } from "./storage";

const BIO_FLAG = "ananta_biometric_enabled";

type Owner = { email: string; role: string } | null;

type AuthCtx = {
  owner: Owner;
  isOwner: boolean;
  ready: boolean;
  biometricEnabled: boolean;
  biometricAvailable: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  setBiometricEnabled: (v: boolean) => Promise<void>;
  authenticateBiometric: () => Promise<boolean>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [owner, setOwner] = useState<Owner>(null);
  const [ready, setReady] = useState(false);
  const [biometricEnabled, setBioEnabled] = useState(false);
  const [biometricAvailable, setBioAvailable] = useState(false);

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

      const token = await getItem(TOKEN_KEY);
      if (token) {
        try {
          const me = await api.me();
          setOwner(me);
        } catch (e: any) {
          // Only drop the session on a real auth rejection. On transient network
          // / 5xx errors keep the token so a relaunch can recover.
          if (e?.status === 401 || e?.status === 403) {
            await deleteItem(TOKEN_KEY);
          }
          setOwner(null);
        }
      }
      setReady(true);
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    await setItem(TOKEN_KEY, res.token);
    resetWelcomeGate();
    setOwner({ email: res.email, role: res.role });
  }, []);

  const logout = useCallback(async () => {
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
