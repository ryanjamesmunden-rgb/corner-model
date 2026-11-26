import "@/App.css";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Suspense } from "react";
import { lazyRoute } from "@/lib/lazyRoute";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "@/components/Layout";
import { AuthProvider } from "@/context/AuthContext";
import { Analytics } from "@vercel/analytics/react";

// Each route is its own chunk: landing on the Scanner shouldn't download and parse
// Streaks and the fixture detail page before it can paint.
//
// lazyRoute, not React's lazy: a tab left open across a deploy asks for chunk names that
// no longer exist, gets the SPA's index.html back as a 404 body, and throws trying to
// parse HTML as JavaScript. That looks like the whole site being down when it is working
// for everyone who arrives fresh. lazyRoute reloads once, which is the entire fix.
const Browse = lazyRoute(() => import("@/pages/Browse"));
const Evidence = lazyRoute(() => import("@/pages/Evidence"));
const Dashboard = lazyRoute(() => import("@/pages/Dashboard"));
const Scanner = lazyRoute(() => import("@/pages/Scanner"));
const Streaks = lazyRoute(() => import("@/pages/Streaks"));
const QuickScan = lazyRoute(() => import("@/pages/QuickScan"));
const Combined = lazyRoute(() => import("@/pages/Combined"));
const FixtureDetail = lazyRoute(() => import("@/pages/FixtureDetail"));
const Join = lazyRoute(() => import("@/pages/Join"));
const Account = lazyRoute(() => import("@/pages/Account"));
const FaqPage = lazyRoute(() => import("@/pages/FaqPage"));
const Saved = lazyRoute(() => import("@/pages/Saved"));
const FormGraph = lazyRoute(() => import("@/pages/FormGraph"));
const MyTeams = lazyRoute(() => import("@/pages/MyTeams"));
const Calendar = lazyRoute(() => import("@/pages/Calendar"));
const WeekCardPage = lazyRoute(() => import("@/pages/WeekCard"));
const ReviewPage = lazyRoute(() => import("@/pages/Review"));
const Bets = lazyRoute(() => import("@/pages/Bets"));
const Results = lazyRoute(() => import("@/pages/Results"));
const Projections = lazyRoute(() => import("@/pages/Projections"));

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
    // OUTERMOST CATCH. Anything that throws below this shows a panel instead of
    // unmounting the app — see components/ErrorBoundary. Individual boards wrap
    // themselves too, so a broken board loses its own panel rather than its page.
    <ErrorBoundary label="This page">
    <Routes>
      {/* THE LANDING PAGE. It was /scanner, which answers "what should I bet" — a good
          question, and not the one somebody arriving has. The index comes first now and
          Value Finder keeps its own page. */}
      <Route path="/" element={page(Browse)} />
      <Route path="/dashboard" element={page(Dashboard)} />
      <Route path="/scanner" element={page(Scanner)} />
      <Route path="/quick-scan" element={page(QuickScan)} />
      <Route path="/combined" element={page(Combined)} />
      <Route path="/streaks" element={page(Streaks)} />
      <Route path="/saved" element={page(Saved)} />
      <Route path="/form" element={page(FormGraph)} />
      <Route path="/my-teams" element={page(MyTeams)} />
      <Route path="/calendar" element={page(Calendar)} />
      {/* The month grid next door answers "when do my teams play". This is the
          other half of the same question: given a day, what is on and what is
          the bet. Separate routes because they are different time scales and
          one page doing both fights for the same screen. */}
      <Route path="/week-card" element={page(WeekCardPage)} />
      {/* Played games keep their prices. The boards drop a fixture at kick-off;
          this is where it goes instead. */}
      <Route path="/review" element={page(ReviewPage)} />
      <Route path="/bets" element={page(Bets)} />
      <Route path="/results" element={page(Results)} />
      {/* PUBLIC. It lists no pick and names no team — it is the model's own
          percentages checked against what happened, which is the one thing worth
          showing somebody who has not signed up for anything yet. */}
      <Route path="/evidence" element={page(Evidence)} />
      <Route path="/fixture/:id" element={page(FixtureDetail)} />
      <Route path="/projections" element={page(Projections)} />
      <Route path="/account" element={page(Account)} />
      {/* Deliberately OUTSIDE page(): the subscription page is for people who are not
          members yet, so it carries no app chrome — no league switcher, no nav to
          sections that presume you already know what this is. */}
      <Route path="/join" element={
        <Suspense fallback={<RouteFallback />}><Join /></Suspense>
      } />
      {/* Outside page() for the same reason as /join: whoever is reading this may not
          have paid yet, and app chrome above "how do I cancel" is noise. */}
      <Route path="/faq" element={
        <Suspense fallback={<RouteFallback />}><FaqPage /></Suspense>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </ErrorBoundary>
  );
}

function App() {
  // NOTHING CLEARS lazyRoute's GUARD, and the first version of this clearing it here is
  // why: App mounts BEFORE a lazy route resolves, so every reload wiped the guard on the
  // way past and the next failure found it unset — 328 page loads in 20 seconds against
  // a chunk that never came back. The guard is a timestamp now and expires on its own.
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster theme="dark" position="top-right" richColors />
        </BrowserRouter>
      </AuthProvider>
      <Analytics />
    </div>
  );
}

export default App;
