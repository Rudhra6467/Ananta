import { createContext, useCallback, useContext, useEffect, useState } from "react";
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
