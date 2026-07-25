import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { CalendarClock, ArrowRight, Flag, RefreshCw } from "lucide-react";
import { api, confMeta, tierMeta } from "@/lib/api";
import { useLeague } from "@/context/LeagueContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import StreakFinder from "@/components/StreakFinder";

const SPLITS = [{ v: "overall", l: "Overall" }, { v: "home", l: "Home" }, { v: "away", l: "Away" }];
const WINDOWS = [{ v: "3", l: "Last 3" }, { v: "5", l: "Last 5" }, { v: "10", l: "Last 10" }];

export default function Dashboard() {
  const { leagueId, leagues } = useLeague();
  const navigate = useNavigate();
  const [fixtures, setFixtures] = useState([]);
  const [teams, setTeams] = useState([]);
  const [split, setSplit] = useState("overall");
  const [window, setWindow] = useState("5");
  const [syncing, setSyncing] = useState(false);
  const league = leagues.find((l) => l.league_id === leagueId);

  const loadData = () => {
    api.fixtures(leagueId).then(setFixtures).catch(() => setFixtures([]));
    api.teams(leagueId, split, window).then(setTeams).catch(() => setTeams([]));
  };

  useEffect(() => { api.fixtures(leagueId).then(setFixtures).catch(() => setFixtures([])); }, [leagueId]);
  useEffect(() => { api.teams(leagueId, split, window).then(setTeams).catch(() => setTeams([])); }, [leagueId, split, window]);

  const handleRefresh = async () => {
    setSyncing(true);
    try {
      await api.refresh(leagueId);
      toast.success("Live sync started — pulling latest fixtures & corner stats. Refreshing in ~90s…");
      setTimeout(() => { loadData(); setSyncing(false); toast.success(`${league?.name} data updated`); }, 90000);
    } catch {
      toast.error("Could not start sync");
      setSyncing(false);
    }
  };

  const fmtDate = (d) => new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Flag className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">{league?.country} · {league?.name}</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">League Dashboard</h1>
        </div>
        <div className="flex items-center gap-3">
          {league?.synced_at && (
            <span className="font-mono-data text-[11px] text-muted-foreground hidden sm:inline">
              Synced {new Date(league.synced_at).toLocaleDateString()} · {league.data_source === "real" ? "LIVE" : "demo"}
            </span>
          )}
          <button
            data-testid="refresh-data-btn"
            onClick={handleRefresh}
            disabled={syncing}
            className="flex items-center gap-2 bg-secondary hover:bg-white/10 border border-border text-sm font-medium rounded-md px-3 py-2 transition-colors duration-150 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing…" : "Refresh data"}
          </button>
        </div>
      </div>

      <StreakFinder leagueId={leagueId} />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Fixtures */}
        <section className="lg:col-span-2 bg-card border border-border rounded-lg">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
            <CalendarClock className="h-4 w-4 text-muted-foreground" />
            <h2 className="font-head font-semibold text-lg">Upcoming Round</h2>
            <span className="ml-auto font-mono-data text-xs text-muted-foreground">{fixtures.length} fixtures</span>
          </div>
          <div className="divide-y divide-border/50">
            {fixtures.map((fx) => {
              const t = fx.best_bet?.tier ? tierMeta[fx.best_bet.tier] : null;
              return (
                <div
                  key={fx.fixture_id}
                  data-testid="fixture-card"
                  onClick={() => navigate(`/fixture/${fx.fixture_id}`)}
                  className="px-4 py-3 hover:bg-white/5 cursor-pointer transition-colors duration-150 group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{fx.home_name} <span className="text-muted-foreground">v</span> {fx.away_name}</span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                    <span className="font-mono-data text-[11px] text-muted-foreground">{fmtDate(fx.date)}</span>
                    <span className="font-mono-data text-[11px] text-primary">λ {fx.lambdas.total.toFixed(1)}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${confMeta[fx.confidence.label]}`}>{fx.confidence.label}</span>
                    {t && fx.best_bet?.ev != null && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${t.chip} font-mono-data`}>
                        {fx.best_bet.group_label} {fx.best_bet.label} · {fx.best_bet.ev > 0 ? "+" : ""}{fx.best_bet.ev.toFixed(1)}%
                      </span>
                    )}
                    {!fx.has_odds && <span className="text-[10px] text-muted-foreground italic">no odds yet</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Form table */}
        <section className="lg:col-span-3 bg-card border border-border rounded-lg">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 border-b border-border">
            <h2 className="font-head font-semibold text-lg">Team Corner Form</h2>
            <div className="sm:ml-auto flex gap-2">
              <Tabs value={split} onValueChange={setSplit}>
                <TabsList className="bg-secondary h-8">
                  {SPLITS.map((s) => <TabsTrigger key={s.v} value={s.v} data-testid={`split-${s.v}`} className="text-xs px-2.5 h-6">{s.l}</TabsTrigger>)}
                </TabsList>
              </Tabs>
              <Tabs value={window} onValueChange={setWindow}>
                <TabsList className="bg-secondary h-8">
                  {WINDOWS.map((w) => <TabsTrigger key={w.v} value={w.v} data-testid={`window-${w.v}`} className="text-xs px-2.5 h-6">{w.l}</TabsTrigger>)}
                </TabsList>
              </Tabs>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
                  <th className="text-left font-medium px-4 py-2.5">#</th>
                  <th className="text-left font-medium px-4 py-2.5">Team</th>
                  <th className="text-right font-medium px-4 py-2.5">Won</th>
                  <th className="text-right font-medium px-4 py-2.5">Conceded</th>
                  <th className="text-right font-medium px-4 py-2.5">Total /g</th>
                  <th className="text-right font-medium px-4 py-2.5">Season</th>
                </tr>
              </thead>
              <tbody className="font-mono-data text-sm">
                {teams.map((t, i) => (
                  <tr key={t.team_id} data-testid="team-row" className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
                    <td className="px-4 py-2.5 text-muted-foreground">{i + 1}</td>
                    <td className="px-4 py-2.5 text-foreground font-sans font-medium whitespace-nowrap">{t.name}</td>
                    <td className="px-4 py-2.5 text-right text-emerald-400">{t.for_avg.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right text-red-400">{t.against_avg.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right text-foreground font-semibold">{t.total_avg.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{t.season_total_avg.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
