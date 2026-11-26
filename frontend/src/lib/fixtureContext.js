// The game-state panel: where each side sits, how its last five went, and what its corners
// do when it is chasing a game against when it is protecting one.
//
// WHY IT EXISTS. The corner numbers on this page say how many a side wins, not why. Bolton
// 6+ at home to West Brom (25 Nov 2026) was backed as the stronger side; West Brom sat
// above them, Bolton never had the ball to chase with, and won one corner. The table, the
// recent results and the chase/park split are the context that would have flagged it.
//
// Pure functions over the fixture payload, so jest can pin them — this page cannot be
// rendered in a test.

import { resultOf } from "./formRun";

export const LAST_GAMES = 5;
// Below this a state bucket's average is shown with its count but not compared, because
// "6.5 when trailing" over two games is an anecdote. Same instinct as state_corners'
// MIN_BUCKET, scaled to one team rather than a whole league.
export const MIN_STATE_GAMES = 4;
// A table gap this big means the weaker side may never get the ball, which is the Bayern
// game, not the chase that pays.
export const BIG_GAP_PLACES = 8;

const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const nums = (games, key) => games.map((g) => g?.[key]).filter((v) => typeof v === "number");

/** The last `n` games (newest first, as `recent` arrives) with a per-game summary. */
export function lastGames(recent = [], n = LAST_GAMES) {
  const games = (recent || []).slice(0, n);
  const results = games.map(resultOf);
  const graded = results.filter(Boolean);
  return {
    games,
    results,
    played: games.length,
    wins: graded.filter((r) => r === "W").length,
    draws: graded.filter((r) => r === "D").length,
    losses: graded.filter((r) => r === "L").length,
    gf: avg(nums(games, "gf")),
    ga: avg(nums(games, "ga")),
    won: avg(nums(games, "won")),
    conceded: avg(nums(games, "conceded")),
    shots: avg(nums(games, "shots_for")),
    // Shots are thinner than corners in the provider's data, so the count rides along
    // and the panel can say "3 of 5" rather than averaging three games as if it were five.
    shotGames: nums(games, "shots_for").length,
  };
}

/**
 * Corners won per game by half-time state, from one state_splits split.
 *
 * FULL-MATCH CORNERS, said on the panel: the provider has no corner minutes, so "trailing"
 * means the side's whole-game count in matches it was behind at the break, not corners won
 * while behind.
 */
export function stateRows(split) {
  const ht = split?.ht;
  if (!ht) return [];
  return [
    ["trailing", "Behind at HT"],
    ["level", "Level at HT"],
    ["leading", "Ahead at HT"],
  ].map(([key, label]) => {
    const b = ht[key] || {};
    return { key, label, games: b.games || 0, won: b.won ?? null, conceded: b.conceded ?? null,
             thin: (b.games || 0) < MIN_STATE_GAMES };
  });
}

/** Mean corners won across every game in a split, the baseline the states are read against. */
export function splitAverage(split) {
  const ht = split?.ht;
  if (!ht) return null;
  let n = 0, sum = 0;
  for (const key of ["trailing", "level", "leading"]) {
    const b = ht[key];
    if (b && b.games && typeof b.won === "number") { n += b.games; sum += b.won * b.games; }
  }
  return n ? sum / n : null;
}

/**
 * Does this side win MORE corners when it is behind? The question a chase angle rests on.
 * "chases" / "sits" / null — null when either bucket is too thin to say.
 */
export function chaseRead(split) {
  const ht = split?.ht;
  const base = splitAverage(split);
  const t = ht?.trailing;
  if (base == null || !t || (t.games || 0) < MIN_STATE_GAMES || typeof t.won !== "number") return null;
  const diff = t.won - base;
  if (diff >= 0.75) return { verdict: "chases", diff };
  if (diff <= -0.75) return { verdict: "sits", diff };
  return { verdict: "same", diff };
}

/** One line on the table gap between the two sides, or null when either is unplaced. */
export function tableGap(homeRow, awayRow, homeName, awayName) {
  if (!homeRow || !awayRow) return null;
  const gap = homeRow.position - awayRow.position;
  if (gap === 0) return null;
  const higher = gap < 0 ? homeName : awayName;
  const lower = gap < 0 ? awayName : homeName;
  const places = Math.abs(gap);
  return { higher, lower, places, big: places >= BIG_GAP_PLACES,
           text: `${higher} sit ${places} place${places === 1 ? "" : "s"} above ${lower}` };
}

export const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export const fmt = (v, dp = 1) => (typeof v === "number" ? v.toFixed(dp) : "—");
