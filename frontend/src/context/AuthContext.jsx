import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { TOKEN_KEY } from "@/lib/api";

const AuthContext = createContext(null);

// Pull an Emergent OAuth session_id out of the URL fragment or query string.
function readSessionId() {
    if (typeof window === "undefined") return null;
    const hash = window.location.hash || "";
    const search = window.location.search || "";
    const fromHash = hash.includes("session_id=")
        ? new URLSearchParams(hash.replace(/^#/, "")).get("session_id")
        : null;
    const fromQuery = new URLSearchParams(search).get("session_id");
    return fromHash || fromQuery || null;
}

function cleanAuthUrl() {
    if (typeof window === "undefined") return;
    window.history.replaceState(null, "", window.location.pathname);
}

export function AuthProvider({ children }) {
    // `owner` holds the authenticated principal for ANY logged-in user
    // (email/password owner + demo, OR Google user). isOwner => any authed session
    // can control THEIR OWN book; house-only endpoints stay backend-guarded (role).
    const [owner, setOwner] = useState(null); // { email, role, name, picture }
    const hasSessionId = typeof window !== "undefined" && !!readSessionId();
    const [ready, setReady] = useState(() => !localStorage.getItem(TOKEN_KEY) && !hasSessionId);

    // On mount: (1) if returning from Google OAuth, exchange the session_id FIRST;
    // otherwise (2) validate any stored token against the backend.
    useEffect(() => {
        let active = true;
        const sessionId = readSessionId();

        if (sessionId) {
            api.googleSession(sessionId)
                .then((res) => {
                    localStorage.setItem(TOKEN_KEY, res.session_token);
                    sessionStorage.removeItem("ananta_welcome_shown");
                    // Full reload (to a clean URL) so every data fetch re-runs with the
                    // new session token → the user's OWN isolated book/settings load.
                    window.location.replace(window.location.pathname);
                })
                .catch(() => {
                    if (active) { toast.error("Google sign-in failed. Please try again."); cleanAuthUrl(); setReady(true); }
                });
            return () => { active = false; };
        }

        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) return undefined;
        api.me()
            .then((me) => { if (active) setOwner(me); })
            .catch(() => {
                localStorage.removeItem(TOKEN_KEY);
                if (active) setOwner(null);
            })
            .finally(() => { if (active) setReady(true); });
        return () => { active = false; };
    }, []);

    // Global session-expiry handling: a 401 from any call flips us to logged-out.
    useEffect(() => {
        const onExpired = () => {
            setOwner((prev) => {
                if (prev) toast.error("Session expired — please sign in again.");
                return null;
            });
        };
        window.addEventListener("ananta:session-expired", onExpired);
        return () => window.removeEventListener("ananta:session-expired", onExpired);
    }, []);

    const login = useCallback(async (email, password) => {
        const res = await api.login(email, password);
        localStorage.setItem(TOKEN_KEY, res.token);
        sessionStorage.removeItem("ananta_welcome_shown");
        setOwner({ email: res.email, role: res.role });
        return res;
    }, []);

    // Continue with Google → Emergent-managed OAuth.
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const loginWithGoogle = useCallback(() => {
        const redirectUrl = window.location.origin + "/";
        window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem(TOKEN_KEY);
        setOwner(null);
        api.logout().catch(() => {});
    }, []);

    const role = owner?.role || null;

    return (
        <AuthContext.Provider
            value={{
                owner,
                isOwner: !!owner,           // any authenticated principal controls its own book
                isHouseOwner: role === "owner" || role === "demo", // house/admin features
                isGoogleUser: role === "user",
                role,
                ready,
                login,
                loginWithGoogle,
                logout,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
