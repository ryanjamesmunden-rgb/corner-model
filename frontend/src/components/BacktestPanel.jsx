import { useState, useEffect } from "react";
import { FlaskConical, Target } from "lucide-react";
import { api } from "@/lib/api";

// Walk-forward backtest: model corner odds vs real results, v2 (previous) vs v3 (live).
// A v3 run returns v2 scored on its OWN rows (v2_same_sample), so one call gives both
// models on an identical sample — two separate calls would compare different rows.
export default function BacktestPanel({ leagueId }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.backtest(scope === "all" ? "all" : leagueId, "v3")
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [leagueId, scope]);

  const v3 = data;
  const v2 = data?.v2_same_sample;
  const byLine = {};
  (v2?.lines || []).forEach((l) => { byLine[l.line] = { line: l.line, n: l.n, actual: l.actual_hit_rate, v2: l.model_prob }; });
  (v3?.lines || []).forEach((l) => { byLine[l.line] = { ...(byLine[l.line] || { line: l.line, n: l.n, actual: l.actual_hit_rate }), v3: l.model_prob }; });
  const rows = Object.values(byLine);
  const used = v3?.rows_using_blocked ?? 0;
  const fell = v3?.rows_fell_back_to_v2 ?? 0;
  const better = v2?.overall_brier != null && v3?.overall_brier != null && v3.overall_brier < v2.overall_brier;

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="backtest-panel">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold text-lg">Model Backtest — v2 vs v3</h2>
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
              <ScoreCard title="v2 — previous (shots intent)" brier={v2?.overall_brier}
                gap={v2?.avg_calibration_gap} accent="#64748B" matches={v3?.matches} />
              <ScoreCard title="v3 — live (blocked-shots intent)" brier={v3?.overall_brier}
                gap={v3?.avg_calibration_gap} accent="#22D3EE" matches={v3?.matches} better={better} />
            </div>

            <div className="rounded-md border border-border/60 bg-secondary/30 px-3 py-2 mb-4 text-[11px] text-muted-foreground" data-testid="backtest-coverage">
              {used === 0 ? (
                <>No blocked-shots history in this sample yet, so <span className="text-foreground">v3 is pricing exactly as v2 here</span>. Run the backfill to give it something to work with.</>
              ) : (
                <>
                  <span className="text-foreground font-mono-data">{used.toLocaleString()}</span> predictions used blocked shots;{" "}
                  <span className="text-foreground font-mono-data">{fell.toLocaleString()}</span> fell back to v2 (not enough history).
                  {fell > used && " Most of the sample is still falling back — extending the backfill would grow the gain."}
                  {v3?.blocked_weight != null && <> Intent weight <span className="font-mono-data">{v3.blocked_weight}</span>.</>}
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
                    <th className="text-right font-medium px-2 py-2">v2 says</th>
                    <th className="text-right font-medium px-2 py-2">v3 says</th>
                  </tr>
                </thead>
                <tbody className="font-mono-data text-sm">
                  {rows.map((r) => {
                    const g2 = r.v2 != null ? Math.abs(r.v2 - r.actual) : null;
                    const g3 = r.v3 != null ? Math.abs(r.v3 - r.actual) : null;
                    return (
                      <tr key={r.line} data-testid="backtest-row" className="border-b border-border/40">
                        <td className="px-2 py-2 text-foreground flex items-center gap-1.5"><Target className="h-3 w-3 text-primary/70" />{r.line}+ corners</td>
                        <td className="px-2 py-2 text-right text-muted-foreground">{r.n?.toLocaleString()}</td>
                        <td className="px-2 py-2 text-right text-foreground font-semibold">{r.actual?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g2 > 2 ? "text-amber-400" : "text-muted-foreground"}`}>{r.v2?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g3 != null && g2 != null && g3 <= g2 ? "text-emerald-400" : "text-primary"}`}>{r.v3?.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              Closer to <span className="text-foreground">Actual %</span> = more trustworthy odds. Brier &amp; average gap both lower = better.
              Both models are scored on the <span className="text-foreground">same rows</span>, so this is a like-for-like comparison.
              <span className="text-foreground"> v3 is live across the site</span> — it uses blocked shots where a team has enough history and falls back to v2 everywhere else, so no team prices worse than it did under v2.
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
