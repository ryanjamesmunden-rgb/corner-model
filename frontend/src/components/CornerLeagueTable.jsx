import { useState, useEffect } from "react";
import { CornerDownRight, ArrowDown } from "lucide-react";
import { api } from "@/lib/api";
import { SPLITS, COLS, THIN, rankTeams, cellFor, maxOf, barFor, splitOf }
  from "@/lib/cornerTable";

/**
 * The selected league's teams, ranked by whichever column you ask for.
 *
 * ONE SOLID AVERAGE TABLE ANSWERS ONE QUESTION. A side that wins eight corners a game at
 * home and four away averages six, and six is a number that describes neither of their
 * halves — so the overall table is the one view in which a home–away split is invisible.
 * Venue is a toggle now, and the column you rank on is a choice, because "who shoots
 * most away from home" and "who wins most corners overall" are different questions that
 * were sharing one answer.
 *
 * ALL THREE SPLITS ARRIVE IN ONE PAYLOAD and the sort happens here, so both controls are
 * instant. Nothing is refetched; there is no state in which the header says "Away" and
 * the rows are still the home ones.
 *
 * A SHOT COLUMN CARRIES ITS COVERAGE. The provider's shot data is thinner than its corner
 * data and thinner again on shots on target — a side can have twelve games of corners and
 * four of shots, and a four-game average sorted into a league table looks exactly like a
 * twelve-game one. Rows whose coverage is below THIN are dimmed and say how many games
 * they are actually built on, and a team with no coverage at all shows a dash rather than
 * a zero: "not recorded" and "none taken" are different claims.
 *
 * AND THEY RANK UNDERNEATH, which dimming alone did not achieve. The first version of
 * this marked a thin cell and left it where the number put it, so a side with one covered
 * game of thirty shots led the shots table over a side averaging eighteen across twelve.
 * The row that leads a table is the row people read. rankTeams has the argument.
 */

/** One figure, plus what it is built on where that is worth knowing. See cornerTable.js. */
function Cell({ row, col }) {
  const { missing, value, covered, thin } = cellFor(row, col);
  if (missing) {
    return <span className="text-muted-foreground/40" data-testid="corner-cell-missing"
                 title="Not recorded for this team">–</span>;
  }
  const games = `${covered} game${covered === 1 ? "" : "s"}`;
  return (
    <span className={thin ? "text-muted-foreground" : ""}
          title={thin ? `${value} over ${games} — a thin sample` : `${value} over ${games}`}>
      {value.toFixed(1)}
      {thin && <span className="ml-0.5 text-[9px] opacity-70">({covered})</span>}
    </span>
  );
}

export default function CornerLeagueTable({ leagueId }) {
  const [data, setData] = useState({ teams: [], league_name: "" });
  const [loading, setLoading] = useState(true);
  const [split, setSplit] = useState("overall");
  const [sort, setSort] = useState("corners_won");

  useEffect(() => {
    setLoading(true);
    api.cornerTable(leagueId)
      .then(setData)
      .catch(() => setData({ teams: [], league_name: "" }))
      .finally(() => setLoading(false));
  }, [leagueId]);

  const rows = rankTeams(data.teams || [], split, sort);
  const max = maxOf(rows, split, sort);
  const label = SPLITS.find((s) => s.v === split)?.label;

  return (
    <aside className="bg-card border border-border rounded-lg overflow-hidden lg:sticky lg:top-20"
           data-testid="corner-league-table">
      <div className="flex items-center gap-2 px-2 py-2 sm:px-4 sm:py-3 border-b border-border">
        <CornerDownRight className="h-4 w-4 text-primary" strokeWidth={2.5} />
        <div className="min-w-0">
          <h2 className="font-head font-semibold text-sm leading-tight truncate">Corner Table</h2>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider truncate">
            {data.league_name} · {label === "All" ? "all games" : `${label} only`}
          </p>
        </div>
      </div>

      <div className="flex gap-1 px-2 py-2 sm:px-3 border-b border-border">
        <div className="flex rounded-md bg-secondary p-0.5" data-testid="corner-table-splits">
          {SPLITS.map((s) => (
            <button key={s.v} onClick={() => setSplit(s.v)}
              data-testid={`corner-table-split-${s.v}`}
              aria-pressed={split === s.v}
              className={`text-[11px] px-2.5 py-1 rounded transition-colors ${
                split === s.v ? "bg-primary text-primary-foreground font-medium"
                              : "text-muted-foreground"}`}>
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-[560px] overflow-y-auto">
        {/* Wide on a phone: the card clips, so the table needs its own scroller. */}
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="border-b border-border text-muted-foreground text-[10px]
                             uppercase tracking-wider">
                <th className="text-left font-medium pl-2 pr-1 py-2">#</th>
                <th className="text-left font-medium px-1 py-2">Team</th>
                {COLS.map((c) => (
                  <th key={c.v} className="text-right font-medium pl-1 pr-1.5 py-2 last:pr-2">
                    {/* THE HEADER IS THE CONTROL. A separate sort menu beside a table whose
                        headers are not clickable is two places to look for one thing. */}
                    <button onClick={() => setSort(c.v)} title={`${c.title} — tap to rank by it`}
                      data-testid={`corner-table-sort-${c.v}`}
                      aria-pressed={sort === c.v}
                      className={`inline-flex items-center gap-0.5 uppercase tracking-wider
                                  transition-colors ${
                        sort === c.v ? "text-primary font-semibold"
                                     : "hover:text-foreground"}`}>
                      {c.short}
                      {sort === c.v && <ArrowDown className="h-2.5 w-2.5" />}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono-data text-xs">
              {loading ? (
                <tr><td colSpan={6}
                        className="px-3 py-10 text-center text-muted-foreground animate-pulse">
                  Loading…
                </td></tr>
              ) : !rows.length ? (
                <tr><td colSpan={6}
                        className="px-3 py-10 text-center text-muted-foreground text-[11px]">
                  No corner data for this league yet.
                </td></tr>
              ) : rows.map((t, i) => {
                const row = splitOf(t, split);
                const bar = barFor(row, COLS.find((c) => c.v === sort), max);
                return (
                  <tr key={t.team_id} data-testid="corner-table-row"
                      className="border-b border-border/40 hover:bg-white/5
                                 transition-colors duration-150">
                    <td className="pl-2 pr-1 py-1.5 text-muted-foreground">{i + 1}</td>
                    <td className="px-1 py-1.5">
                      <div className="relative">
                        <div className="absolute inset-0 bg-primary/10 rounded-sm"
                             style={{ width: `${bar * 100}%` }} />
                        <span className="relative text-foreground font-sans whitespace-nowrap
                                         truncate block max-w-[86px]">{t.name}</span>
                      </div>
                    </td>
                    {COLS.map((c) => (
                      <td key={c.v}
                          className={`pl-1 pr-1.5 py-1.5 text-right last:pr-2 ${
                            sort === c.v ? "text-primary font-semibold"
                                         : "text-muted-foreground"}`}>
                        <Cell row={row} col={c} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* SAID ONCE UNDER THE TABLE rather than as a caveat per row. A split being half a
          season is the thing that makes an away table readable, and a bracketed number
          is meaningless until somebody says what it counts. */}
      {!loading && rows.length > 0 && (
        <div className="px-3 py-2 text-[10px] text-muted-foreground border-t border-border
                        space-y-0.5" data-testid="corner-table-note">
          {split !== "overall" && (
            <p>{label} games only — roughly half a season each, so these move more than
              the combined table does.</p>
          )}
          <p>
            A bracketed figure is how many games that number is built on, where the
            provider covered fewer than {THIN}. Those rank below the better-evidenced
            rows; a dash means not recorded, which is not the same as none.
          </p>
        </div>
      )}
    </aside>
  );
}
