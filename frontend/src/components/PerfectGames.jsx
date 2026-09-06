import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Crosshair, ArrowRight, Info } from "lucide-react";
import { api } from "@/lib/api";
import { withFlag } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";
import { tightestWin } from "@/lib/cushion";
import TeamStar from "@/components/TeamStar";
import TierBadge from "@/components/TierBadge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Where the RUN and the MATCHUP point at the same game.
//
// The two screens next door answer different questions and were never put side by side.
// Streaks ask what a team keeps doing; mismatches ask who they have drawn. Either alone
// is a lead. A team on both lists for the same fixture has a habit and a favourable
// opponent at once, and that is the shortlist this screen is.
//
// IT SAYS WHAT IT IS NOT, prominently, because the failure mode here is a punter reading
// "perfect" as "certain" and staking accordingly. The two signals share an input — how
// many corners this team wins drives both — so their agreement is not two independent
// models concurring. The half that is genuinely new is the opponent's concession rate,
// measured on the opponent's own games. The note under the table says exactly that, and
// the screen is named for the shortlist rather than for a verdict.

const WINDOWS = [
  { v: "3", l: "Next 3 days" },
  { v: "7", l: "Next 7 days" },
  { v: "14", l: "Next 14 days" },
];
// Looser first: 4/5 finds more pairings, 5/5 demands a clean run.
const RUNS = [
  { v: "4", l: "4 of last 5" },
  { v: "5", l: "5 of last 5" },
];

export default function PerfectGames() {
  const navigate = useNavigate();
  const [days, setDays] = useState("7");
  const [minHits, setMinHits] = useState("4");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.perfectGames({ within_days: Number(days), min_hits: Number(minHits), limit: 30 })
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [days, minHits]);

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="perfect-games">
      <div className="flex flex-col lg:flex-row lg:items-center gap-3 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Crosshair className="h-4 w-4 text-primary" />
          <h2 className="font-head font-semibold text-lg">Perfect Games</h2>
          <span className="text-xs text-muted-foreground hidden sm:inline">
            a run and a favourable matchup on the same fixture
          </span>
          {rows.length > 0 && (
            <span className="font-mono-data text-[10px] text-muted-foreground ml-1" data-testid="perfect-count">
              {rows.length} found
            </span>
          )}
        </div>
        <div className="lg:ml-auto flex flex-wrap items-center gap-2">
          <Select value={minHits} onValueChange={setMinHits}>
            <SelectTrigger data-testid="perfect-run" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {RUNS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger data-testid="perfect-window" className="w-[140px] bg-[#121212] border-border text-xs h-8"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-[#121212] border-border">
              {WINDOWS.map((o) => <SelectItem key={o.v} value={o.v} className="text-xs">{o.l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="overflow-x-auto sm:max-h-[420px] sm:overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5 sticky left-0 bg-card z-20">Team</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Next</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="What the run says: the line this team keeps clearing, and how often">The run</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Tightest winning margin across the window — how close the run has come to breaking">Cushion</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Corners this opponent concedes per game at this venue. Measured on THEIR games — the half of the signal the run doesn't already contain.">Opp leaks</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="Projected corners for this team in this fixture">Proj λ</th>
              <th className="text-left font-medium px-2 py-1.5 sm:px-4 sm:py-2.5"
                title="The line the projection supports for this fixture — not always the line the run has been clearing">Fixture line</th>
              <th className="text-right font-medium px-2 py-1.5 sm:px-4 sm:py-2.5">Model odds</th>
              <th className="px-2 py-1.5 sm:px-4 sm:py-2.5"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {loading ? (
              <tr><td colSpan={9} className="px-4 py-12 text-center text-muted-foreground animate-pulse">
                Pairing runs with matchups…
              </td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-12 text-center text-muted-foreground">
                No fixture has both a run and a favourable matchup in this window. That is
                the normal state — try a wider window or the looser 4-of-5 run.
              </td></tr>
            ) : rows.map((r) => {
              const nf = r.next_fixture || {};
              const tight = tightestWin({ ...r.streak, direction: "over" });
              // The two lines disagreeing is information, not an error — see the note
              // on /perfect-games. Flagged rather than reconciled.
              const lineGap = r.mismatch.line - r.streak.line;
              return (
                <tr key={`${r.team_id}-${nf.fixture_id}`} data-testid="perfect-row"
                  onClick={() => nf.fixture_id && navigate(`/fixture/${nf.fixture_id}`)}
                  className="border-b border-border/50 hover:bg-white/5 cursor-pointer transition-colors"
                  style={{ borderLeft: "2px solid #10B981" }}>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 sticky left-0 bg-card z-10">
                    <div className="flex items-center gap-1.5">
                      <span className="text-foreground font-sans font-medium whitespace-nowrap">{r.name}</span>
                      <TeamStar teamId={r.team_id} teamName={r.name} />
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground uppercase tracking-wider font-sans">
                      <span className="truncate">{withFlag(r.league_id, r.league_name)}</span>
                      <TierBadge tier={r.tier} country={r.league_name} />
                    </div>
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                    <span className="text-foreground/80">{nf.is_home ? "vs" : "@"} {nf.opponent}</span>
                    <div className="text-[10px]">{kickoffLabel(nf.date)}</div>
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                      {r.streak.line_label}
                    </span>
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      {r.streak.hits}/{r.streak.settled}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">
                    {tight == null ? <span className="text-muted-foreground">—</span> : (
                      <span className={`font-semibold ${
                        tight >= 3 ? "text-emerald-400" : tight >= 2 ? "text-primary"
                          : tight >= 1 ? "text-amber-400" : "text-red-400"}`}
                        title={`Tightest winning game cleared by ${tight}`}>+{tight}</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground">
                    {r.mismatch.opp_conceded.toFixed(2)}
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground">
                    {Number(r.mismatch.lambda).toFixed(2)}
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 whitespace-nowrap">
                    <span className="text-foreground">{r.mismatch.line}+</span>
                    {lineGap !== 0 && (
                      <span className={`ml-1.5 text-[10px] font-sans ${lineGap > 0 ? "text-emerald-400" : "text-amber-400"}`}
                        title={lineGap > 0
                          ? `The fixture projects ${lineGap} above the ${r.streak.line}+ the run has been clearing — the matchup is doing the work.`
                          : `The fixture projects ${-lineGap} below the ${r.streak.line}+ the run has been clearing — the run is carrying this one.`}>
                        {lineGap > 0 ? `+${lineGap} vs run` : `${lineGap} vs run`}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right text-foreground">
                    {r.mismatch.fair_odds?.toFixed(2) ?? "—"}
                  </td>
                  <td className="px-2 py-1.5 sm:px-4 sm:py-2.5 text-right">
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground inline" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* THE CAVEAT IS PART OF THE FEATURE. "Perfect" plus two green ticks is exactly the
          screen someone over-stakes off, and the two signals are not independent. */}
      <div className="px-3 py-2.5 border-t border-border text-[11px] text-muted-foreground leading-relaxed">
        <p className="flex items-start gap-2">
          <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            <span className="text-foreground">These are two views of one team, not two independent models.</span>{" "}
            The run and the projection are both driven partly by how many corners this side
            wins, so a strong corner team tends to appear on both lists whoever it plays.
            The genuinely additional part is <span className="text-foreground">Opp leaks</span> —
            measured on the opponent's own games. Read a row as "a good run, against
            someone who concedes", and treat the shortlist as where to look rather than
            what to back.
          </span>
        </p>
      </div>
    </section>
  );
}
