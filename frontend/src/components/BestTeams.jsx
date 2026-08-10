import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trophy, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SIDES = [{ v: "overall", l: "Overall" }, { v: "home", l: "Home" }, { v: "away", l: "Away" }];
const WINDOWS = [{ v: "0", l: "Season" }, { v: "5", l: "Last 5" }, { v: "10", l: "Last 10" }];

const fmt = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });

// Best corner-winning teams across leagues, ranked by average corners won.
export default function BestTeams({ leagueId }) {
  const navigate = useNavigate();
  const [scope, setScope] = useState("all");
  const [side, setSide] = useState("overall");
  const [win, setWin] = useState("0");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.topCornerTeams({ league_id: scope === "current" ? leagueId : "all", side, window: win, limit: 40 })
      .then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [scope, side, win, leagueId]);

  const max = rows.length ? rows[0].won_avg : 1;

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="best-teams">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Best Corner Teams</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">highest average corners won (real games)</span>
        </div>
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Tabs value={side} onValueChange={setSide}>
            <TabsList className="bg-secondary h-8">
              {SIDES.map((s) => <TabsTrigger key={s.v} value={s.v} data-testid={`best-side-${s.v}`} className="text-xs px-2.5 h-6">{s.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Tabs value={win} onValueChange={setWin}>
            <TabsList className="bg-secondary h-8">
              {WINDOWS.map((w) => <TabsTrigger key={w.v} value={w.v} data-testid={`best-win-${w.v}`} className="text-xs px-2.5 h-6">{w.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Select value={scope} onValueChange={setScope}>
            <SelectTrigger data-testid="best-scope" className="w-[130px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              <SelectItem value="all" className="text-xs">All Leagues</SelectItem>
              <SelectItem value="current" className="text-xs">This League</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-4 py-2.5">#</th>
              <th className="text-left font-medium px-4 py-2.5">Team</th>
              <th className="text-right font-medium px-4 py-2.5">Won/g</th>
              <th className="text-left font-medium px-4 py-2.5 hidden md:table-cell w-[180px]">&nbsp;</th>
              <th className="text-right font-medium px-4 py-2.5">Conc/g</th>
              <th className="text-right font-medium px-4 py-2.5">Total/g</th>
              <th className="text-right font-medium px-4 py-2.5">Games</th>
              <th className="text-left font-medium px-4 py-2.5">Next</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={9} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Ranking corner teams…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-12 text-center text-muted-foreground">No teams with enough games on this filter.</td></tr>
            ) : rows.map((r, i) => (
              <tr
                key={r.team_id}
                data-testid="best-team-row"
                onClick={() => r.next_fixture && navigate(`/fixture/${r.next_fixture.fixture_id}`)}
                className={`border-b border-border/50 transition-colors duration-150 ${r.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`}
                style={{ borderLeft: i < 3 ? "2px solid #22D3EE" : "2px solid transparent" }}
              >
                <td className="px-4 py-2.5 text-muted-foreground">{i + 1}</td>
                <td className="px-4 py-2.5">
                  <div className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{r.league_name}</div>
                </td>
                <td className="px-4 py-2.5 text-right text-emerald-400 font-semibold">{r.won_avg.toFixed(2)}</td>
                <td className="px-4 py-2.5 hidden md:table-cell">
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.min(100, (r.won_avg / max) * 100)}%` }} />
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right text-red-400">{r.conceded_avg.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-right text-foreground">{r.total_avg.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-right text-muted-foreground">{r.games}</td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {r.next_fixture ? `${r.next_fixture.is_home ? "vs" : "@"} ${r.next_fixture.opponent} · ${fmt(r.next_fixture.date)}` : "—"}
                </td>
                <td className="px-4 py-2.5 text-right">{r.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
