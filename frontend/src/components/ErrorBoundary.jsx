import { Component } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

// App-level error boundary: a render/runtime crash shows a branded fallback with a
// reload action instead of a blank white screen. Scoped per route via `where`.
export default class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, info) {
        // Surface to the console for production log capture; no PII.
        console.error(`[ErrorBoundary${this.props.where ? `:${this.props.where}` : ""}]`, error, info?.componentStack);
    }

    render() {
        if (!this.state.hasError) return this.props.children;
        return (
            <div data-testid="app-error-boundary" className="min-h-screen bg-atlas-bg text-white grid place-items-center p-6">
                <div className="panel border-atlas-border rounded-2xl p-8 max-w-md w-full text-center space-y-4">
                    <div className="w-14 h-14 rounded-2xl grid place-items-center border border-atlas-negative/40 bg-atlas-negative/10 mx-auto">
                        <AlertTriangle className="w-7 h-7 text-atlas-negative" />
                    </div>
                    <div className="font-heading text-xl text-atlas-text">Something went wrong</div>
                    <p className="font-mono text-[12px] text-atlas-textSecondary leading-relaxed">
                        A part of the interface hit an unexpected error. Your data is safe — reloading usually fixes it.
                    </p>
                    <button data-testid="error-boundary-reload" onClick={() => window.location.reload()}
                        className="inline-flex items-center gap-2 rounded-full bg-atlas-cyan text-black font-mono text-xs font-bold px-5 py-2.5 hover:brightness-110 active:scale-95 transition-all">
                        <RotateCcw className="w-4 h-4" /> Reload
                    </button>
                </div>
            </div>
        );
    }
}
