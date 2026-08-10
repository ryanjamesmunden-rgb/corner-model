import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import Dashboard from "@/pages/Dashboard";
import Scanner from "@/pages/Scanner";
import Streaks from "@/pages/Streaks";
import QuickScan from "@/pages/QuickScan";
import Picks from "@/pages/Picks";
import FixtureDetail from "@/pages/FixtureDetail";
import Layout from "@/components/Layout";

function AppRouter() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Layout><Dashboard /></Layout>} />
      <Route path="/scanner" element={<Layout><Scanner /></Layout>} />
      <Route path="/quick-scan" element={<Layout><QuickScan /></Layout>} />
      <Route path="/picks" element={<Layout><Picks /></Layout>} />
      <Route path="/streaks" element={<Layout><Streaks /></Layout>} />
      <Route path="/fixture/:id" element={<Layout><FixtureDetail /></Layout>} />
      <Route path="*" element={<Navigate to="/scanner" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AppRouter />
        <Toaster theme="dark" position="top-right" richColors />
      </BrowserRouter>
    </div>
  );
}

export default App;
