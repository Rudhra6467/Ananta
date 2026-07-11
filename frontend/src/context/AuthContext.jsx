import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { TOKEN_KEY } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [owner, setOwner] = useState(null); // { email, role } when logged in
    const [ready, setReady] = useState(() => !localStorage.getItem(TOKEN_KEY));

    // On mount, validate any stored token against the backend (async only).
    useEffect(() => {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) return undefined;
        let active = true;
        api.me()
            .then((me) => { if (active) setOwner(me); })
            .catch(() => {
                localStorage.removeItem(TOKEN_KEY);
                if (active) setOwner(null);
            })
            .finally(() => { if (active) setReady(true); });
        return () => { active = false; };
    }, []);

    // Global session-expiry handling: a 401 from any call flips us to logged-out
    // (read-only) state and tells the user, instead of silently failing writes.
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
        setOwner({ email: res.email, role: res.role });
        return res;
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem(TOKEN_KEY);
        setOwner(null);
        api.logout().catch(() => {});
    }, []);

    return (
        <AuthContext.Provider value={{ owner, isOwner: !!owner, ready, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
