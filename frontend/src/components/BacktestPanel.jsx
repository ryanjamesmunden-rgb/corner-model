import { useState, useEffect } from "react";
import { FlaskConical, Target } from "lucide-react";
import { api } from "@/lib/api";

// Walk-forward backtest: how well the model's team-corner probabilities matched reality.
export default function BacktestPanel({ leagueId }) {
  const [data, setData] = useState(null);
  const [scope, setScope] = useState("league"); // 'league' | 'all'
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.backtest(scope === "all" ? "all" : leagueId, "v1")
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [leagueId, scope]);

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="backtest-panel">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold text-lg">Model Backtest</h2>
        <span className="text-xs text-muted-foreground hidden md:inline">how the model's corner odds matched real results (walk-forward, no leakage)</span>
        <div className="ml-auto flex rounded-md bg-secondary p-0.5">
          {["league", "all"].map((s) => (
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
        ) : !data || !data.lines?.length ? (
          <p className="text-muted-foreground text-sm">Not enough historical data to backtest this league yet.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono-data text-xs text-muted-foreground mb-3">
              <span><span className="text-foreground font-semibold">{data.matches.toLocaleString()}</span> matches</span>
              <span><span className="text-foreground font-semibold">{data.predictions.toLocaleString()}</span> predictions</span>
              <span title="Brier score — lower is better (0 = perfect)">Brier <span className="text-primary font-semibold">{data.overall_brier}</span></span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                    <th className="text-left font-medium px-2 py-2">Team line</th>
                    <th className="text-right font-medium px-2 py-2">Sample</th>
                    <th className="text-right font-medium px-2 py-2" title="What the model predicted on average">Model %</th>
                    <th className="text-right font-medium px-2 py-2" title="What actually happened">Actual %</th>
                    <th className="text-right font-medium px-2 py-2" title="Gap between model and reality — smaller is better">Gap</th>
                  </tr>
                </thead>
                <tbody className="font-mono-data text-sm">
                  {data.lines.map((l) => {
                    const good = l.calibration_gap <= 2;
                    return (
                      <tr key={l.line} data-testid="backtest-row" className="border-b border-border/40">
                        <td className="px-2 py-2 text-foreground flex items-center gap-1.5"><Target className="h-3 w-3 text-primary/70" />{l.line}+ corners</td>
                        <td className="px-2 py-2 text-right text-muted-foreground">{l.n.toLocaleString()}</td>
                        <td className="px-2 py-2 text-right text-primary">{l.model_prob}%</td>
                        <td className="px-2 py-2 text-right text-foreground font-semibold">{l.actual_hit_rate}%</td>
                        <td className={`px-2 py-2 text-right ${good ? "text-emerald-400" : "text-amber-400"}`}>±{l.calibration_gap}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted-foreground mt-2">
              Model % ≈ Actual % means the odds are trustworthy. A large gap on a line means the model is over/under-rating it — the target for model v2.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
