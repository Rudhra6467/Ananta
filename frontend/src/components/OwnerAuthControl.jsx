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
    const { isOwner, owner, login, logout } = useAuth();
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
        return (
            <div className="flex items-center gap-2" data-testid="owner-session">
                <span className="hidden md:inline-flex items-center gap-1.5 font-mono text-[10px] font-bold text-atlas-positive uppercase tracking-wider">
                    <ShieldCheck className="w-3.5 h-3.5" /> OWNER
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
                    <LogIn className="w-4 h-4 sm:mr-1.5" /> <span className="hidden sm:inline">Owner Login</span>
                </Button>
            </DialogTrigger>
            <DialogContent className="bg-atlas-bg border-atlas-border" data-testid="owner-login-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading tracking-tight">Owner Access</DialogTitle>
                    <DialogDescription className="font-mono text-xs text-atlas-textSecondary">
                        Public view is read-only. Log in to configure settings, switch environments, and run resets.
                    </DialogDescription>
                </DialogHeader>
                <form onSubmit={submit} className="space-y-4 mt-2">
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
