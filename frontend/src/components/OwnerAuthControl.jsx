import { useState } from "react";
import { Eye, EyeOff, LogIn, LogOut, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";

export default function OwnerAuthControl() {
    const { isOwner, owner, login, loginWithGoogle, logout } = useAuth();
    const [open, setOpen] = useState(false);
    const [email, setEmail] = useState("owner@ananta.ai");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [busy, setBusy] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await login(email.trim(), password);
            toast.success("Owner session active — full control enabled.");
            setOpen(false);
            setPassword("");
        } catch (err) {
            const msg = err?.response?.status === 429
                ? "Too many attempts. Try again shortly."
                : "Invalid email or password.";
            toast.error(msg);
        } finally {
            setBusy(false);
        }
    };

    if (isOwner) {
        const isHouse = owner?.role === "owner" || owner?.role === "demo";
        const label = isHouse ? "OWNER" : (owner?.name || owner?.email || "SIGNED IN");
        return (
            <div className="flex items-center gap-2" data-testid="owner-session">
                <span className="hidden md:inline-flex items-center gap-1.5 font-mono text-[10px] font-bold text-atlas-positive uppercase tracking-wider max-w-[160px] truncate">
                    <ShieldCheck className="w-3.5 h-3.5 shrink-0" /> {label}
                </span>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={logout}
                    data-testid="owner-logout-button"
                    className="font-mono text-[11px] uppercase tracking-wider text-atlas-textSecondary hover:text-white h-8 px-2"
                >
                    <LogOut className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Logout</span>
                </Button>
            </div>
        );
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button
                    variant="outline"
                    size="sm"
                    data-testid="owner-login-button"
                    className="font-mono text-[11px] uppercase tracking-wider border-atlas-border bg-transparent hover:bg-atlas-border/40 h-8 px-2.5"
                >
                    <LogIn className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Sign In</span>
                </Button>
            </DialogTrigger>
            <DialogContent className="bg-atlas-bg border-atlas-border" data-testid="owner-login-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading tracking-tight">Sign In</DialogTitle>
                    <DialogDescription className="font-mono text-xs text-atlas-textSecondary">
                        Continue with Google to create your own paper account, or log in as owner.
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={submit} className="space-y-4 mt-2">
                    <Button
                        type="button"
                        onClick={loginWithGoogle}
                        data-testid="google-signin-button"
                        variant="outline"
                        className="w-full bg-white text-[#1f1f1f] hover:bg-white/90 border-atlas-border font-mono text-xs uppercase tracking-wider font-bold gap-2"
                    >
                        <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
                            <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                            <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                            <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                            <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                        </svg>
                        Continue with Google
                    </Button>
                    <div className="flex items-center gap-3">
                        <div className="h-px flex-1 bg-atlas-border" />
                        <span className="font-mono text-[10px] text-atlas-textSecondary uppercase tracking-wider">or owner login</span>
                        <div className="h-px flex-1 bg-atlas-border" />
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="owner-email" className="label-tag text-[10px]">EMAIL</Label>
                        <Input
                            id="owner-email"
                            data-testid="owner-email-input"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            autoComplete="username"
                            className="font-mono text-sm bg-atlas-panel border-atlas-border"
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label htmlFor="owner-password" className="label-tag text-[10px]">PASSWORD</Label>
                        <div className="relative">
                            <Input
                                id="owner-password"
                                data-testid="owner-password-input"
                                type={showPassword ? "text" : "password"}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                autoComplete="current-password"
                                className="font-mono text-sm bg-atlas-panel border-atlas-border pr-10"
                            />
                            <button
                                type="button"
                                data-testid="toggle-password-visibility"
                                onClick={() => setShowPassword((v) => !v)}
                                aria-label={showPassword ? "Hide password" : "Show password"}
                                className="absolute inset-y-0 right-0 flex items-center px-3 text-atlas-textSecondary hover:text-white transition-colors"
                            >
                                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                    <Button
                        type="submit"
                        disabled={busy || !password}
                        data-testid="owner-login-submit"
                        className="w-full bg-atlas-cyan text-atlas-bg hover:bg-atlas-cyan/90 font-mono text-xs uppercase tracking-wider font-bold"
                    >
                        {busy ? "Authenticating…" : "Log In"}
                    </Button>
                </form>
            </DialogContent>
        </Dialog>
    );
}
