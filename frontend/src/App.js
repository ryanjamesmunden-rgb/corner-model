import "@/App.css";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import { AuthProvider } from "@/context/AuthContext";

// Each route is its own chunk: landing on the Scanner shouldn't download and parse
// Streaks, Picks and the fixture detail page before it can paint.
const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Scanner = lazy(() => import("@/pages/Scanner"));
const Streaks = lazy(() => import("@/pages/Streaks"));
const QuickScan = lazy(() => import("@/pages/QuickScan"));
const Picks = lazy(() => import("@/pages/Picks"));
const FixtureDetail = lazy(() => import("@/pages/FixtureDetail"));
const Join = lazy(() => import("@/pages/Join"));
const Saved = lazy(() => import("@/pages/Saved"));

const RouteFallback = () => (
  <div className="py-20 text-center text-muted-foreground animate-pulse font-mono-data text-sm">
    Loading…
  </div>
);

// Suspense sits inside Layout, not around the router: the header, nav and league
// picker stay painted while a route chunk loads, and only the content area swaps.
const page = (Component) => (
  <Layout>
    <Suspense fallback={<RouteFallback />}>
      <Component />
    </Suspense>
  </Layout>
);

function AppRouter() {
  return (
    <Routes>
      <Route path="/dashboard" element={page(Dashboard)} />
      <Route path="/scanner" element={page(Scanner)} />
      <Route path="/quick-scan" element={page(QuickScan)} />
      <Route path="/picks" element={page(Picks)} />
      <Route path="/streaks" element={page(Streaks)} />
      <Route path="/saved" element={page(Saved)} />
      <Route path="/fixture/:id" element={page(FixtureDetail)} />
      {/* Deliberately OUTSIDE page(): the subscription page is for people who are not
          members yet, so it carries no app chrome — no league switcher, no nav to
          sections that presume you already know what this is. */}
      <Route path="/join" element={
        <Suspense fallback={<RouteFallback />}><Join /></Suspense>
      } />
      <Route path="*" element={<Navigate to="/scanner" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster theme="dark" position="top-right" richColors />
        </BrowserRouter>
      </AuthProvider>
    </div>
  );
}

export default App;
