import { useState, useEffect } from "react";
import { FlaskConical, Target, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";

// Walk-forward backtest: model corner odds vs real results, v1 (old) vs v2 (new).
export default function BacktestPanel({ leagueId }) {
  const [v1, setV1] = useState(null);
  const [v2, setV2] = useState(null);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const id = scope === "all" ? "all" : leagueId;
    Promise.all([api.backtest(id, "v1"), api.backtest(id, "v2")])
      .then(([a, b]) => { setV1(a); setV2(b); })
      .catch(() => { setV1(null); setV2(null); })
      .finally(() => setLoading(false));
  }, [leagueId, scope]);

  const gapAvg = (d) => d && d.lines?.length ? (d.lines.reduce((s, l) => s + l.calibration_gap, 0) / d.lines.length) : null;
  const g1 = gapAvg(v1), g2 = gapAvg(v2);
  const byLine = {};
  (v1?.lines || []).forEach((l) => { byLine[l.line] = { line: l.line, n: l.n, actual: l.actual_hit_rate, v1: l.model_prob }; });
  (v2?.lines || []).forEach((l) => { byLine[l.line] = { ...(byLine[l.line] || { line: l.line, n: l.n, actual: l.actual_hit_rate }), v2: l.model_prob }; });
  const rows = Object.values(byLine);

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="backtest-panel">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold text-lg">Model Backtest — v1 vs v2</h2>
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
              <ScoreCard title="v1 — old (Poisson, corners only)" brier={v1?.overall_brier} gap={g1} accent="#64748B" matches={v1?.matches} />
              <ScoreCard title="v2 — new (dispersion + shots/form)" brier={v2?.overall_brier} gap={g2} accent="#22D3EE" matches={v2?.matches} better={g2 != null && g1 != null && g2 < g1} />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                    <th className="text-left font-medium px-2 py-2">Team line</th>
                    <th className="text-right font-medium px-2 py-2">Sample</th>
                    <th className="text-right font-medium px-2 py-2" title="What actually happened">Actual %</th>
                    <th className="text-right font-medium px-2 py-2">v1 says</th>
                    <th className="text-right font-medium px-2 py-2">v2 says</th>
                  </tr>
                </thead>
                <tbody className="font-mono-data text-sm">
                  {rows.map((r) => {
                    const g1l = r.v1 != null ? Math.abs(r.v1 - r.actual) : null;
                    const g2l = r.v2 != null ? Math.abs(r.v2 - r.actual) : null;
                    return (
                      <tr key={r.line} data-testid="backtest-row" className="border-b border-border/40">
                        <td className="px-2 py-2 text-foreground flex items-center gap-1.5"><Target className="h-3 w-3 text-primary/70" />{r.line}+ corners</td>
                        <td className="px-2 py-2 text-right text-muted-foreground">{r.n?.toLocaleString()}</td>
                        <td className="px-2 py-2 text-right text-foreground font-semibold">{r.actual?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g1l > 2 ? "text-amber-400" : "text-muted-foreground"}`}>{r.v1?.toFixed(1)}%</td>
                        <td className={`px-2 py-2 text-right ${g2l <= 1.5 ? "text-emerald-400" : "text-primary"}`}>{r.v2?.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              Closer to <span className="text-foreground">Actual %</span> = more trustworthy odds. v2 fixes the old model's over-rating of the lower lines. Brier &amp; average gap both lower = better. v2 is now live across the site.
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
