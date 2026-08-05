import { useState, useEffect } from "react";
import { Database, CheckCircle2, AlertTriangle, Loader2, Clock } from "lucide-react";
import { api } from "@/lib/api";

const STATUS = {
  success: { icon: CheckCircle2, cls: "text-emerald-400", label: "Success" },
  partial: { icon: AlertTriangle, cls: "text-amber-400", label: "Partial" },
  failed: { icon: AlertTriangle, cls: "text-red-400", label: "Failed" },
  running: { icon: Loader2, cls: "text-primary", label: "Running", spin: true },
};

const when = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

export default function SyncPanel() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let timer;
    const tick = async () => {
      let data = [];
      try { data = await api.syncRuns(8); if (active) setRuns(data); } catch {} finally { if (active) setLoading(false); }
      if (!active) return;
      const running = data[0]?.status === "running";
      timer = setTimeout(tick, running ? 6000 : 30000);
    };
    tick();
    return () => { active = false; clearTimeout(timer); };
  }, []);

  const latest = runs[0];

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="sync-panel">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Database className="h-4 w-4 text-primary" />
        <h2 className="font-head font-semibold text-lg">Data &amp; Sync</h2>
        <span className="text-xs text-muted-foreground hidden sm:inline">auto-refreshes 07:00 &amp; 19:00 UTC · frontend reads only cached data</span>
      </div>

      <div className="p-4 space-y-3">
        {loading ? (
          <p className="text-muted-foreground text-sm animate-pulse">Loading sync history…</p>
        ) : !latest ? (
          <p className="text-muted-foreground text-sm">No sync runs recorded yet.</p>
        ) : (
          <>
            {/* latest run summary */}
            <LatestSummary run={latest} />

            {/* errors from latest run */}
            {(latest.leagues || []).some((l) => l.status === "error") && (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3" data-testid="sync-errors">
                <p className="text-xs font-medium text-red-400 mb-1">Errors this run</p>
                <ul className="space-y-0.5 font-mono-data text-[11px] text-red-300/90">
                  {latest.leagues.filter((l) => l.status === "error").map((l) => (
                    <li key={l.league_id}>· {l.league_id}: {l.error}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* recent runs */}
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                    <th className="text-left font-medium px-2 py-2">Started</th>
                    <th className="text-left font-medium px-2 py-2">Trigger</th>
                    <th className="text-left font-medium px-2 py-2">Status</th>
                    <th className="text-right font-medium px-2 py-2">Leagues</th>
                    <th className="text-right font-medium px-2 py-2" title="Fixtures fetched from API vs served from cache">API / Cache</th>
                  </tr>
                </thead>
                <tbody className="font-mono-data text-xs">
                  {runs.map((r) => {
                    const s = STATUS[r.status] || STATUS.running;
                    const SIcon = s.icon;
                    const okCount = (r.leagues || []).filter((l) => l.status === "ok").length;
                    const fetched = (r.leagues || []).reduce((a, l) => a + (l.api_fetched || 0), 0);
                    const cache = (r.leagues || []).reduce((a, l) => a + (l.cache_hit || 0), 0);
                    return (
                      <tr key={`${r.trigger}-${r.started_at}`} data-testid="sync-run-row" className="border-b border-border/40">
                        <td className="px-2 py-1.5 text-muted-foreground whitespace-nowrap">{when(r.started_at)}</td>
                        <td className="px-2 py-1.5 text-muted-foreground">{r.trigger}</td>
                        <td className={`px-2 py-1.5 ${s.cls}`}>
                          <span className="inline-flex items-center gap-1">
                            <SIcon className={`h-3 w-3 ${s.spin ? "animate-spin" : ""}`} />{s.label}
                          </span>
                        </td>
                        <td className="px-2 py-1.5 text-right text-foreground">{okCount}/{(r.targets || []).length}</td>
                        <td className="px-2 py-1.5 text-right text-muted-foreground">
                          <span className="text-amber-400">{fetched}</span> / <span className="text-emerald-400">{cache}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function LatestSummary({ run }) {
  const s = STATUS[run.status] || STATUS.running;
  const Icon = s.icon;
  const fetched = (run.leagues || []).reduce((a, l) => a + (l.api_fetched || 0), 0);
  const cache = (run.leagues || []).reduce((a, l) => a + (l.cache_hit || 0), 0);
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-md bg-secondary/60 border border-border p-3">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${s.cls} ${s.spin ? "animate-spin" : ""}`} />
        <span className={`text-sm font-medium ${s.cls}`}>{s.label}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Clock className="h-3.5 w-3.5" /> {when(run.finished_at || run.started_at)}
        <span className="opacity-40">·</span> {run.trigger}
      </div>
      <div className="font-mono-data text-xs text-muted-foreground">
        <span className="text-amber-400">{fetched}</span> fetched from API ·{" "}
        <span className="text-emerald-400">{cache}</span> served from cache (quota saved)
      </div>
    </div>
  );
}
