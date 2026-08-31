import { useState, useEffect } from "react";
import { CornerDownRight, Crosshair } from "lucide-react";
import { api } from "@/lib/api";

// Mini "corner league table" — ranks the selected league's teams by corners won/game (+ shots/game).
export default function CornerLeagueTable({ leagueId }) {
  const [data, setData] = useState({ teams: [], league_name: "" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.cornerTable(leagueId).then(setData).catch(() => setData({ teams: [], league_name: "" })).finally(() => setLoading(false));
  }, [leagueId]);

  const max = Math.max(1, ...data.teams.map((t) => t.corners_won));

  return (
    <aside className="bg-card border border-border rounded-lg overflow-hidden lg:sticky lg:top-20" data-testid="corner-league-table">
      <div className="flex items-center gap-2 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <CornerDownRight className="h-4 w-4 text-primary" strokeWidth={2.5} />
        <div className="min-w-0">
          <h2 className="font-head font-semibold text-sm leading-tight truncate">Corner Table</h2>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider truncate">{data.league_name} · corners won /g</p>
        </div>
      </div>
      <div className="max-h-[560px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-card z-10">
            <tr className="border-b border-border text-muted-foreground text-[10px] uppercase tracking-wider">
              <th className="text-left font-medium px-3 py-2">#</th>
              <th className="text-left font-medium px-2 py-2">Team</th>
              <th className="text-right font-medium px-2 py-2" title="Corners won per game">CW</th>
              <th className="text-right font-medium px-3 py-2" title="Shots taken per game">Sh</th>
            </tr>
          </thead>
          <tbody className="font-mono-data text-xs">
            {loading ? (
              <tr><td colSpan={4} className="px-3 py-10 text-center text-muted-foreground animate-pulse">Loading…</td></tr>
            ) : data.teams.length === 0 ? (
              <tr><td colSpan={4} className="px-3 py-10 text-center text-muted-foreground text-[11px]">No corner data for this league yet.</td></tr>
            ) : data.teams.map((t, i) => (
              <tr key={t.team_id} data-testid="corner-table-row" className="border-b border-border/40 hover:bg-white/5 transition-colors duration-150">
                <td className="px-3 py-1.5 text-muted-foreground">{i + 1}</td>
                <td className="px-2 py-1.5">
                  <div className="relative">
                    <div className="absolute inset-0 bg-primary/10 rounded-sm" style={{ width: `${(t.corners_won / max) * 100}%` }} />
                    <span className="relative text-foreground font-sans whitespace-nowrap truncate block max-w-[120px]">{t.name}</span>
                  </div>
                </td>
                <td className="px-2 py-1.5 text-right text-primary font-semibold">{t.corners_won.toFixed(1)}</td>
                <td className="px-3 py-1.5 text-right text-muted-foreground flex items-center justify-end gap-1">
                  <Crosshair className="h-3 w-3 opacity-50" />{t.shots.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </aside>
  );
}
