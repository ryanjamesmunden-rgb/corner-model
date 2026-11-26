import { Fragment } from "react";
import { resultOf } from "@/lib/formRun";
import {
  LAST_GAMES, chaseRead, fmt, lastGames, ordinal, splitAverage, stateRows, tableGap,
} from "@/lib/fixtureContext";

// THE CONTEXT AROUND THE CORNER LINE: where each side sits, how its last five went, and
// what its corners do when it is behind against when it is ahead. lib/fixtureContext has
// the reasoning; this only lays it out.

const RESULT_CLS = {
  W: "bg-primary/20 text-primary border border-primary/40",
  D: "bg-secondary text-muted-foreground border border-border",
  L: "bg-slate-600/25 text-slate-400 border border-slate-600/40",
};

const shortDate = (d) => {
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? "" : t.toLocaleDateString(undefined, { day: "numeric", month: "short" });
};

const READ_TEXT = {
  chases: { text: "Wins MORE corners when behind", cls: "text-emerald-400" },
  sits: { text: "Wins FEWER corners when behind", cls: "text-amber-400" },
  same: { text: "Corners barely move when behind", cls: "text-muted-foreground" },
};

function TableLine({ row }) {
  if (!row) {
    return <p className="text-xs text-muted-foreground">No league position on file this season.</p>;
  }
  return (
    <p className="text-xs" data-testid="table-line">
      <span className="font-semibold text-foreground">{ordinal(row.position)}</span>
      <span className="text-muted-foreground"> of {row.of} · {row.points} pts · GD {row.gd > 0 ? "+" : ""}{row.gd} · P{row.played}</span>
    </p>
  );
}

function LastFive({ team }) {
  const s = lastGames(team?.recent || []);
  if (!s.played) return <p className="text-xs text-muted-foreground">No recent games on file.</p>;
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
        Last {Math.min(LAST_GAMES, s.played)} · {s.wins}W {s.draws}D {s.losses}L
      </div>
      <ul className="space-y-1" data-testid="last-five">
        {s.games.map((g, i) => {
          const r = resultOf(g);
          return (
            <li key={`${g.date}-${i}`} className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className={`w-[18px] h-[18px] shrink-0 rounded-[3px] text-[10px] font-mono-data font-semibold flex items-center justify-center ${RESULT_CLS[r] || RESULT_CLS.D}`}>
                {r || "?"}
              </span>
              <span className="w-11 shrink-0 tabular-nums">{shortDate(g.date)}</span>
              <span className="w-3 shrink-0">{g.home ? "H" : "A"}</span>
              <span className="min-w-0 flex-1 truncate text-foreground">{g.opponent}</span>
              <span className="w-9 shrink-0 text-right tabular-nums">
                {typeof g.gf === "number" ? `${g.gf}-${g.ga}` : "—"}
              </span>
              <span className="w-12 shrink-0 text-right tabular-nums text-foreground" title="Corners won – conceded">
                {g.won}-{g.conceded}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-muted-foreground">
        Averages: {fmt(s.gf)} scored, {fmt(s.ga)} conceded · {fmt(s.won)} corners won, {fmt(s.conceded)} conceded
        {s.shotGames ? ` · ${fmt(s.shots)} shots${s.shotGames < s.played ? ` (${s.shotGames} game${s.shotGames === 1 ? "" : "s"})` : ""}` : ""}
      </p>
    </div>
  );
}

function StateTable({ team, venue }) {
  const venueSplit = team?.state_splits?.[venue];
  const allSplit = team?.state_splits?.overall;
  const vRows = stateRows(venueSplit);
  const aRows = stateRows(allSplit);
  if (!aRows.length) return null;
  const read = chaseRead(venueSplit) || chaseRead(allSplit);
  const cell = (r) => (
    r && r.games
      ? <span className={r.thin ? "text-muted-foreground" : "text-foreground"}>
          {fmt(r.won)} <span className="text-muted-foreground">({r.games})</span>
        </span>
      : <span className="text-muted-foreground">{"—"}</span>
  );
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Corners won by game state</div>
      <div className="grid text-xs gap-y-1 gap-x-3" style={{ gridTemplateColumns: "1fr auto auto" }}
        data-testid="state-table">
        <span />
        <span className="text-[10px] text-muted-foreground text-right capitalize">{venue}</span>
        <span className="text-[10px] text-muted-foreground text-right">All</span>
        {aRows.map((r, i) => (
          <Fragment key={r.key}>
            <span className="text-muted-foreground">{r.label}</span>
            <span className="text-right tabular-nums">{cell(vRows[i])}</span>
            <span className="text-right tabular-nums">{cell(r)}</span>
          </Fragment>
        ))}
        <span className="text-muted-foreground">Average</span>
        <span className="text-right tabular-nums">{fmt(splitAverage(venueSplit))}</span>
        <span className="text-right tabular-nums">{fmt(splitAverage(allSplit))}</span>
      </div>
      {read && (
        <p className={`text-xs ${READ_TEXT[read.verdict].cls}`}>
          {READ_TEXT[read.verdict].text} ({read.diff > 0 ? "+" : ""}{fmt(read.diff)} a game)
        </p>
      )}
    </div>
  );
}

export default function GameStatePanel({ data }) {
  const fx = data?.fixture;
  if (!fx) return null;
  const home = data.home_team, away = data.away_team;
  const gap = tableGap(home?.table, away?.table, fx.home_name, fx.away_name);
  const sides = [
    { key: "home", name: fx.home_name, team: home, venue: "home" },
    { key: "away", name: fx.away_name, team: away, venue: "away" },
  ];
  return (
    <div className="bg-card border border-border rounded-lg p-3.5 space-y-3" data-testid="game-state-panel">
      <div>
        <h3 className="font-head font-semibold text-sm">Game state</h3>
        <p className="text-xs text-muted-foreground mt-0.5">
          Who is likely to have the ball, and what each side&apos;s corners do when it is chasing.
        </p>
      </div>
      {gap && (
        <p data-testid="table-gap"
          className={`text-xs rounded-md px-2.5 py-1.5 ${gap.big
            ? "bg-amber-500/10 border border-amber-500/25 text-amber-200/90"
            : "bg-secondary text-muted-foreground"}`}>
          {gap.text}{gap.big ? ". A gap this big can mean the weaker side never gets the ball to chase with." : "."}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        {sides.map(({ key, name, team, venue }) => (
          <div key={key} className="min-w-0 space-y-2.5" data-testid={`game-state-${key}`}>
            <div>
              <div className="text-sm font-medium truncate">{name}</div>
              <TableLine row={team?.table} />
            </div>
            <LastFive team={team} />
            <StateTable team={team} venue={venue} />
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Table rebuilt from the results on file, so P shows how many games it counts. Game-state
        corners are full-match counts in games the side was behind, level or ahead at half-time
        — the provider gives no corner minutes. Brackets are games; grey means too few to lean on.
      </p>
    </div>
  );
}
