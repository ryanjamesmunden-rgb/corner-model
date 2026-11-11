// The multi-team form line chart's arithmetic, kept out of the page so it is testable.
//
// Input: teams from /team-form, each { team_id, name, form, tracked_at? } with `form` the
// last twenty REAL games, OLDEST FIRST, each { date, opponent, home, won, conceded, total }.
//
// ALIGNED ON THE MOST RECENT GAME. Teams play on different days, so the x-axis is "games
// ago", not a date: the right-hand edge is every team's latest game. A date axis would
// scatter ten lines across different Saturdays and make them impossible to compare.
//
// TWO MODES. "raw" plots the corner count. "diff" plots each game against THAT TEAM'S OWN
// average over the games shown — above zero they over-performed, below they under-performed
// — which is what lets a 4-a-game side and an 8-a-game side share one chart honestly.

export const PAGE_SIZE = 10;

// Ten series colours, validated (lightness band, chroma, adjacent colour-blind separation,
// normal-vision separation, contrast) against the site's dark card surface #11161d.
// Colour follows the team's slot on its page, never its rank.
export const SERIES_COLOURS = [
  "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181",
  "#008300", "#9085e9", "#e66767", "#1c9ab0", "#b8732a",
];

const round1 = (x) => Math.round(x * 10) / 10;
const mean = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);

/** One team's games for the current toggles, oldest first. Venue filters BEFORE the window. */
export function sliceGames(form, venue = "all", window = 20) {
  let games = Array.isArray(form) ? form : [];
  if (venue === "home") games = games.filter((g) => g.home);
  else if (venue === "away") games = games.filter((g) => !g.home);
  return games.slice(-window);
}

/** Pages of PAGE_SIZE, so no more than ten lines are ever drawn together. */
export function pages(teams, size = PAGE_SIZE) {
  const out = [];
  for (let i = 0; i < (teams || []).length; i += size) out.push(teams.slice(i, i + size));
  return out;
}

/**
 * Per-team summary: average, best and worst game against its own average (with the
 * opponent), and — for tracked teams — the average before and since tracking started.
 */
export function teamSummary(team, { venue = "all", window = 20, metric = "won" } = {}) {
  const games = sliceGames(team.form, venue, window)
    .filter((g) => typeof g[metric] === "number");
  const avg = mean(games.map((g) => g[metric]));
  const withDiff = games.map((g) => ({ ...g, value: g[metric], diff: round1(g[metric] - avg) }));
  const byDiff = [...withDiff].sort((a, b) => b.diff - a.diff);
  const out = {
    team_id: team.team_id,
    n: games.length,
    avg: avg == null ? null : Math.round(avg * 100) / 100,
    best: byDiff[0] || null,
    worst: byDiff.length ? byDiff[byDiff.length - 1] : null,
    over: withDiff.filter((g) => g.diff > 0).length,
    under: withDiff.filter((g) => g.diff < 0).length,
    since: null,
  };
  if (team.tracked_at) {
    const cut = String(team.tracked_at).slice(0, 10);
    const after = games.filter((g) => String(g.date || "").slice(0, 10) >= cut);
    const before = games.filter((g) => String(g.date || "").slice(0, 10) < cut);
    out.since = {
      tracked_at: team.tracked_at,
      games: after.length,
      avg: after.length ? Math.round(mean(after.map((g) => g[metric])) * 100) / 100 : null,
      before_avg: before.length ? Math.round(mean(before.map((g) => g[metric])) * 100) / 100 : null,
    };
  }
  return out;
}

/**
 * Chart rows, one per "games ago" slot, right-aligned on each team's latest game.
 * Row: { slot, ago, [team_id]: plotted value, [`${team_id}__g`]: the game itself }.
 * A team with fewer games simply has no point in the older slots.
 */
export function chartRows(teams, { venue = "all", window = 20, metric = "won", mode = "raw" } = {}) {
  const sliced = (teams || []).map((t) => {
    const games = sliceGames(t.form, venue, window);
    const vals = games.map((g) => g[metric]).filter((v) => typeof v === "number");
    return { id: t.team_id, games, avg: mean(vals) };
  });
  const width = Math.max(0, ...sliced.map((s) => s.games.length));
  const rows = [];
  for (let slot = 0; slot < width; slot += 1) rows.push({ slot, ago: width - slot });
  for (const s of sliced) {
    const offset = width - s.games.length;
    s.games.forEach((g, j) => {
      const v = g[metric];
      if (typeof v !== "number") return;   // a gap, not a zero
      const row = rows[offset + j];
      row[s.id] = mode === "diff" ? round1(v - s.avg) : v;
      row[`${s.id}__g`] = g;
    });
  }
  return rows;
}
