import { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import MobileNav from "@/components/MobileNav";
import { CornerDownRight, LayoutDashboard, Radar, Flame, Zap, Star, Sparkles, Receipt, Trophy,
         TrendingUp, ClipboardPaste } from "lucide-react";
import { LeagueContext } from "@/context/LeagueContext";
import ExportMenu from "@/components/ExportMenu";
import { api } from "@/lib/api";
import SignIn from "@/components/SignIn";
import SiteFooter from "@/components/SiteFooter";
import { useAuth } from "@/context/AuthContext";
import { dataHealth, healthTitle, freshnessLabel } from "@/lib/freshness";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export default function Layout({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  // Whether to show the join CTA. `ready` matters: until the session has resolved,
  // everyone looks signed out, and flashing "Join" at an existing member for half a
  // second is a worse first impression than showing it a beat late.
  const { user, member, ready: authReady } = useAuth();
  const [leagues, setLeagues] = useState([]);
  const [leagueId, setLeagueId] = useState(localStorage.getItem("leagueId") || "ned-ed");
  const [now, setNow] = useState(Date.now());
  const [moreOpen, setMoreOpen] = useState(false);

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
    { to: "/dashboard", label: "Leagues", icon: LayoutDashboard },
    { to: "/streaks", label: "Streaks", icon: Flame },
    // ACCOUNT HOLDERS ONLY, link and all. It is the model's projection for games that
    // have not been played, which is the product rather than an advert for it — and a nav
    // item that always leads to a wall teaches people the nav is lying.
    ...(user ? [{ to: "/projections", label: "Projected", icon: TrendingUp }] : []),
    { to: "/saved", label: "Saved", icon: Star },
    { to: "/bets", label: "Bets", icon: Receipt },
    // WAS the one page shown to signed-out visitors, on the reasoning that it argues for
    // all the others and cannot do that from behind a login. That reasoning still holds;
    // the trade was made anyway, because the record is a list of the picks this site made
    // and the picks are the product. Signing in is free, so the ask is small.
    ...(user ? [{ to: "/results", label: "Results", icon: Trophy }] : []),
    // MEMBERS ONLY, and not because the page is precious — because it WRITES. Every other
    // entry here reads. Putting a data-entry page in front of every visitor invites
    // strangers to type prices into the board the site's own posts are chosen from.
    ...(member ? [{ to: "/prices", label: "Prices", icon: ClipboardPaste }] : []),
  ];

  // WHICH SCREENS THE LEAGUE ACTUALLY FILTERS. It drove four of them and sat on all
  // eleven, in the widest slot of the header, where on a phone it truncated to
  // "Premier Le…" and pushed everything else together. It is a page filter, so it now
  // renders with the page — in one strip under the header rather than inside each of the
  // four, which keeps it a single definition and leaves those pages untouched.
  const LEAGUE_ROUTES = ["/scanner", "/dashboard", "/streaks"];
  const showLeague = LEAGUE_ROUTES.includes(location.pathname)
    || location.pathname.startsWith("/fixture/");

  return (
    <LeagueContext.Provider value={{ leagueId, changeLeague, leagues }}>
      <div className="min-h-screen bg-background">
        <header className="sticky top-0 z-40 bg-[#0a0a0a]/80 backdrop-blur-xl border-b border-white/10">
          <div className="max-w-[1600px] mx-auto px-3 sm:px-6 min-h-12 sm:min-h-16 py-1.5 sm:py-2 flex items-center gap-1.5 sm:gap-4 flex-wrap">
            {/* SHOWN ON THE PHONE NOW, because the nav no longer is: without it the
                header opened on an anonymous row of controls with nothing saying where
                you were. */}
            <Link to="/scanner" className="flex items-center gap-2 shrink-0">
              <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center">
                <CornerDownRight className="h-4 w-4 text-black" strokeWidth={2.5} />
              </div>
              <div className="hidden sm:block">
                <p className="font-head font-bold text-sm leading-none tracking-tight">Corner Model</p>
                <p className="font-mono-data text-[9px] text-primary tracking-widest">v2.0</p>
              </div>
            </Link>

            {/* THE NAV LEAVES THE HEADER ON A PHONE. It moves to a bottom bar, where a
                thumb reaches it and a label fits beside the icon — see MobileNav. */}
            <nav className="hidden sm:flex items-center gap-0.5 sm:gap-1 sm:ml-2">
              {nav.map((n) => {
                const active = location.pathname === n.to;
                return (
                  <button
                    key={n.to}
                    data-testid={`nav-${n.to.slice(1)}`}
                    onClick={() => navigate(n.to)}
                    className={`flex items-center gap-2 px-2 sm:px-3 py-1.5 sm:py-2 rounded-md text-sm font-medium transition-colors duration-150 ${
                      active ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                    }`}
                  >
                    <n.icon className="h-4 w-4" />
                    <span className="hidden sm:inline">{n.label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="ml-auto flex items-center gap-1.5 sm:gap-3">
              {/* THE ONLY WAY INTO /join from inside the app. It had no link at all —
                  the page existed and could be reached by typing the URL or by hitting a
                  members-only screen, which meant every signup had to be hand-delivered.
                  Shown to anyone who is not a member, on every screen, including mobile
                  where the label is what makes it worth the space. */}
              {authReady && !member && location.pathname !== "/join" && (
                <button
                  onClick={() => navigate("/join")}
                  data-testid="nav-join"
                  className="flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-md
                             bg-primary text-black font-semibold text-xs sm:text-sm
                             hover:opacity-90 transition-opacity shrink-0"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Join
                </button>
              )}
              <SignIn />
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
              <div className="hidden sm:block">
                <ExportMenu />
              </div>
            </div>
          </div>

          {/* THE LEAGUE, WITH THE PAGE IT FILTERS. A full-width 44px control on a phone
              instead of a 104px chip reading "Premier Le…", and only on the screens it
              changes anything on — on the other seven it was furniture. */}
          {showLeague && (
            <div className="border-t border-white/5 bg-[#0a0a0a]/60">
              <div className="max-w-[1600px] mx-auto px-3 sm:px-6 py-2">
                <Select value={leagueId} onValueChange={changeLeague}>
                  <SelectTrigger data-testid="league-switcher"
                    className="w-full sm:w-[220px] bg-[#121212] border-border font-mono-data
                               text-xs h-11 sm:h-9">
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
              </div>
            </div>
          )}
        </header>

        {/* Bottom padding clears the tab bar. Without it the last row of every board sits
            underneath it, which reads as the page having been cut off. */}
        <main className="max-w-[1600px] mx-auto px-3 sm:px-6 py-3 sm:py-6 pb-24 sm:pb-6 fade-in">
          {children}
        </main>

        {/* THE FRESHNESS BADGE, ON A PHONE, IN THE FOOTER. In the header it was competing
            with navigation for the narrowest row on the site to say something nobody
            needs on a healthy day — and it already hid itself when green. Down here it is
            readable when someone goes looking, and the header still shows it at any width
            when the data has actually gone stale. */}
        {freshness && health && health.key === "live" && (
          <div className="sm:hidden max-w-[1600px] mx-auto px-3 pt-4 flex items-center gap-2"
            data-testid="data-freshness-footer">
            <span className={`relative inline-flex rounded-full h-2 w-2 ${health.dot}`} />
            <span className={`font-mono-data text-[10px] ${health.text} tracking-wide`}>
              {health.label} · {freshness}
            </span>
          </div>
        )}
        <SiteFooter className="mb-20 sm:mb-0" />
        {/* Export goes in the sheet rather than the header: it is a thing you do once in
            a while, and it was taking permanent space beside the things you do daily. */}
        <MobileNav nav={nav} open={moreOpen} setOpen={setMoreOpen} extra={<ExportMenu />} />
      </div>
    </LeagueContext.Provider>
  );
}
