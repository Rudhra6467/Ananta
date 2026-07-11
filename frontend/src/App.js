import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "@/AppShell";
import JudgeView from "@/pages/JudgeView";
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
                                <Route path="/" element={<ErrorBoundary where="app"><AppShell /></ErrorBoundary>} />
                            </Routes>
                        </BrowserRouter>
                    </AccessGateProvider>
                </AuthProvider>
            </ErrorBoundary>
        </div>
    );
}
