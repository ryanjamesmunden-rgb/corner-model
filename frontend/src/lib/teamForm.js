// The followed-team form graph's arithmetic, kept out of the component so it is testable.
//
// Input is the `form` list from /favourites/teams: a side's last twenty REAL games,
// OLDEST FIRST, each { date, opponent, home, won, conceded, total, gf, ga }.
//
// VENUE FILTERS FIRST, THEN THE WINDOW. "Last 5 home" means the five most recent games
// played at home — not whichever of the last five overall happened to be at home, which
// would usually be two or three games and read as a bug.

export const VENUES = [
  { key: "all", label: "All" },
  { key: "home", label: "Home" },
  { key: "away", label: "Away" },
];

export const WINDOWS = [5, 10, 20];

export const METRICS = [
  { key: "won", label: "Won" },
  { key: "conceded", label: "Conceded" },
  { key: "total", label: "Match" },
];

const avg = (xs) => (xs.length ? Math.round((xs.reduce((s, x) => s + x, 0) / xs.length) * 100) / 100 : null);

/** The games the graph draws, oldest first, and the summary under it. */
export function formView(form, { venue = "all", window = 20, metric = "won", line = null } = {}) {
  let games = Array.isArray(form) ? form : [];
  if (venue === "home") games = games.filter((g) => g.home);
  else if (venue === "away") games = games.filter((g) => !g.home);
  games = games.slice(-window);

  // A game with no value for this metric (an old row missing the concede count) is left
  // out of the average rather than counted as zero — zero corners is a real result.
  const vals = games.map((g) => g[metric]).filter((v) => typeof v === "number");
  const out = {
    games,
    n: games.length,
    avg: avg(vals),
    high: vals.length ? Math.max(...vals) : null,
    low: vals.length ? Math.min(...vals) : null,
    peak: vals.length ? Math.max(...vals) : 0,
    hits: null,
    run: null,
  };

  if (line != null && vals.length) {
    out.hits = vals.filter((v) => v >= line).length;
    // The live run, counted back from the newest game. A miss — or a game with no
    // number — ends it; a run that skips a gap is not a run.
    let run = 0;
    for (let i = games.length - 1; i >= 0; i -= 1) {
      const v = games[i][metric];
      if (typeof v !== "number" || v < line) break;
      run += 1;
    }
    out.run = run;
  }
  return out;
}

/** A sensible default line to judge hits against: the average, rounded down, min 1. */
export function defaultLine(avgValue) {
  if (avgValue == null) return null;
  return Math.max(1, Math.floor(avgValue));
}
