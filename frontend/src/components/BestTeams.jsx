import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trophy, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import ShareButtons from "@/components/ShareButtons";
import { withFlag } from "@/lib/countryFlag";
import { bestTeamsShare } from "@/lib/shareText";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Kept in step with the precomputed "top_teams" screen in server.py — a different
// value here would miss that cache and scan every team on each visit.
const TOP_TEAMS_LIMIT = 60;
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
    api.topCornerTeams({ league_id: scope === "current" ? leagueId : "all", side, window: win, limit: TOP_TEAMS_LIMIT })
      .then(setRows).catch(() => setRows([])).finally(() => setLoading(false));
  }, [scope, side, win, leagueId]);

  const max = rows.length ? rows[0].won_avg : 1;

  // Shared with the scheduled post — see lib/shareText.
  const SHARE_ROWS = 8;
  const buildShare = bestTeamsShare({ rows, side, windowLabel: WINDOWS.find((w) => w.v === win)?.l || "" });

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="best-teams">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Best Corner Teams</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">highest average corners won (real games)</span>
          {rows.length > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground">{rows.length} shown</span>
          )}
        </div>
        {rows.length > 0 && <ShareButtons text={buildShare(SHARE_ROWS)} buildX={buildShare} />}
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

      {/* Tall enough to screenshot a long run of the table in one go; the header row
          stays stuck so a scrolled-down capture still shows what the columns are. */}
      <div className="overflow-x-auto max-h-[80vh] min-h-[520px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">#</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Team</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Won/g</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5 hidden md:table-cell w-[180px]">&nbsp;</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Conc/g</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Total/g</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Shots taken per game, over the fixtures the provider covered">Shots F</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Shots faced per game — a team winning corners against a side that concedes shots freely is a softer signal">Shots A</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Shots on target per game. Reported for only about half of fixtures, so this is a thinner sample than Shots — hover a value for its count.">SoT F</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Shots on target faced per game. Same reduced coverage as SoT F.">SoT A</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Games</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Next</th>
              <th className="px-2 py-1.5 sm:px-4 sm:py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={13} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Ranking corner teams…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={13} className="px-4 py-12 text-center text-muted-foreground">No teams with enough games on this filter.</td></tr>
            ) : rows.map((r, i) => (
              <tr
                key={r.team_id}
                data-testid="best-team-row"
                onClick={() => r.next_fixture && navigate(`/fixture/${r.next_fixture.fixture_id}`)}
                className={`border-b border-border/50 transition-colors duration-150 ${r.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`}
                style={{ borderLeft: i < 3 ? "2px solid #22D3EE" : "2px solid transparent" }}
              >
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-muted-foreground">{i + 1}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5">
                  <div className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider font-sans">{withFlag(r.league_id, r.league_name)}</div>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-emerald-400 font-semibold">{r.won_avg.toFixed(2)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 hidden md:table-cell">
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.min(100, (r.won_avg / max) * 100)}%` }} />
                  </div>
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-red-400">{r.conceded_avg.toFixed(2)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground">{r.total_avg.toFixed(2)}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground"
                  title={r.shots_games ? `from ${r.shots_games} covered game${r.shots_games === 1 ? "" : "s"}` : undefined}>
                  {r.shots_for_avg != null ? r.shots_for_avg.toFixed(1)
                    : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-muted-foreground">
                  {r.shots_against_avg != null ? r.shots_against_avg.toFixed(1) : "—"}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground"
                  title={r.sot_games ? `from ${r.sot_games} covered game${r.sot_games === 1 ? "" : "s"}`
                                     : "not reported for any of this team's fixtures"}>
                  {r.sot_for_avg != null ? r.sot_for_avg.toFixed(1)
                    : <span className="text-muted-foreground">—</span>}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-muted-foreground">
                  {r.sot_against_avg != null ? r.sot_against_avg.toFixed(1) : "—"}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-muted-foreground">{r.games}</td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                  {r.next_fixture ? `${r.next_fixture.is_home ? "vs" : "@"} ${r.next_fixture.opponent} · ${fmt(r.next_fixture.date)}` : "—"}
                </td>
                <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">{r.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
