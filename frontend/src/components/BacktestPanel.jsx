import { useState, useEffect } from "react";
import { FlaskConical, Target } from "lucide-react";
import { api } from "@/lib/api";

// Walk-forward backtest: model corner odds vs real results, v3 (previous) vs v4 (live).
// A v4 run returns v3 scored on its OWN rows (v3_same_sample), so one call gives both
// models on an identical sample — two separate calls would compare different rows.
//
// v4 = v3 plus the opponent's blocking. Its weight was NOT swept before shipping, so this
// panel is the thing that decides whether it stays: if v3 wins here, the term should go
// to zero. The copy below says so rather than presenting the live model as settled.
export default function BacktestPanel({ leagueId }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.backtest(scope === "all" ? "all" : leagueId, "v4")
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [leagueId, scope]);

  const v4 = data;
  const v3 = data?.v3_same_sample;
  const byLine = {};
  (v3?.lines || []).forEach((l) => { byLine[l.line] = { line: l.line, n: l.n, actual: l.actual_hit_rate, v3: l.model_prob }; });
  (v4?.lines || []).forEach((l) => { byLine[l.line] = { ...(byLine[l.line] || { line: l.line, n: l.n, actual: l.actual_hit_rate }), v4: l.model_prob }; });
  const rows = Object.values(byLine);
  const used = v4?.rows_using_opponent_blocking ?? 0;
  const better = v3?.overall_brier != null && v4?.overall_brier != null && v4.overall_brier < v3.overall_brier;
  // Stated plainly because it is the whole decision: a run where the term barely applied
  // cannot answer the question either way, and a run it lost is an instruction to switch
  // the term off, not a curiosity.
  const verdict = used === 0 ? "none"
    : v3?.overall_brier == null || v4?.overall_brier == null ? "none"
    : better ? "keep" : "drop";

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="backtest-panel">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold text-lg">Model Backtest — v3 vs v4</h2>
        <span className="text-xs text-muted-foreground hidden md:inline">how the model's corner odds matched real results (walk-forward, no leakage)</span>
        <div className="ml-auto flex rounded-md bg-secondary p-0.5">
          {["all", "league"].map((s) => (
            <button key={s} data-testid={`backtest-scope-${s}`} onClick={() => setScope(s)}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${scope === s ? "bg-primary text-black font-medium" : "text-muted-foreground"}`}>
              {s === "all" ? "All leagues" : "This league"}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <p className="text-muted-foreground text-sm animate-pulse">Running backtest…</p>
        ) : !rows.length ? (
          <p className="text-muted-foreground text-sm">Not enough historical data to backtest this league yet.</p>
        ) : (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <ScoreCard title="v3 — previous (team's own blocked shots)" brier={v3?.overall_brier}
                gap={v3?.avg_calibration_gap} accent="#64748B" matches={v4?.matches} />
              <ScoreCard title="v4 — live (+ opponent's blocking)" brier={v4?.overall_brier}
                gap={v4?.avg_calibration_gap} accent="#22D3EE" matches={v4?.matches} better={better} />
            </div>

            <div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2 mb-4 text-[11px] text-muted-foreground" data-testid="backtest-coverage">
              {verdict === "none" ? (
                <>Not enough of this sample carries the opponent's blocked shots, so <span className="text-foreground">v4 is pricing exactly as v3 here</span> and this run cannot judge the new term either way. Run the backfill to give it something to work with.</>
              ) : (
                <>
                  <span className="text-foreground font-mono-data">{used.toLocaleString()}</span> predictions used the opponent's blocking
                  {v4?.opp_weight != null && <> at weight <span className="font-mono-data">{v4.opp_weight}</span></>}.{" "}
                  {verdict === "keep" ? (
                    <span className="text-emerald-400">v4 beats v3 on this sample — the term is earning its place.</span>
                  ) : (
                    <span className="text-amber-400">v4 does NOT beat v3 on this sample. Sweep <span className="font-mono-data">opp_weight</span>, and if nothing wins, set <span className="font-mono-data">V4_OPP_BLOCKED_WEIGHT</span> to 0 to price as v3 again.</span>
                  )}
                </>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                    <th className="text-left font-medium px-2 py-2">Team line</th>
                    <th className="text-right font-medium px-2 py-2">Sample</th>
                    <th className="text-right font-medium px-2 py-2" title="What actually happened">Actual %</th>
                    <th className="text-right font-medium px-2 py-2">v3 says</th>
                    <th className="text-right font-medium px-2 py-2">v4 says</th>
                  </tr>
                </thead>
                <tbody className="font-mono-data text-sm">
                  {rows.map((r) => {
                    const g3 = r.v3 != null ? Math.abs(r.v3 - r.actual) : null;
                    const g4 = r.v4 != null ? Math.abs(r.v4 - r.actual) : null;
                    return (
                      <tr key={r.line} data-testid="backtest-row" className="border-b border-border/40">
                        <td className="px-2 py-2 text-foreground flex items-center gap-1.5"><Target className="h-3 w-3 text-primary/70" />{r.line}+ corners</td>
                        <td className="px-2 py-2 text-right text-muted-foreground">{r.n?.toLocaleString()}</td>
                        <td className="px-2 py-2 text-right text-foreground font-semibold">{r.actual?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g3 > 2 ? "text-amber-400" : "text-muted-foreground"}`}>{r.v3?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g4 != null && g3 != null && g4 <= g3 ? "text-emerald-400" : "text-primary"}`}>{r.v4?.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              Closer to <span className="text-foreground">Actual %</span> = more trustworthy odds. Brier &amp; average gap both lower = better.
              Both models are scored on the <span className="text-foreground">same rows</span>, so this is a like-for-like comparison.
              <span className="text-foreground"> v4 is live across the site</span> — on top of v3 it reads how many shots the OPPOSING side blocks, since a block is the commonest way a shot becomes a corner. Where that history is missing it prices exactly as v3 did, so no fixture prices worse than before.
            </p>
          </>
        )}
      </div>
    </section>
  );
}

function ScoreCard({ title, brier, gap, accent, better, matches }) {
  return (
    <div className="rounded-md border border-border p-3" style={{ borderLeft: `3px solid ${accent}` }}>
      <p className="text-xs text-muted-foreground mb-1.5">{title}{better && <span className="ml-2 text-emerald-400 font-medium">✓ better</span>}</p>
      <div className="flex items-center gap-5 font-mono-data">
        <div><span className="text-lg font-bold" style={{ color: accent }}>{brier}</span><span className="text-[10px] text-muted-foreground ml-1">Brier</span></div>
        <div><span className="text-lg font-bold" style={{ color: accent }}>±{gap?.toFixed(2)}%</span><span className="text-[10px] text-muted-foreground ml-1">avg gap</span></div>
        {matches != null && <div className="text-[10px] text-muted-foreground ml-auto">{matches.toLocaleString()} matches</div>}
      </div>
    </div>
  );
}
