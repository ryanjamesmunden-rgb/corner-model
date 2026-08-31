import { useState, useEffect } from "react";
import { Flag } from "lucide-react";
import { api } from "@/lib/api";
import { useLeague } from "@/context/LeagueContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import MatchupTable from "@/components/MatchupTable";
import CornerLeagueTable from "@/components/CornerLeagueTable";
import SyncPanel from "@/components/SyncPanel";
import BacktestPanel from "@/components/BacktestPanel";
import ToolsPanel from "@/components/ToolsPanel";

const SPLITS = [{ v: "overall", l: "Overall" }, { v: "home", l: "Home" }, { v: "away", l: "Away" }];
const WINDOWS = [{ v: "3", l: "Last 3" }, { v: "5", l: "Last 5" }, { v: "10", l: "Last 10" }];

export default function Dashboard() {
  const { leagueId, leagues } = useLeague();
  const [teams, setTeams] = useState([]);
  const [split, setSplit] = useState("overall");
  const [window, setWindow] = useState("5");
  const league = leagues.find((l) => l.league_id === leagueId);

  useEffect(() => {
    api.teams(leagueId, split, window).then(setTeams).catch(() => setTeams([]));
  }, [leagueId, split, window]);

  return (
    <div className="space-y-3 sm:space-y-6" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <Flag className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">{league?.country} · {league?.name}</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Leagues</h1>
        </div>
        <div className="flex items-center gap-3">
          {/* No manual refresh here on purpose. Syncing spends API credits and this
              app is public, so both refresh endpoints now require TOOLS_TOKEN. The
              sync runs on a schedule instead — .github/workflows/sync.yml, every 12
              hours — which is also what fixed it silently not running at all. */}
          {league?.synced_at && (
            <span className="font-mono-data text-[11px] text-muted-foreground hidden sm:inline">
              Synced {new Date(league.synced_at).toLocaleDateString()} · {league.data_source === "real" ? "LIVE" : "demo"}
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6 items-start">
        <div className="space-y-6 min-w-0">
          <MatchupTable leagueId={leagueId} />

          <section className="bg-card border border-border rounded-lg">
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

        <CornerLeagueTable leagueId={leagueId} />
      </div>

      <SyncPanel />
      <BacktestPanel leagueId={leagueId} />

      <ToolsPanel />
    </div>
  );
}
