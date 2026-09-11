import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Loader2, ArrowUp, ArrowDown, Info } from "lucide-react";
import { api } from "@/lib/api";
import PreviewWall from "@/components/PreviewWall";
import { flagBullet } from "@/lib/countryFlag";
import { kickoffLabel } from "@/lib/kickoff";

// EVERY GAME, RANKED BY PROJECTED CORNERS — BOTH ENDS OF THE LIST.
//
// The fixture board answers "what should I look at tonight": it needs a strong angle,
// applies an absolute quality bar, groups by day and caps each day. Three of those four
// make it structurally unable to answer "which of these games projects highest". A big
// projection with nothing to bet on is dropped as trivia, and the quiet end — the games
// projecting LOWEST, which is what an under is bet on — can never appear at all.
//
// So this shows the whole distribution, unfiltered, and lets it be read from either end.
//
// TWO ORDERINGS, BECAUSE THEY ARE DIFFERENT QUESTIONS. Both numbers sit on every row so
// they can be compared rather than chosen between — see the note above the toggle.

const SORTS = [
  { key: "total", label: "Projected total",
    hint: "The raw number. Will this game have a lot of corners?" },
  { key: "edge", label: "vs league par",
    hint: "The projection over what this league normally produces. Is it busy FOR ITS LEAGUE?" },
];

const DAYS = [3, 7, 14];

export default function Projections() {
  const navigate = useNavigate();
  const [sort, setSort] = useState("total");
  const [days, setDays] = useState(7);
  const [asc, setAsc] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["projections", sort, days],
    queryFn: () => api.projections({ sort, days, limit: 200 }),
  });

  const rows = useMemo(() => {
    const list = data?.rows || [];
    // The server ranks descending. Flipping here rather than re-fetching keeps the rank
    // numbers meaning "position in the full ranking" at either end — a row that is 1st
    // from the bottom is still the 180th busiest game, and relabelling it 1 would hide
    // that. Only ever reverses what was returned, so it cannot invent an ordering.
    return asc ? [...list].reverse() : list;
  }, [data, asc]);

  const par = sort === "edge";

  return (
    <div className="max-w-5xl mx-auto p-4 space-y-4" data-testid="projections-page">
      <div>
        <h1 className="font-head text-xl font-semibold">Projected corners</h1>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed max-w-2xl">
          Every upcoming game the model can price, ranked. Unlike the fixture board this
          filters nothing — a game with no angle on it still appears, and so does the
          bottom of the list, which is where an under lives.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded overflow-hidden border border-border">
          {SORTS.map((s) => (
            <button key={s.key} onClick={() => setSort(s.key)} title={s.hint}
              data-testid={`sort-${s.key}`}
              className={`text-xs px-3 py-1.5 ${sort === s.key
                ? "bg-primary text-primary-foreground font-semibold"
                : "bg-card text-muted-foreground hover:text-foreground"}`}>
              {s.label}
            </button>
          ))}
        </div>

        <div className="flex rounded overflow-hidden border border-border">
          {DAYS.map((d) => (
            <button key={d} onClick={() => setDays(d)}
              className={`text-xs px-3 py-1.5 ${days === d
                ? "bg-secondary text-foreground font-semibold"
                : "bg-card text-muted-foreground hover:text-foreground"}`}>
              {d}d
            </button>
          ))}
        </div>

        <button onClick={() => setAsc((v) => !v)} data-testid="flip-order"
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border
                     border-border bg-card text-muted-foreground hover:text-foreground">
          {asc ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
          {asc ? "Lowest first" : "Highest first"}
        </button>

        <span className="text-xs text-muted-foreground ml-auto">
          {isLoading ? "loading…"
            : `${data?.returned ?? 0} of ${data?.scanned ?? 0} games in the next ${days} days`}
        </span>
      </div>

      {/* THE CAVEAT GOES ABOVE THE TABLE, NOT UNDER IT. Sorted by raw total the head of
          this list is largely a ranking of which competitions produce corners rather than
          which matches are unusual, and someone reading the top five and stopping is
          exactly who needs to be told that. */}
      {!par && (
        <div className="flex gap-2 text-[11px] text-muted-foreground bg-secondary/30
                        border border-border rounded p-2.5 leading-relaxed">
          <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <p>
            Raw totals <span className="text-foreground">don't compare across leagues</span>.
            A projected 10.5 where the league averages 9.0 is a busy game; the same 10.5
            where par is 11.5 is a quiet one. Sorted this way the top of the list is mostly
            telling you which competitions produce corners — switch to{" "}
            <button onClick={() => setSort("edge")} className="text-primary underline">
              vs league par
            </button>{" "}
            to rank by how unusual a game is instead.
          </p>
        </div>
      )}

      {error && (
        <div className="text-sm text-red-400">Couldn't load the projections — try again.</div>
      )}

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 p-8 text-muted-foreground text-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> Projecting every fixture…
          </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No fixtures in the next {days} days with enough on record to project.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-muted-foreground
                               border-b border-border">
                  <th className="text-left font-medium px-3 py-2 w-10">#</th>
                  <th className="text-left font-medium px-3 py-2">Game</th>
                  {/* λ is a symbol, not a word: `uppercase` on this row turned it into Λ,
                      which is a different letter and means nothing here. */}
                  <th className="text-right font-medium px-3 py-2">
                    <span className="normal-case">λ</span> total
                  </th>
                  <th className="text-right font-medium px-3 py-2 hidden sm:table-cell">Par</th>
                  <th className="text-right font-medium px-3 py-2">vs par</th>
                  <th className="text-right font-medium px-3 py-2 hidden md:table-cell">Split</th>
                  <th className="text-right font-medium px-3 py-2 hidden lg:table-cell">Games</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const thin = Math.min(r.home_games, r.away_games) < 6;
                  return (
                    <tr key={r.fixture_id}
                      onClick={() => navigate(`/fixture/${r.fixture_id}`)}
                      className="border-b border-border/50 last:border-0 hover:bg-secondary/40
                                 cursor-pointer">
                      <td className="px-3 py-2 text-[11px] text-muted-foreground font-mono-data
                                     tabular-nums">{r.rank}</td>
                      <td className="px-3 py-2">
                        <div className="leading-tight">
                          {flagBullet(r.league_id)} {r.home} v {r.away}
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">
                          {r.league_name}
                          {r.date ? ` · ${kickoffLabel(r.date)}` : ""}
                          {r.angle_count > 0
                            ? ` · ${r.angle_count} angle${r.angle_count === 1 ? "" : "s"}`
                            : ""}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right font-mono-data tabular-nums
                                     font-semibold">
                        {r.lambda_total?.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono-data tabular-nums
                                     text-muted-foreground text-xs hidden sm:table-cell">
                        {r.league_avg_total?.toFixed(2)}
                      </td>
                      {/* The ratio is the only number here that means the same thing in
                          every league, so it is the one that gets the colour. */}
                      <td className={`px-3 py-2 text-right font-mono-data tabular-nums text-xs
                        ${r.corner_edge >= 1.1 ? "text-emerald-400"
                          : r.corner_edge <= 0.92 ? "text-sky-400" : "text-muted-foreground"}`}>
                        {r.corner_edge?.toFixed(2)}×
                      </td>
                      <td className="px-3 py-2 text-right font-mono-data tabular-nums text-xs
                                     text-muted-foreground hidden md:table-cell">
                        {r.lambda_home?.toFixed(1)} / {r.lambda_away?.toFixed(1)}
                      </td>
                      {/* A projection off four games is mostly the league prior wearing a
                          team's name. Shown rather than filtered, so a thin row is
                          visibly thin instead of quietly thin. */}
                      <td className={`px-3 py-2 text-right font-mono-data tabular-nums text-xs
                        hidden lg:table-cell ${thin ? "text-amber-400" : "text-muted-foreground"}`}>
                        {r.home_games}/{r.away_games}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {data?.preview && (
          <PreviewWall total={data.total} shown={rows.length} noun="games" />
        )}
      </div>

      <p className="text-[10px] text-muted-foreground leading-relaxed max-w-2xl">
        <span className="text-foreground">λ is an expected count, not a price.</span> It
        says how many corners the model expects, and nothing about what a bookmaker is
        offering — a high projection with no price beside it is a lead to check, not a bet.
        Amber in the Games column means one side has fewer than six matches on record, so
        its projection is carrying more league prior than team.
      </p>
    </div>
  );
}
