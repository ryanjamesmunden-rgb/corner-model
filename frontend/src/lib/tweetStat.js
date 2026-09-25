// The daily X post: one statistic about the whole board, not a list of rows.
//
// WHY THIS SHAPE. Every other share here hands over rows — four streaks, a card, a menu.
// Rows are what a MEMBER wants; they are the product. A public post has a different job:
// it has to be interesting to somebody who has never heard of the site, in one screen,
// without giving away the thing people pay for. So this leads on a number about the board
// as a whole and sends the reader to the page for the names:
//
//   23 teams playing in the next 3 days have won 4+ corners in each of their last 5.
//   They span 9 countries. Between them that is 168 straight clears, the longest 18.
//
// The names are the paid half and they stay on the site. That is not coyness — a list of
// twenty teams is also a worse post, because nobody reads twenty rows on a timeline.
//
// EVERY CLAIM IS BACKWARD-LOOKING, AND THE WORDING HAS TO KEEP IT THAT WAY. "have won" is
// a fact about matches already played. "will win", "are due", "good bets" are predictions,
// and this is a public post carrying no price, no stake and no qualification — so it says
// only what happened. A streak is the weakest reading of a team on its own (five clears
// can be five coin flips, and measure_chase_board could not separate four orderings from a
// shuffled control), which is exactly why the post states the run and stops there.
//
// NO TEAM IS NAMED, INCLUDING THE BEST ONE. "The longest is 18 in a row" is the hook;
// "Plymouth are 18 in a row" is the answer, and the answer is what the link is for.
//
// THE COUNT IS THE HEADLINE AND IT MUST BE HONEST. It counts rows that clear the stated
// bar, in the stated window, and nothing else — so a quiet day produces a small number or
// no post at all rather than a loosened threshold that keeps the number up.
import { countryCodeFor } from "./countryFlag.js";
import { fitToPost, weightedLength } from "./xLimit.js";

/** The bar the post claims. Kept at the finder's, so the two cannot describe different boards. */
export const STAT_MIN_LINE = 4;
export const STAT_MIN_RUN = 5;
/** Below this the number is not a story — a post saying "3 teams" advertises a quiet board. */
export const STAT_MIN_TEAMS = 6;
export const STAT_DAYS = 3;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const runOf = (r) => num(r?.streak?.length) || 0;

/**
 * Rows the post is allowed to count.
 *
 * THE SAME FILTER THE FINDER USES, deliberately. If the tweet counted rows the channel
 * post excludes, somebody clicking through from the timeline would find a shorter list
 * than the number that brought them, and the first thing they would learn about this site
 * is that its numbers do not tie up.
 */
export const counted = (rows = [], minLine = STAT_MIN_LINE, minRun = STAT_MIN_RUN) =>
  rows.filter((r) => (r.direction || "over") === "over"
    && num(r.line) !== null && num(r.line) >= minLine
    && runOf(r) >= minRun
    && !!r.next_fixture?.date);

/**
 * The facts, separated from the sentence that carries them.
 *
 * Split out so the numbers can be tested without asserting on prose, and so a later
 * rewording cannot quietly change what is being claimed.
 */
export const statsFrom = (rows = [], opts = {}) => {
  const minLine = opts.minLine ?? STAT_MIN_LINE;
  const minRun = opts.minRun ?? STAT_MIN_RUN;
  const picked = counted(rows, minLine, minRun);
  if (!picked.length) return null;

  const runs = picked.map(runOf).sort((a, b) => b - a);
  // Countries, not leagues: two English divisions are one country, and "9 countries"
  // is the claim a reader can check at a glance. A cup has no country code — see
  // countryCodeFor — so it is counted as its own competition rather than guessed at.
  const codes = new Set();
  for (const r of picked) {
    const code = countryCodeFor(r.league_id);
    codes.add(code || `cup:${r.league_id}`);
  }
  return {
    teams: picked.length,
    countries: codes.size,
    // The total is "between them" — the sum of the runs, which is what it says it is.
    clears: runs.reduce((a, b) => a + b, 0),
    longest: runs[0],
    second: runs.length > 1 ? runs[1] : null,
    minLine,
    minRun,
  };
};

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/**
 * The post, at the largest size X will actually accept.
 *
 * BUILT IN SENTENCES AND DROPPED FROM THE END, because they are in descending order of
 * interest: the count is the post, the spread is context, the longest run is a flourish.
 * fitToPost drops from the tail, so what survives a long day is the part that matters.
 * The weighted count is X's, not JavaScript's — see xLimit.js.
 */
export const tweetStat = ({ rows = [], days = STAT_DAYS, site = "",
                            minTeams = STAT_MIN_TEAMS, ...opts } = {}) => {
  const s = statsFrom(rows, opts);
  // A QUIET BOARD GETS NO POST. Dropping the bar to keep the number up is how a daily
  // statistic stops meaning anything, and the account that does it teaches people to
  // scroll past. Returning nothing lets the caller say "quiet day" instead.
  if (!s || s.teams < minTeams) return { text: "", stats: s };

  const when = days === 1 ? "today" : `in the next ${days} days`;
  const sentences = [
    `${plural(s.teams, "team", "teams")} playing ${when} have won ${s.minLine}+ corners `
    + `in each of their last ${s.minRun} or more.`,
    s.countries > 1 ? `They span ${plural(s.countries, "country", "countries")}.` : "",
    `Between them that is ${s.clears} straight clears.`,
    s.longest >= s.minRun * 2
      ? `The longest run is ${s.longest}${s.second ? `, then ${s.second}` : ""}.`
      : "",
  ].filter(Boolean);

  const where = String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
  const text = fitToPost((n) => {
    const body = sentences.slice(0, n).join(" ");
    return where ? `${body}\n\n${where}/streaks` : body;
  }, sentences.length);

  return { text, stats: s, weight: weightedLength(text) };
};
