import { useState, useEffect } from "react";
import { toast } from "sonner";
import { ClipboardCheck, CheckCircle2, XCircle, Clock, RefreshCw, TrendingUp } from "lucide-react";
import { api } from "@/lib/api";

const MANUAL_KEY = "__manual__";
const dayFmt = (d) => (d === MANUAL_KEY ? "Manually tracked" : new Date(d).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" }));
const timeFmt = (iso) => (iso ? new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "");

const STATUS = {
  won: { icon: CheckCircle2, chip: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", bar: "#10B981", label: "Won" },
  lost: { icon: XCircle, chip: "bg-red-500/15 text-red-400 border-red-500/30", bar: "#EF4444", label: "Lost" },
  pending: { icon: Clock, chip: "bg-amber-500/15 text-amber-400 border-amber-500/30", bar: "#F59E0B", label: "Pending" },
};

export default function Picks() {
  const [data, setData] = useState({ record: {}, picks: [] });
  const [loading, setLoading] = useState(true);
  const [settling, setSettling] = useState(false);

  const load = () => api.picks().then(setData).catch(() => {}).finally(() => setLoading(false));

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  const settle = async () => {
    setSettling(true);
    try {
      await api.settlePicks();
      toast.success("Checking latest results — updating in ~15s…");
      setTimeout(() => { load(); setSettling(false); }, 15000);
    } catch {
      toast.error("Could not refresh results");
      setSettling(false);
    }
  };

  const r = data.record || {};
  // group picks by date; picks without a date are manually-tracked historical results
  const groups = {};
  (data.picks || []).forEach((p) => { const k = p.date || MANUAL_KEY; (groups[k] = groups[k] || []).push(p); });
  // manual group first, then dated groups ascending
  const dates = Object.keys(groups).sort((a, b) => {
    if (a === MANUAL_KEY) return -1;
    if (b === MANUAL_KEY) return 1;
    return a < b ? -1 : 1;
  });

  return (
    <div className="space-y-6" data-testid="picks-page">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <ClipboardCheck className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Tracked Live</span>
          </div>
          <h1 className="font-head text-3xl sm:text-4xl font-bold tracking-tight">Corner Model 2.0 Picks</h1>
          <p className="text-muted-foreground text-sm mt-1">Hand-picked team-corner angles — watch the results come in.</p>
        </div>
        <button
          data-testid="settle-picks-btn"
          onClick={settle}
          disabled={settling}
          className="flex items-center gap-2 bg-secondary hover:bg-white/10 border border-border text-sm font-medium rounded-md px-3 py-2 transition-colors duration-150 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${settling ? "animate-spin" : ""}`} />
          {settling ? "Checking…" : "Refresh results"}
        </button>
      </div>

      {/* Record strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="picks-record">
        <RecordChip label="Won" value={r.won ?? 0} cls="text-emerald-400" dot="bg-emerald-500" />
        <RecordChip label="Lost" value={r.lost ?? 0} cls="text-red-400" dot="bg-red-500" />
        <RecordChip label="Pending" value={r.pending ?? 0} cls="text-amber-400" dot="bg-amber-500" />
        <RecordChip label="Strike rate" value={r.settled ? `${r.win_rate}%` : "—"} cls="text-primary" dot="bg-primary" icon={TrendingUp} testid="picks-strike-rate" sub={r.settled ? `${r.won}/${r.settled} settled` : "no results yet"} />
      </div>

      {loading ? (
        <div className="py-20 text-center text-muted-foreground animate-pulse font-mono-data text-sm">Loading picks…</div>
      ) : dates.length === 0 ? (
        <div className="bg-card border border-border rounded-lg py-20 text-center text-muted-foreground text-sm">No picks tracked yet.</div>
      ) : (
        <div className="space-y-6">
          {dates.map((date) => (
            <div key={date}>
              <div className="flex items-center gap-2 mb-2">
                <h2 className="font-head font-semibold text-lg">{dayFmt(date)}</h2>
                <span className="font-mono-data text-xs text-muted-foreground">{groups[date].length} pick{groups[date].length > 1 ? "s" : ""}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {groups[date].map((p) => <PickRow key={`${p.date}-${p.home}-${p.team}-${p.line}`} p={p} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PickRow({ p }) {
  const s = STATUS[p.status] || STATUS.pending;
  const SIcon = s.icon;
  const hasFixture = p.home && p.away;
  return (
    <div
      data-testid="pick-card"
      className="bg-card border border-border rounded-lg p-4 flex items-center gap-4"
      style={{ borderLeft: `3px solid ${s.bar}` }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="font-head font-semibold text-base truncate">{p.team}</span>
          <span className="text-[11px] font-mono-data px-1.5 py-0.5 rounded bg-primary/15 text-primary border border-primary/30 shrink-0">{p.line}+ corners</span>
          {p.odds ? (
            <span data-testid="pick-odds" className="text-[11px] font-mono-data px-1.5 py-0.5 rounded bg-white/5 text-foreground border border-border shrink-0">@ {p.odds.toFixed(2)}</span>
          ) : (
            <span className="text-[10px] font-mono-data px-1.5 py-0.5 rounded bg-white/5 text-muted-foreground border border-border shrink-0">no odds</span>
          )}
        </div>
        {hasFixture ? (
          <p className="font-mono-data text-xs text-muted-foreground truncate">
            {p.home} <span className="opacity-50">v</span> {p.away}
          </p>
        ) : (
          <p className="font-mono-data text-xs text-muted-foreground truncate">{p.market || `${p.line}+ team corners`}</p>
        )}
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
          {p.league_name}{p.kickoff ? ` · ${timeFmt(p.kickoff)}` : ""}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${s.chip}`}>
          <SIcon className="h-3.5 w-3.5" /> {s.label}
        </span>
        {p.result_corners != null && (
          <span className="font-mono-data text-[11px] text-muted-foreground" data-testid="pick-result">
            {p.result_corners} corners
          </span>
        )}
      </div>
    </div>
  );
}

const RecordChip = ({ label, value, cls, dot, icon: Icon, sub, testid }) => (
  <div className="bg-card border border-border rounded-lg px-4 py-3" data-testid={testid}>
    <div className="flex items-center gap-2">
      {Icon ? <Icon className={`h-4 w-4 ${cls}`} /> : <span className={`h-2 w-2 rounded-full ${dot}`} />}
      <span className={`font-mono-data text-2xl font-bold ${cls}`}>{value}</span>
    </div>
    <p className="text-xs text-muted-foreground mt-0.5">{label}{sub ? ` · ${sub}` : ""}</p>
  </div>
);
