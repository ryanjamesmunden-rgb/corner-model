import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { CornerDownRight, LayoutDashboard, Radar, Flame, Zap, ClipboardCheck } from "lucide-react";
import { LeagueContext } from "@/context/LeagueContext";
import ExportMenu from "@/components/ExportMenu";
import { api } from "@/lib/api";
import { dataHealth, healthTitle, freshnessLabel } from "@/lib/freshness";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export default function Layout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [leagues, setLeagues] = useState([]);
  const [leagueId, setLeagueId] = useState(localStorage.getItem("leagueId") || "ned-ed");
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    api.leagues().then(setLeagues).catch(() => {});
    const t = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(t);
  }, []);

  const lastSynced = leagues
    .map((l) => l.synced_at)
    .filter(Boolean)
    .map((s) => new Date(s).getTime())
    .sort((a, b) => a - b)
    .slice(-1)[0];
  const freshness = freshnessLabel(lastSynced, now);
  const health = dataHealth(lastSynced ? Math.max(0, (now - lastSynced) / 3600000) : null);

  const changeLeague = (id) => {
    setLeagueId(id);
    localStorage.setItem("leagueId", id);
  };

  const nav = [
    { to: "/scanner", label: "Value Finder", icon: Radar },
    { to: "/quick-scan", label: "Quick Scan", icon: Zap },
    { to: "/picks", label: "Picks", icon: ClipboardCheck },
    { to: "/dashboard", label: "Leagues", icon: LayoutDashboard },
    { to: "/streaks", label: "Streaks", icon: Flame },
  ];

  return (
    <LeagueContext.Provider value={{ leagueId, changeLeague, leagues }}>
      <div className="min-h-screen bg-background">
        <header className="sticky top-0 z-40 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-white/10">
          <div className="max-w-[1600px] mx-auto px-4 sm:px-6 min-h-16 py-2 flex items-center gap-2 sm:gap-4 flex-wrap">
            <Link to="/scanner" className="flex items-center gap-2 shrink-0">
              <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center">
                <CornerDownRight className="h-4 w-4 text-black" strokeWidth={2.5} />
              </div>
              <div className="hidden sm:block">
                <p className="font-head font-bold text-sm leading-none tracking-tight">Corner Model</p>
                <p className="font-mono-data text-[9px] text-primary tracking-widest">v2.0</p>
              </div>
            </Link>

            <nav className="flex items-center gap-1 sm:ml-2">
              {nav.map((n) => {
                const active = location.pathname === n.to;
                return (
                  <button
                    key={n.to}
                    data-testid={`nav-${n.to.slice(1)}`}
                    onClick={() => navigate(n.to)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors duration-150 ${
                      active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                    }`}
                  >
                    <n.icon className="h-4 w-4" />
                    <span className="hidden sm:inline">{n.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="ml-auto flex items-center gap-3">
              {freshness && health && (
                <div
                  data-testid="data-freshness"
                  data-health={health.key}
                  title={healthTitle(health.key, lastSynced)}
                  className={`flex items-center gap-2 px-2.5 py-1.5 rounded-md border ${health.cls} ${
                    // A green LIVE badge is decoration and can hide on a narrow screen.
                    // A warning that the numbers are out of date is not — that is exactly
                    // when a phone user needs it, so only the healthy state stays hidden.
                    health.key === "live" ? "hidden md:flex" : ""}`}
                >
                  <span className="relative flex h-2 w-2">
                    {health.pulse && (
                      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${health.dot} opacity-60`} />
                    )}
                    <span className={`relative inline-flex rounded-full h-2 w-2 ${health.dot}`} />
                  </span>
                  <span className={`font-mono-data text-[10px] ${health.text} tracking-wide leading-none`}>
                    {health.label} · {freshness}
                  </span>
                </div>
              )}
              <Select value={leagueId} onValueChange={changeLeague}>
                <SelectTrigger data-testid="league-switcher" className="w-[130px] sm:w-[180px] bg-[#121212] border-border font-mono-data text-xs h-9">
                  <SelectValue placeholder="Select league" />
                </SelectTrigger>
                <SelectContent className="bg-[#121212] border-border">
                  {leagues.map((l) => (
                    <SelectItem key={l.league_id} value={l.league_id} data-testid={`league-opt-${l.league_id}`} className="font-mono-data text-xs">
                      {l.name} · {l.country}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <ExportMenu />
            </div>
          </div>
        </header>
        <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 fade-in">{children}</main>
      </div>
    </LeagueContext.Provider>
  );
}
