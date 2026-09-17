import { useState, useEffect, Fragment } from "react";
import { useNavigate } from "react-router-dom";
import { TrendingUp, ArrowRight, ArrowUpRight, ChevronRight } from "lucide-react";
import { api } from "@/lib/api";
import PreviewWall from "@/components/PreviewWall";
import { lockClass, lockCounts } from "@/lib/locked";
import TeamStar from "@/components/TeamStar";
import { withFlag } from "@/lib/countryFlag";
import { useLeague } from "@/context/LeagueContext";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const SIDES = [{ v: "overall", l: "Overall" }, { v: "home", l: "Home" }, { v: "away", l: "Away" }];
const WINDOWS = [{ v: "3", l: "Last 3" }, { v: "5", l: "Last 5" }, { v: "10", l: "Last 10" }];
const METRICS = [{ v: "total", l: "Total corners" }, { v: "won", l: "Corners won" }];

// Teams averaging MORE corners lately than their season baseline (hot form).
export default function TrendFinder() {
  const { leagueId, leagues } = useLeague();
  const navigate = useNavigate();
  const [scope, setScope] = useState("all");
  const [side, setSide] = useState("overall");
  const [win, setWin] = useState("5");
  const [metric, setMetric] = useState("total");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  // Set by the API when the server trimmed this board for a non-member.
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.trends({ league_id: scope === "current" ? leagueId : "all", window: win, metric, side })
      .then((d) => { setRows(d); setPreview(d?.preview ? { total: d.total } : null); })
      .catch(() => { setRows([]); setPreview(null); })
      .finally(() => setLoading(false));
  }, [scope, leagueId, win, metric, side]);

  // Which rows have their games opened out. Keyed by team so a filter change that keeps a
  // team on the board keeps it open.
  const [open, setOpen] = useState({});
  const toggle = (id) => (e) => { e.stopPropagation(); setOpen((o) => ({ ...o, [id]: !o[id] })); };

  const fmt = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const recKey = metric === "total" ? "recent_total" : "recent_won";
  const seaKey = metric === "total" ? "season_total" : "season_won";
  // The number each game contributed to the recent average, on the metric being shown.
  const gameValue = (m) => (metric === "total" ? m.corners_for + m.corners_against : m.corners_for);
  const score = (m) => (m.goals_for != null && m.goals_against != null
    ? `${m.goals_for > m.goals_against ? "W" : m.goals_for < m.goals_against ? "L" : "D"} ${m.goals_for}-${m.goals_against}`
    : null);

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="trend-finder">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Hot Form</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">teams averaging more corners than usual</span>
        </div>
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Tabs value={side} onValueChange={setSide}>
            <TabsList className="bg-secondary h-8">
              {SIDES.map((s) => <TabsTrigger key={s.v} value={s.v} data-testid={`trend-side-${s.v}`} className="text-xs px-2.5 h-6">{s.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Tabs value={win} onValueChange={setWin}>
            <TabsList className="bg-secondary h-8">
              {WINDOWS.map((w) => <TabsTrigger key={w.v} value={w.v} data-testid={`trend-win-${w.v}`} className="text-xs px-2.5 h-6">{w.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger data-testid="trend-metric" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {METRICS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={scope} onValueChange={setScope}>
            <SelectTrigger data-testid="trend-scope" className="w-[130px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              <SelectItem value="all" className="text-xs">All Leagues</SelectItem>
              <SelectItem value="current" className="text-xs">{leagues.find((l) => l.league_id === leagueId)?.name || "This League"}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="overflow-x-auto sm:max-h-[520px] sm:overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="w-8 pl-2 sm:pl-3"><span className="sr-only">Show games</span></th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Team</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Recent avg</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Season avg</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Trend</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Each recent game's corners, newest first. Green beat the season average.">Games</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Next</th>
              <th className="px-2 py-1.5 sm:px-4 sm:py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Scanning form trends…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">No teams trending up on this filter.</td></tr>
            ) : rows.map((r) => (
              <Fragment key={r.team_id}>
              <tr
                data-testid="trend-row"
                onClick={() => r.next_fixture && navigate(`/fixture/${r.next_fixture.fixture_id}`)}
                className={lockClass(r, `border-b border-border/50 transition-colors duration-150 ${r.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`)}
                style={{ borderLeft: "2px solid #22D3EE" }}
              >
                {/* ITS OWN COLUMN, first in the row. Tucked after the corner chips it read as
                    decoration; at the row's start it reads as what it is — open this up. */}
                <td className="w-8 pl-2 sm:pl-3 py-1.5 sm:py-2.5">
                  {(r.recent || []).length > 0 && (
                    <button onClick={toggle(r.team_id)} data-testid="trend-games-toggle"
                      aria-expanded={!!open[r.team_id]}
                      aria-label={open[r.team_id] ? `Hide ${r.name}'s games` : `Show ${r.name}'s games`}
                      className="flex h-6 w-6 items-center justify-center rounded border border-border bg-secondary text-muted-foreground hover:text-foreground hover:border-primary/60 transition-colors">
                      <ChevronRight className={`h-4 w-4 transition-transform duration-150 ${open[r.team_id] ? "rotate-90" : ""}`} />
                    </button>
                  )}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</span>
                    <TeamStar teamId={r.team_id} teamName={r.name} />
                  </div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{withFlag(r.league_id, r.league_name)}</div>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground font-semibold">{r[recKey].toFixed(2)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-muted-foreground">{r[seaKey].toFixed(2)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">
                  <span className="inline-flex items-center gap-1 text-emerald-400 font-semibold">
                    <ArrowUpRight className="h-3.5 w-3.5" />+{r.delta.toFixed(2)}
                  </span>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5">
                  {(r.recent || []).length > 0 ? (
                    <div className="flex items-center gap-1">
                      {r.recent.map((m, i) => (
                        <span key={i}
                          title={`${gameValue(m)} corners ${m.home ? "vs" : "@"} ${m.opponent || "?"}${score(m) ? ` (${score(m)})` : ""}`}
                          className={`inline-flex h-5 min-w-5 px-1 items-center justify-center rounded text-[10px] ${
                            gameValue(m) > r[seaKey] ? "bg-emerald-500/20 text-emerald-400" : "bg-white/5 text-muted-foreground"}`}>
                          {gameValue(m)}
                        </span>
                      ))}
                    </div>
                  ) : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {r.next_fixture ? `${r.next_fixture.is_home ? "vs" : "@"} ${r.next_fixture.opponent} · ${fmt(r.next_fixture.date)}` : "—"}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">{r.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}</td>
              </tr>
              {/* THE GAMES BEHIND THE AVERAGE. Opponent and scoreline are what separate a
                  team that has changed from one that just met three leaky defences. */}
              {open[r.team_id] && (
                <tr className="border-b border-border/50 bg-white/[0.02]" data-testid="trend-games">
                  <td colSpan={8} className="px-2 py-2 sm:px-4">
                    <div className="grid gap-1 text-xs">
                      {r.recent.map((m, i) => (
                        <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                          <span className="w-14 text-muted-foreground">{m.date ? fmt(m.date) : "—"}</span>
                          <span className="font-sans text-foreground min-w-[10rem]">
                            {m.home ? "vs" : "@"} {m.opponent || "Unknown"}
                          </span>
                          <span className="w-14 text-muted-foreground">{score(m) || "—"}</span>
                          <span className={gameValue(m) > r[seaKey] ? "text-emerald-400 font-semibold" : "text-muted-foreground"}>
                            {m.corners_for}–{m.corners_against} corners
                            {metric === "total" && ` (${m.corners_for + m.corners_against})`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {preview && <PreviewWall total={preview.total} shown={rows.length}
        locked={lockCounts(rows).locked} noun="teams" />}
    </section>
  );
}
