import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "@/AppShell";
import JudgeView from "@/pages/JudgeView";
import LaunchPage from "@/pages/LaunchPage";
import SignUp from "@/pages/SignUp";
import Support from "@/pages/Support";
import Privacy from "@/pages/Privacy";
import { AuthProvider } from "@/context/AuthContext";
import { AccessGateProvider } from "@/context/AccessGateContext";
import ErrorBoundary from "@/components/ErrorBoundary";

export default function App() {
    return (
        <div className="App">
            <ErrorBoundary where="root">
                <AuthProvider>
                    <AccessGateProvider>
                        <BrowserRouter>
                            <Routes>
                                <Route path="/judge" element={<ErrorBoundary where="judge"><JudgeView /></ErrorBoundary>} />
                                <Route path="/launch" element={<ErrorBoundary where="launch"><LaunchPage /></ErrorBoundary>} />
                                <Route path="/signup" element={<ErrorBoundary where="signup"><SignUp /></ErrorBoundary>} />
                                <Route path="/support" element={<ErrorBoundary where="support"><Support /></ErrorBoundary>} />
                                <Route path="/privacy" element={<ErrorBoundary where="privacy"><Privacy /></ErrorBoundary>} />
                                <Route path="/" element={<ErrorBoundary where="app"><AppShell /></ErrorBoundary>} />
                            </Routes>
                        </BrowserRouter>
                    </AccessGateProvider>
                </AuthProvider>
            </ErrorBoundary>
        </div>
    );
}
