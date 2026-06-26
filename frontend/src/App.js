import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "@/AppShell";
import JudgeView from "@/pages/JudgeView";
import { AuthProvider } from "@/context/AuthContext";

export default function App() {
    return (
        <div className="App">
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/judge" element={<JudgeView />} />
                        <Route path="/" element={<AppShell />} />
                    </Routes>
                </BrowserRouter>
            </AuthProvider>
        </div>
    );
}
