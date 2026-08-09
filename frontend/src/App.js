import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import AuthCallback from "@/pages/AuthCallback";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Scanner from "@/pages/Scanner";
import Streaks from "@/pages/Streaks";
import QuickScan from "@/pages/QuickScan";
import Picks from "@/pages/Picks";
import FixtureDetail from "@/pages/FixtureDetail";
import Layout from "@/components/Layout";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
        <span className="font-mono text-sm animate-pulse">Loading…</span>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/scanner" element={<ProtectedRoute><Scanner /></ProtectedRoute>} />
      <Route path="/quick-scan" element={<ProtectedRoute><QuickScan /></ProtectedRoute>} />
      <Route path="/picks" element={<ProtectedRoute><Picks /></ProtectedRoute>} />
      <Route path="/streaks" element={<ProtectedRoute><Streaks /></ProtectedRoute>} />
      <Route path="/fixture/:id" element={<ProtectedRoute><FixtureDetail /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/scanner" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster theme="dark" position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
