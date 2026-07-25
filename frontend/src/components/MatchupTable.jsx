import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Trophy, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const SIDES = [{ v: "overall", l: "Overall" }, { v: "home", l: "Home" }, { v: "away", l: "Away" }];

const tierStyle = {
  strong: { row: "#10B981", chip: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", label: "Mismatch" },
  decent: { row: "#F59E0B", chip: "bg-amber-500/15 text-amber-400 border-amber-500/30", label: "Lean" },
  none: { row: "transparent", chip: "", label: "" },
};

// Top corner-winning teams in a league + their next fixture, green when it's a corner mismatch.
export default function MatchupTable({ leagueId }) {
  const navigate = useNavigate();
  const [side, setSide] = useState("overall");
  const [data, setData] = useState({ teams: [], league_avg_won: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.matchups(leagueId, side).then(setData).catch(() => setData({ teams: [], league_avg_won: 0 })).finally(() => setLoading(false));
  }, [leagueId, side]);

  const fmt = (d) => new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const sideLabel = side === "overall" ? "corners won /g" : `${side} corners /g`;

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="matchup-table">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Trophy className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Top Corner Teams &amp; Next Matchup</h2>
        </div>
        <div className="sm:ml-auto flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground hidden md:inline">green = strong team vs leaky defence</span>
          <Tabs value={side} onValueChange={setSide}>
            <TabsList className="bg-secondary h-8">
              {SIDES.map((s) => <TabsTrigger key={s.v} value={s.v} data-testid={`matchup-side-${s.v}`} className="text-xs px-2.5 h-6">{s.l}</TabsTrigger>)}
            </TabsList>
          </Tabs>
        </div>
      </div>
      <div className="overflow-x-auto max-h-[440px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-4 py-2.5">#</th>
              <th className="text-left font-medium px-4 py-2.5">Team</th>
              <th className="text-right font-medium px-4 py-2.5">{sideLabel}</th>
              <th className="text-left font-medium px-4 py-2.5">Next fixture</th>
              <th className="text-right font-medium px-4 py-2.5">Opp concedes</th>
              <th className="text-right font-medium px-4 py-2.5">Proj λ</th>
              <th className="text-right font-medium px-4 py-2.5">Model ({"\u2265"}line)</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground animate-pulse">Loading matchups…</td></tr>
            ) : data.teams.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">No data for this league yet.</td></tr>
            ) : data.teams.map((t, i) => {
              const st = tierStyle[t.tier];
              const p = t.projection;
              return (
                <tr
                  key={t.team_id}
                  data-testid="matchup-row"
                  onClick={() => p && t.next_fixture && navigate(`/fixture/${t.next_fixture.fixture_id}`)}
                  className={`border-b border-border/50 transition-colors duration-150 ${t.next_fixture ? "hover:bg-white/5 cursor-pointer" : ""}`}
                  style={{ borderLeft: `2px solid ${st.row}`, background: t.tier === "strong" ? "rgba(16,185,129,0.06)" : undefined }}
                >
                  <td className="px-4 py-2.5 text-muted-foreground">{i + 1}</td>
                  <td className="px-4 py-2.5">
                    <span className="text-foreground font-sans font-medium whitespace-nowrap">{t.name}</span>
                    {t.real_samples < 5 && <span className="ml-2 text-[9px] text-amber-400/70">est</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right text-emerald-400 font-semibold">{t.side_for.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    {t.next_fixture ? `${t.next_fixture.is_home ? "vs" : "@"} ${t.next_fixture.opponent} · ${fmt(t.next_fixture.date)}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {p ? <span className={p.opp_conceded >= data.league_avg_won * 1.1 ? "text-emerald-400" : "text-muted-foreground"}>{p.opp_conceded.toFixed(1)}</span> : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right text-primary font-semibold">{p ? p.lambda.toFixed(1) : "—"}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {p ? <span className="text-foreground" title={`${p.prob.toFixed(0)}% to win ${p.line}+ corners`}>{p.line}+ @ {p.fair_odds?.toFixed(2)}</span> : <span className="text-muted-foreground">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {t.tier !== "none" && <span className={`text-[10px] px-2 py-0.5 rounded border ${st.chip} mr-2`}>{st.label}</span>}
                    {t.next_fixture && <ArrowRight className="h-4 w-4 text-muted-foreground inline" />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
