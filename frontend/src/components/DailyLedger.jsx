import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { LineChart, RefreshCw, TrendingUp, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";

const unit = (n) => `${n > 0 ? "+" : ""}${n.toFixed(2)}u`;

// Asian lines can land half-won/half-lost, and a push returns the stake.
const RESULT = {
  won: ["Won", "text-emerald-400"],
  half_won: ["Half won", "text-emerald-400/80"],
  lost: ["Lost", "text-red-400"],
  half_lost: ["Half lost", "text-red-400/80"],
  void: ["Void", "text-zinc-400"],
  pending: ["Pending", "text-amber-400"],
};
const dayFmt = (d) => (d ? new Date(d).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—");

export default function DailyLedger() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.ledger().then(setData).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const snapshot = async () => {
    setBusy(true);
    try {
      const res = await api.snapshotLedger();
      toast.success(res.inserted ? `Locked in ${res.inserted} pick(s) for today` : "Nothing to lock in — no unplayed games left today");
      load();
    } catch { toast.error("Could not lock in today's picks"); }
    finally { setBusy(false); }
  };

  if (!data) return null;
  const s = data.summary || {};
  const rows = data.rows || [];
  const priced = rows.filter((r) => r.balance != null);
  const up = s.profit >= 0;

  return (
    <div className="space-y-4" data-testid="daily-ledger">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-primary mb-1">
            <LineChart className="h-4 w-4" />
            <span className="font-mono-data text-xs tracking-widest uppercase">Daily 2 · Rolling Ledger</span>
          </div>
          <h2 className="font-head text-2xl font-bold tracking-tight">Best 2 games each day, flat 1u</h2>
          <p className="text-muted-foreground text-sm mt-1">
            Picks are locked in before kickoff and never re-selected, so the balance below is a real forward record.
          </p>
        </div>
        <button
          data-testid="ledger-snapshot-btn"
          onClick={snapshot}
          disabled={busy}
          className="flex items-center gap-2 bg-secondary hover:bg-white/10 border border-border text-sm font-medium rounded-md px-3 py-2 transition-colors duration-150 disabled:opacity-60"
        >
          <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Lock in today
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat
          label={`from ${s.staked || 0} priced bet${s.staked === 1 ? "" : "s"}`}
          value={s.staked ? unit(s.profit) : "—"}
          cls={s.staked ? (up ? "text-emerald-400" : "text-red-400") : "text-muted-foreground"}
          icon={up ? TrendingUp : TrendingDown}
          testid="ledger-balance"
        />
        <Stat label="ROI" value={s.staked ? `${s.roi > 0 ? "+" : ""}${s.roi}%` : "—"} cls={s.staked ? (s.roi >= 0 ? "text-emerald-400" : "text-red-400") : "text-muted-foreground"} />
        <Stat label={s.settled ? `${s.won}/${s.settled} settled` : "no results yet"} value={s.settled ? `${s.win_rate}%` : "—"} cls="text-primary" />
        <Stat label="picks tracked" value={s.picks || 0} cls="text-foreground" />
      </div>

      {s.unpriced > 0 && (
        <p className="text-[11px] text-amber-400/90 font-mono-data">
          {s.unpriced} settled pick{s.unpriced > 1 ? "s have" : " has"} no bookmaker price recorded, so
          {s.unpriced > 1 ? " they are" : " it is"} counted in the strike rate but left out of the balance —
          scoring unpriced losses without their matching wins would force ROI to −100%.
          Enter odds on a fixture to bring {s.unpriced > 1 ? "them" : "it"} into the P/L.
        </p>
      )}

      {priced.length >= 2 && <BalanceChart rows={priced} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Breakdown title="By venue" groups={data.by_venue} />
        <Breakdown title="By signal" groups={data.by_signal} />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="font-head font-semibold text-sm">Every tracked pick</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
                <th className="text-left font-medium px-4 py-2">Date</th>
                <th className="text-left font-medium px-4 py-2">Pick</th>
                <th className="text-left font-medium px-4 py-2">Fixture</th>
                <th className="text-center font-medium px-2 py-2">V</th>
                <th className="text-right font-medium px-3 py-2">Odds</th>
                <th className="text-center font-medium px-3 py-2">Result</th>
                <th className="text-right font-medium px-3 py-2">P/L</th>
                <th className="text-right font-medium px-4 py-2">Balance</th>
              </tr>
            </thead>
            <tbody className="font-mono-data text-sm" data-testid="ledger-rows">
              {rows.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-muted-foreground text-xs">
                  No picks locked in yet — they are recorded automatically each morning, or hit "Lock in today".
                </td></tr>
              ) : rows.map((r, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-white/5 transition-colors duration-150">
                  <td className="px-4 py-2 text-muted-foreground text-xs whitespace-nowrap">{dayFmt(r.date)}</td>
                  <td className="px-4 py-2 text-foreground whitespace-nowrap">
                    <span className="font-sans">{r.team}</span> <span className="text-primary">{r.line}+</span>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground text-xs font-sans truncate max-w-[200px]">{r.home} v {r.away}</td>
                  <td className="px-2 py-2 text-center">
                    <span className={`text-[9px] px-1 py-0.5 rounded ${r.venue === "home" ? "bg-primary/15 text-primary" : "bg-zinc-500/15 text-zinc-400"}`}>
                      {r.venue === "home" ? "H" : "A"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-muted-foreground text-xs">
                    {r.odds ? r.odds.toFixed(2) : <span title="no bookmaker price recorded">—</span>}
                  </td>
                  <td className="px-3 py-2 text-center text-xs">
                    {(() => {
                      const [label, cls] = RESULT[r.status] || RESULT.pending;
                      return <span className={cls} title={r.settle_reason || undefined}>{label}</span>;
                    })()}
                    {r.result_corners != null && <span className="text-muted-foreground"> · {r.result_corners}</span>}
                  </td>
                  <td className={`px-3 py-2 text-right ${r.profit == null ? "text-muted-foreground" : r.profit >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {r.profit == null ? "—" : unit(r.profit)}
                  </td>
                  <td className={`px-4 py-2 text-right font-semibold ${r.balance == null ? "text-muted-foreground" : r.balance >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {r.balance == null ? "—" : unit(r.balance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function BalanceChart({ rows }) {
  const W = 800, H = 160, PAD = 24;
  const vals = rows.map((r) => r.balance);
  const min = Math.min(0, ...vals), max = Math.max(0, ...vals);
  const span = max - min || 1;
  const x = (i) => PAD + (i * (W - PAD * 2)) / Math.max(1, rows.length - 1);
  const y = (v) => H - PAD - ((v - min) / span) * (H - PAD * 2);
  const pts = rows.map((r, i) => `${x(i)},${y(r.balance)}`).join(" ");
  const last = vals[vals.length - 1];
  const stroke = last >= 0 ? "#10B981" : "#EF4444";
  return (
    <div className="bg-card border border-border rounded-lg p-4" data-testid="ledger-chart">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-head font-semibold text-sm">Rolling balance</h3>
        <span className="font-mono-data text-xs text-muted-foreground">{rows.length} settled bets</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 180 }} preserveAspectRatio="none">
        <line x1={PAD} x2={W - PAD} y1={y(0)} y2={y(0)} stroke="#3f3f46" strokeWidth="1" strokeDasharray="4 4" />
        <polyline points={pts} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {rows.map((r, i) => (
          <circle key={i} cx={x(i)} cy={y(r.balance)} r="2.5" fill={stroke} />
        ))}
      </svg>
      <div className="flex justify-between font-mono-data text-[10px] text-muted-foreground mt-1">
        <span>{dayFmt(rows[0].date)}</span>
        <span className={last >= 0 ? "text-emerald-400" : "text-red-400"}>{unit(last)}</span>
        <span>{dayFmt(rows[rows.length - 1].date)}</span>
      </div>
    </div>
  );
}

function Breakdown({ title, groups }) {
  const entries = Object.entries(groups || {}).filter(([, g]) => g.picks > 0);
  return (
    <div className="bg-card border border-border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-border">
        <h3 className="font-head font-semibold text-sm">{title}</h3>
      </div>
      {entries.length === 0 ? (
        <p className="px-4 py-6 text-center text-muted-foreground text-xs">Nothing tracked yet</p>
      ) : (
        // Wide on a phone: the card clips, so the table needs its own scroller.
        <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
              <th className="text-left font-medium px-4 py-2">Group</th>
              <th className="text-right font-medium px-3 py-2">Picks</th>
              <th className="text-right font-medium px-3 py-2">Strike</th>
              <th className="text-right font-medium px-3 py-2">P/L</th>
              <th className="text-right font-medium px-4 py-2">ROI</th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-sm">
            {entries.map(([k, g]) => (
              <tr key={k} className="border-b border-border/50">
                <td className="px-4 py-2 capitalize text-foreground">{k}</td>
                <td className="px-3 py-2 text-right text-muted-foreground">{g.picks}</td>
                <td className="px-3 py-2 text-right text-foreground">{g.settled ? `${g.win_rate}%` : "—"}</td>
                <td className={`px-3 py-2 text-right ${!g.staked ? "text-muted-foreground" : g.profit >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {g.staked ? unit(g.profit) : "—"}
                </td>
                <td className={`px-4 py-2 text-right font-semibold ${!g.staked ? "text-muted-foreground" : g.roi >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {g.staked ? `${g.roi > 0 ? "+" : ""}${g.roi}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}

const Stat = ({ label, value, cls, icon: Icon, testid }) => (
  <div className="bg-card border border-border rounded-lg px-4 py-3" data-testid={testid}>
    <div className="flex items-center gap-2">
      {Icon && <Icon className={`h-4 w-4 ${cls}`} />}
      <span className={`font-mono-data text-2xl font-bold ${cls}`}>{value}</span>
    </div>
    <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
  </div>
);
