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

// ---------------------------------------------------------------------------------------
// Ranking the followed teams on Saved.
//
// Same slicing as the graph (venue first, then the window), so the number a card shows
// next to the team is the number its chart would show with the same toggles. Done on the
// page from the twenty games /favourites/teams already sends: no new endpoint, no request.

export const SAVED_SORTS = [
  { key: "next", label: "Kick-off" },
  { key: 5, label: "Last 5" },
  { key: 10, label: "Last 10" },
  { key: 20, label: "Last 20" },
];

// Under three games an average is an anecdote: a side with one 9-corner game must not sit
// above a side averaging 7 over five. Thin samples still show, below the rest.
export const MIN_RANK_GAMES = 3;

const nextKick = (t) => (t?.fixtures?.length ? String(t.fixtures[0].date) : "9999");

/**
 * Followed teams in the order the chosen sort asks for. Never mutates the input.
 *
 * "next" keeps the server's order (soonest game first). A window sorts by the average of
 * `metric` over the last N games at `venue`, highest first; ties go to the bigger sample,
 * then the sooner kick-off. Teams with fewer than MIN_RANK_GAMES games fall to the bottom.
 */
export function rankTeams(teams, { sort = "next", venue = "all", metric = "won" } = {}) {
  const list = Array.isArray(teams) ? teams : [];
  if (sort === "next") {
    return [...list].sort((a, b) => nextKick(a).localeCompare(nextKick(b)));
  }
  const scored = list.map((t) => ({ t, v: formView(t.form, { venue, window: sort, metric }) }));
  const thin = (s) => s.v.avg == null || s.v.n < MIN_RANK_GAMES;
  scored.sort((a, b) =>
    (thin(a) - thin(b))
    || ((b.v.avg ?? -1) - (a.v.avg ?? -1))
    || (b.v.n - a.v.n)
    || nextKick(a.t).localeCompare(nextKick(b.t)));
  return scored.map((s) => s.t);
}
