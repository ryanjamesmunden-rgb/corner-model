import { useState, useEffect, useCallback } from "react";
import { Terminal, Play, Loader2, CheckCircle2, AlertTriangle, KeyRound } from "lucide-react";
import { api } from "@/lib/api";

// Runs the analysis scripts from the browser so the whole loop works on a phone.
// Gated by TOOLS_TOKEN on the backend; the token is kept in localStorage only.
const TOKEN_KEY = "cm2_tools_token";

const MEASURES = [
  { mode: "features", label: "Blocked shots", hint: "does the shot data improve prediction?" },
  { mode: "sweep", label: "Weight sweep", hint: "try several blocked-shots intent weights" },
  { mode: "game_state", label: "Game state", hint: "the chase thesis — corners by half-time state" },
  { mode: "chase_board", label: "Chase board rank", hint: "does the board's ranking pick better spots?" },
  { mode: "backfill_fh", label: "Backfill half-time goals", hint: "fills fh_goals_against onto team history — needed for the corners-by-state splits" },
];

const when = (iso) => (iso ? new Date(iso).toLocaleString() : "—");

export default function ToolsPanel() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [draft, setDraft] = useState("");
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [limit, setLimit] = useState(120);

  const refresh = useCallback(async (t) => {
    if (!t) return;
    try {
      const d = await api.toolRuns(t);
      setRuns(d.runs || []);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not load runs");
      if (e?.response?.status === 403) setRuns([]);
    }
  }, []);

  // initial load on unlock
  useEffect(() => { if (token) refresh(token); }, [token, refresh]);

  // poll: schedule only — refreshing here as well would re-trigger this effect through
  // `runs` and loop without pause
  useEffect(() => {
    if (!token) return;
    const running = runs.some((r) => r.status === "running");
    const t = setTimeout(() => refresh(token), running ? 5000 : 30000);
    return () => clearTimeout(t);
  }, [token, refresh, runs]);

  const fire = async (fn) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh(token);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to start");
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <section className="bg-card border border-border rounded-lg" data-testid="tools-panel">
        <Header />
        <div className="p-4 flex flex-wrap items-center gap-2">
          <KeyRound className="h-4 w-4 text-muted-foreground" />
          <input
            type="password" value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="TOOLS_TOKEN" data-testid="tools-token-input"
            className="bg-[#121212] border border-border rounded px-2 py-1.5 text-sm font-mono-data flex-1 min-w-[160px]" />
          <button
            data-testid="tools-token-save"
            onClick={() => { localStorage.setItem(TOKEN_KEY, draft); setToken(draft); }}
            className="text-xs px-3 py-1.5 rounded bg-primary text-black font-medium">Unlock</button>
          <p className="text-[11px] text-muted-foreground w-full">
            Set <span className="font-mono-data">TOOLS_TOKEN</span> in the backend environment, then paste it here.
            Stored in this browser only.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-card border border-border rounded-lg" data-testid="tools-panel">
      <Header onLock={() => { localStorage.removeItem(TOKEN_KEY); setToken(""); setRuns([]); }} />
      <div className="p-4 space-y-4">
        <div>
          <p className="text-xs text-muted-foreground mb-2">Measurement — reads the database, no API calls</p>
          <div className="flex flex-wrap gap-2">
            {MEASURES.map((m) => (
              <button key={m.mode} disabled={busy} title={m.hint}
                data-testid={`tools-measure-${m.mode}`}
                onClick={() => fire(() => api.toolMeasure(token, m.mode))}
                className="text-xs px-3 py-1.5 rounded border border-border bg-secondary hover:bg-white/5 disabled:opacity-50 flex items-center gap-1.5">
                <Play className="h-3 w-3" /> {m.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-muted-foreground mb-2">
            Backfill — <span className="text-amber-400">spends API-Football credits</span>, one call per un-filled fixture
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input type="number" min={1} max={500} value={limit}
              onChange={(e) => setLimit(e.target.value)} data-testid="tools-backfill-limit"
              className="bg-[#121212] border border-border rounded px-2 py-1.5 text-sm font-mono-data w-24" />
            <span className="text-[11px] text-muted-foreground">per league</span>
            <button disabled={busy} data-testid="tools-backfill-run"
              onClick={() => fire(() => api.toolBackfill(token, { limit }))}
              className="text-xs px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 disabled:opacity-50 flex items-center gap-1.5">
              <Play className="h-3 w-3" /> Run backfill
            </button>
            <button disabled={busy} data-testid="tools-backfill-project"
              onClick={() => fire(() => api.toolBackfill(token, { project_only: true }))}
              className="text-xs px-3 py-1.5 rounded border border-border bg-secondary hover:bg-white/5 disabled:opacity-50">
              Project only (free)
            </button>
            <button disabled={busy} data-testid="tools-probe-halves"
              title="Can API-Football give corners split by half? ~6 calls on one fixture"
              onClick={() => fire(() => api.toolProbeHalves(token))}
              className="text-xs px-3 py-1.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 disabled:opacity-50 flex items-center gap-1.5">
              <Play className="h-3 w-3" /> Probe 1H/2H
            </button>
          </div>
        </div>

        {error && <p className="text-xs text-red-400" data-testid="tools-error">{error}</p>}

        <div className="space-y-2">
          {!runs.length ? (
            <p className="text-muted-foreground text-sm">No tool runs yet.</p>
          ) : runs.map((r, i) => <RunCard key={`${r.started_at}-${i}`} run={r} />)}
        </div>
      </div>
    </section>
  );
}

function Header({ onLock }) {
  return (
    <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
      <Terminal className="h-4 w-4 text-primary" />
      <h2 className="font-head font-semibold text-lg">Tools</h2>
      <span className="text-xs text-muted-foreground hidden sm:inline">run the analysis scripts without a shell</span>
      {onLock && (
        <button onClick={onLock} data-testid="tools-lock"
          className="ml-auto text-[11px] text-muted-foreground hover:text-foreground">Forget token</button>
      )}
    </div>
  );
}

function RunCard({ run }) {
  const [open, setOpen] = useState(run.status === "running");
  const meta = {
    running: { Icon: Loader2, cls: "text-primary animate-spin" },
    success: { Icon: CheckCircle2, cls: "text-emerald-400" },
    failed: { Icon: AlertTriangle, cls: "text-red-400" },
  }[run.status] || { Icon: AlertTriangle, cls: "text-muted-foreground" };
  const { Icon } = meta;
  return (
    <div className="rounded-md border border-border" data-testid="tools-run">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
        <Icon className={`h-4 w-4 shrink-0 ${meta.cls}`} />
        <span className="text-sm text-foreground font-mono-data">{run.script}</span>
        <span className="text-[11px] text-muted-foreground truncate">{run.label}</span>
        <span className="ml-auto text-[10px] text-muted-foreground whitespace-nowrap">{when(run.started_at)}</span>
      </button>
      {open && (
        <pre className="px-3 pb-3 text-[10px] leading-relaxed text-muted-foreground overflow-x-auto whitespace-pre max-h-[320px] overflow-y-auto">
{run.output || (run.status === "running" ? "running…" : "(no output)")}
        </pre>
      )}
    </div>
  );
}
