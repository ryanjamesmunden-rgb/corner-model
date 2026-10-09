/**
 * Ranking and reading the league's corner table.
 *
 * ONE SOLID AVERAGE TABLE ANSWERS ONE QUESTION. A side that wins eight corners a game at
 * home and four away averages six, and six describes neither of their halves — so the
 * overall table is the one view in which a home–away split is invisible. Venue is a
 * choice here, and so is the column being ranked, because "who shoots most away from
 * home" and "who wins most corners overall" are different questions that were sharing
 * one answer.
 *
 * A SHOT FIGURE IS NOT AS WELL EVIDENCED AS A CORNER ONE. The provider's shot coverage is
 * thinner than its corner coverage and thinner again on shots on target, so a side can
 * have twelve games of corners and four of shots. A four-game average sorted into a
 * league table looks exactly like a twelve-game one, and the only thing that can tell
 * them apart is the denominator — which is why `covered` is carried per column and why
 * `cellFor` returns it rather than just a number.
 */

/**
 * Below this many covered games a figure is shown but marked.
 *
 * FOUR is the point at which one blow-out stops reading as an outlier and starts being
 * the average: a 30-shot game inside a four-game sample moves it by seven and a half.
 */
export const THIN = 4;

export const SPLITS = [
  { v: "overall", label: "All" },
  { v: "home", label: "Home" },
  { v: "away", label: "Away" },
];

/**
 * How much recent history each view uses.
 *
 * A SEASON AVERAGE CANNOT TELL A SIDE THAT HAS STARTED winning eight a game from one
 * that has been winning eight all year and has just stopped. Both read the same, and
 * only one of them is a reason to back anything.
 *
 * The window is applied INSIDE the venue on the server, so "last 5, home" is the five
 * most recent games played at home — not whichever of the last five overall happened
 * to be at home, which would hand a side returning from a long away trip a one-game
 * "last five".
 */
export const WINDOWS = [
  { v: "all", label: "Season" },
  { v: "10", label: "Last 10" },
  { v: "5", label: "Last 5" },
];

export const isWindow = (v) => WINDOWS.some((w) => w.v === v);

/** `shot` marks the columns whose denominator is coverage rather than games played. */
export const COLS = [
  { v: "corners_won", short: "CW", title: "Corners won per game" },
  { v: "corners_conceded", short: "CA", title: "Corners conceded per game" },
  { v: "shots", short: "Sh", title: "Shots taken per game", shot: true },
  { v: "shots_on_target", short: "SoT", title: "Shots on target per game", shot: true },
];

export const isSplit = (v) => SPLITS.some((s) => s.v === v);
export const isCol = (v) => COLS.some((c) => c.v === v);

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** One team's numbers for one venue and window, or an empty row rather than a throw. */
export const splitOf = (team, split, window = "all") =>
  (team && team.splits && team.splits[split] && team.splits[split][window]) || {};

/**
 * Highest first — in three tiers: well evidenced, thin, then absent.
 *
 * A TEAM WITH NOTHING IN THIS COLUMN SINKS, it does not lead. Treating a missing figure
 * as zero would put every side the provider has no shot data for at the bottom of a
 * shots table, which is defensible, and at the TOP of a conceded table, which is not —
 * so it is sorted as absent in both rather than as a number in either.
 *
 * AND A THIN FIGURE SINKS BELOW A WELL-EVIDENCED ONE, which is the part that is easy to
 * get wrong and was got wrong here first. Dimming a thin cell is not enough, because
 * watchlist.py already paid for this lesson and press_board.py quotes it:
 *
 *     "a five-game average is EXTREME by construction, so thin rows do not merely appear
 *      in the ranking, they lead it."
 *
 * A side with one covered game of thirty shots tops a shots table over a side averaging
 * eighteen across twelve, and the row that leads a table is the one people read. Ranking
 * the thin ones underneath keeps them visible — they are still real games — without
 * letting a sample size masquerade as a finding. Within a tier it is still just the
 * number, descending.
 */
export function rankTeams(teams = [], split = "overall", col = "corners_won",
                          window = "all") {
  const spec = COLS.find((c) => c.v === col) || { v: col };
  const tier = (t) => {
    const cell = cellFor(splitOf(t, split, window), spec);
    if (cell.missing) return 2;
    return cell.thin ? 1 : 0;
  };
  return [...(teams || [])].sort((a, b) => {
    const ta = tier(a);
    const tb = tier(b);
    if (ta !== tb) return ta - tb;
    return (num(splitOf(b, split, window)[col]) || 0)
         - (num(splitOf(a, split, window)[col]) || 0);
  });
}

/**
 * What to render in one cell: the figure, what it is built on, and whether to say so.
 *
 * `missing` AND A ZERO ARE DIFFERENT CLAIMS. "Not recorded" and "none taken" look the
 * same once a gap has been filled with 0, and only one of them is true — so a column
 * with no coverage comes back missing and the component draws a dash.
 */
export function cellFor(row = {}, col = { v: "corners_won" }) {
  const value = num(row[col.v]);
  const covered = col.shot
    ? Number((row.covered || {})[col.v] || 0)
    : Number(row.games || 0);
  if (value === null) return { missing: true, value: null, covered, thin: false };
  return { missing: false, value, covered, thin: covered < THIN };
}

/**
 * The biggest WELL-EVIDENCED value in the ranked column, for scaling the bar behind each
 * team name.
 *
 * SCALED ON WHAT YOU SORTED BY, so the bar always means "how this row compares on the
 * column you are reading" rather than silently staying about corners while you read a
 * shots table.
 *
 * AND THIN ROWS DO NOT SET THE SCALE, which is the same argument as rankTeams' and was
 * missed there first. A side with one covered game of thirty shots is ranked below the
 * leaders — and if it still sets the maximum, it gets the longest bar on the table while
 * sitting fourth, so the picture contradicts the order. Its own bar is clamped at full
 * width by barWidth rather than allowed to overflow its cell.
 *
 * Falls back to every value when nothing in the column is well covered, so an all-thin
 * column still draws bars instead of flat-lining; at least 1, so nothing divides by zero.
 */
export function maxOf(teams = [], split = "overall", col = "corners_won",
                      window = "all") {
  const spec = COLS.find((c) => c.v === col) || { v: col };
  const cells = (teams || []).map((t) => cellFor(splitOf(t, split, window), spec));
  const solid = cells.filter((c) => !c.missing && !c.thin).map((c) => c.value);
  const any = cells.filter((c) => !c.missing).map((c) => c.value);
  return Math.max(1, ...(solid.length ? solid : any));
}

/** A value's share of that scale, 0 to 1. Clamped, since a thin figure can exceed it. */
export function barWidth(value, max) {
  const v = num(value);
  if (v === null || !(max > 0)) return 0;
  return Math.max(0, Math.min(1, v / max));
}

/**
 * The bar to draw behind one team name: a share of the scale, or nothing.
 *
 * A THIN ROW GETS NO BAR. Clamping its width was the first attempt and it still left a
 * side ranked fourth with the longest bar on the table, because clamped means full. The
 * bar is the at-a-glance version of the ranking, so a bar that disagrees with the order
 * is worse than no bar — and the figure, its bracketed game count and the note under the
 * table all remain, so nothing is hidden. Scale and order now say the same thing.
 */
export function barFor(row = {}, col = { v: "corners_won" }, max = 1) {
  const cell = cellFor(row, col);
  if (cell.missing || cell.thin) return 0;
  return barWidth(cell.value, max);
}
