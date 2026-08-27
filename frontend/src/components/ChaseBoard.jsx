import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Target, Flame, ArrowRight, Plus, Zap } from "lucide-react";
import { api, tierMeta } from "@/lib/api";

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) : "");

export default function ChaseBoard({ leagueId = "all", withinDays = 7, limit = 25 }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.chaseBoard({ league_id: leagueId, within_days: withinDays, limit })
      .then((d) => setRows(d.board || []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [leagueId, withinDays, limit]);

  if (loading) {
    return <div className="bg-card border border-border rounded-lg py-16 text-center text-muted-foreground animate-pulse font-mono-data text-sm">Building this week's chase board…</div>;
  }
  if (rows.length === 0) {
    return <div className="bg-card border border-border rounded-lg py-16 text-center text-muted-foreground text-sm">No chase spots in this window. Try widening the days or switching to all leagues.</div>;
  }

  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden" data-testid="chase-board">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-xs uppercase tracking-wider">
              <th className="text-left font-medium px-4 py-3">#</th>
              <th className="text-left font-medium px-4 py-3">Chase spot</th>
              <th className="text-right font-medium px-3 py-3">Won/g</th>
              <th className="text-right font-medium px-3 py-3">Opp conc</th>
              <th className="text-right font-medium px-3 py-3" title="How often the opponent scores a first-half goal. Context only — five tests failed to find any effect from it, so it no longer influences the order.">Opp FH</th>
              <th className="text-center font-medium px-3 py-3" title="How many of the last 5 same-venue games the team hit this line">Hits</th>
              <th className="text-right font-medium px-3 py-3">Proj λ</th>
              <th className="text-left font-medium px-3 py-3">Line</th>
              <th className="text-right font-medium px-3 py-3">Fair</th>
              <th className="text-right font-medium px-4 py-3">Your edge</th>
              <th className="px-3 py-3"></th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {rows.map((r, i) => {
              const nf = r.next_fixture || {};
              const hot = r.opp_fh_rate >= 60;
              const solid = r.consistency === r.consistency_of;
              const t = r.tier ? tierMeta[r.tier] : null;
              return (
                <tr
                  key={`${r.team_id}-${i}`}
                  data-testid="chase-row"
                  onClick={() => nf.fixture_id && navigate(`/fixture/${nf.fixture_id}`)}
                  className="border-b border-border/50 hover:bg-white/5 cursor-pointer transition-colors duration-150"
                >
                  <td className="px-4 py-3 text-muted-foreground">{i + 1}</td>
                  <td className="px-4 py-3">
                    <div className="text-foreground whitespace-nowrap font-sans font-medium">
                      {r.name} <span className="text-muted-foreground font-normal">{nf.is_home ? "vs" : "@"}</span> {nf.opponent}
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground uppercase tracking-wider font-sans mt-0.5">
                      <span>{r.league_name}</span>
                      {fmtDate(nf.date) && <><span className="opacity-40">·</span><span className="text-primary/80 normal-case tracking-normal">{fmtDate(nf.date)}</span></>}
                      {nf.round && nf.round !== "Upcoming" && <><span className="opacity-40">·</span><span className="normal-case tracking-normal">{nf.round}</span></>}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-right text-emerald-400">{r.team_for.toFixed(1)}</td>
                  <td className="px-3 py-3 text-right text-red-400">{r.opp_conceded.toFixed(1)}</td>
                  <td className="px-3 py-3 text-right">
                    <span className={`inline-flex items-center gap-1 ${hot ? "text-amber-400 font-semibold" : "text-muted-foreground"}`}>
                      {hot && <Zap className="h-3 w-3" />}{r.opp_fh_rate}%
                    </span>
                  </td>
                  <td className="px-3 py-3 text-center">
                    <span className={`text-[11px] px-1.5 py-0.5 rounded border ${solid ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-white/5 text-muted-foreground border-border"}`}>
                      {r.consistency}/{r.consistency_of}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right text-foreground font-semibold">{r.lambda.toFixed(1)}</td>
                  <td className="px-3 py-3">
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-primary/15 text-primary border border-primary/30">{r.line}+</span>
                  </td>
                  <td className="px-3 py-3 text-right text-muted-foreground">{r.fair_odds?.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">
                    {r.ev != null ? (
                      <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${t ? t.chip : ""}`} data-testid="chase-ev">
                        {r.ev > 0 ? "+" : ""}{r.ev.toFixed(1)}% @ {r.book_odds}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-primary/80" data-testid="chase-add-odds">
                        <Plus className="h-3 w-3" /> add odds
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-right"><ArrowRight className="h-4 w-4 text-muted-foreground inline" /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* Measured, and it does not rank. Saying so on the panel matters more than the
          panel looking authoritative — the row order is a filter, not a pick order. */}
      <p className="px-4 py-2.5 border-t border-border text-[10px] text-muted-foreground">
        The order here is <span className="text-foreground">descriptive, not a measured edge</span>.
        Replaying this board walk-forward, its ranking scored +0.02 against a shuffled
        control of 0.00 — it does not find spots the model underrates. Use it as a filter
        (teams that clear their line reliably), and take the bet from the line and your own
        price, not from a row's position.
      </p>
    </div>
  );
}
