// SEVERAL statistics a day, not one.
//
// WHY THIS EXISTS. tweetStat builds one post about the streak board, and one post a day off
// one board is a thin account: the same sentence with a different number in it, which is
// what people learn to scroll past. This builds a SET of candidates from the boards the
// site already computes, and the daily job sends all of them with a Post button each — so
// the choice of what goes out stays with a person, and a quiet board costs a candidate
// rather than the day.
//
// EVERY ONE OBEYS THE SAME RULES AS tweetStat, because they go to the same account:
//
//   - BACKWARD-LOOKING ONLY. "have won", "average", "concede" are facts about matches
//     already played. "will", "are due", "value", "banker" are tips, and this account
//     carries no price, no stake and no qualification.
//   - NOBODY IS NAMED. The names are the paid half and the reason to click through. A post
//     that answers its own hook has given the product away.
//   - A CANDIDATE THAT CANNOT CLEAR ITS OWN BAR IS DROPPED, never loosened. Each one states
//     a threshold and counts what clears it; the day a threshold has to move to keep the
//     number up is the day the number stopped meaning anything. A quiet board yields fewer
//     candidates, and no candidates yields no post.
//   - 280 BY X'S WEIGHTING, with the link counted at URL_WEIGHT. See xLimit.js.
//
// THEY ARE DELIBERATELY NOT RANKED BY HOW GOOD A BET ANYTHING IS, because none of them is
// about a bet. The order is how surprising the number is likely to be to somebody who has
// never seen the site, which is an editorial guess and is labelled as one.
//
// AND THEY MUST NOT ALL BE THE SAME POST. Two candidates that differ only in a threshold
// are one candidate and a rounding error, so `dedupe` drops a later one whose headline
// count matches an earlier one's — otherwise a board where every run is long produces
// "20 teams..." and "20 of them are on 10 or more", which reads as padding.
import { countryCodeFor } from "./countryFlag.js";
import { fitToPost, xWeight } from "./xLimit.js";
import { STAT_DAYS, STAT_MIN_LINE, STAT_MIN_RUN, STAT_MIN_TEAMS, counted, statsFrom }
  from "./tweetStat.js";

export { STAT_DAYS, STAT_MIN_LINE, STAT_MIN_RUN, STAT_MIN_TEAMS };

/** A long run, for the candidate that is about long runs. Double the ordinary bar. */
export const DEEP_RUN = STAT_MIN_RUN * 2;
/** A high line, for the candidate that is about high lines. One above the ordinary bar. */
export const HIGH_LINE = STAT_MIN_LINE + 1;
/** Both sides of a mismatch have to be at least this, in corners per game. */
export const MISMATCH_BAR = 6.0;
/** Below this a count is not a story, whatever it is counting. */
export const MIN_SUBJECTS = 4;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const runOf = (r) => num(r?.streak?.length) || 0;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const host = (site) => String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");

/** The London calendar day of a kick-off, as YYYY-MM-DD. Same zone as every other post. */
export const ukDay = (iso, tz = "Europe/London") => {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  try {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit",
    }).format(d);
  } catch {
    return null;
  }
};

/**
 * Wrap a body and a link at X's real limit.
 *
 * Sentences are dropped from the END because every candidate below is written in
 * descending order of interest: the count is the post, the rest is context.
 */
const build = (sentences, site, path) => {
  const where = host(site);
  const body = sentences.filter(Boolean);
  if (!body.length) return "";
  // appendUrl: false — the link is IN the text below, so xWeight charges it once at its
  // flat t.co cost. Leaving the default on would reserve room for a second copy and drop a
  // sentence that fitted.
  return fitToPost((n) => {
    const text = body.slice(0, n).join(" ");
    return where ? `${text}\n\n${where}${path}` : text;
  }, body.length, { appendUrl: false });
};

const candidate = (key, text, stats) =>
  (text ? { key, text, stats, weight: xWeight(text) } : null);


// --------------------------------------------------------------------------
// The candidates
// --------------------------------------------------------------------------

/** The board as a whole — the post tweetStat already wrote, kept as the lead candidate. */
export const breadthStat = ({ rows = [], days = STAT_DAYS, site = "",
                              minTeams = STAT_MIN_TEAMS } = {}) => {
  const s = statsFrom(rows);
  if (!s || s.teams < minTeams) return null;
  const when = days === 1 ? "today" : `in the next ${days} days`;
  return candidate("breadth", build([
    `${plural(s.teams, "team", "teams")} playing ${when} have won ${s.minLine}+ corners `
    + `in each of their last ${s.minRun} or more.`,
    s.countries > 1 ? `They span ${plural(s.countries, "country", "countries")}.` : "",
    `Between them that is ${s.clears} straight clears.`,
    s.longest >= s.minRun * 2
      ? `The longest run is ${s.longest}${s.second ? `, then ${s.second}` : ""}.`
      : "",
  ], site, "/streaks"), s);
};

/**
 * The deep end of the same board.
 *
 * A DIFFERENT CLAIM, not a re-cut of the first. "20 teams are on 5 or more" and "7 of them
 * are on 10 or more" answer different questions — the second is about how far out the tail
 * goes, which is the part a reader has no intuition for.
 */
export const deepRunStat = ({ rows = [], days = STAT_DAYS, site = "",
                              deep = DEEP_RUN, minSubjects = MIN_SUBJECTS } = {}) => {
  const picked = counted(rows);
  const deepOnes = picked.filter((r) => runOf(r) >= deep);
  if (deepOnes.length < minSubjects) return null;
  const runs = deepOnes.map(runOf).sort((a, b) => b - a);
  const when = days === 1 ? "today" : `in the next ${days} days`;
  const stats = { teams: deepOnes.length, of: picked.length, deep,
                  longest: runs[0], clears: runs.reduce((a, b) => a + b, 0) };
  return candidate("deep", build([
    `${plural(deepOnes.length, "team", "teams")} playing ${when} have won `
    + `${STAT_MIN_LINE}+ corners in each of their last ${deep} games or more.`,
    `That is ${stats.clears} consecutive clears between them, and not one of them has `
    + `missed since.`,
    `The longest is ${stats.longest} in a row.`,
  ], site, "/streaks"), stats);
};

/**
 * The same board read at a higher line.
 *
 * 4+ is the bar the channel post uses, and it is a low bar by design. How many clear FIVE
 * every week is the number that says whether the board is unusual or ordinary, and it is
 * not derivable from the headline.
 */
export const highLineStat = ({ rows = [], days = STAT_DAYS, site = "",
                               line = HIGH_LINE, minSubjects = MIN_SUBJECTS } = {}) => {
  const picked = counted(rows, line, STAT_MIN_RUN);
  if (picked.length < minSubjects) return null;
  const all = counted(rows);
  const runs = picked.map(runOf).sort((a, b) => b - a);
  const codes = new Set();
  for (const r of picked) codes.add(countryCodeFor(r.league_id) || `cup:${r.league_id}`);
  const when = days === 1 ? "today" : `in the next ${days} days`;
  const stats = { teams: picked.length, of: all.length, line,
                  countries: codes.size, longest: runs[0] };
  return candidate("high", build([
    `${plural(picked.length, "team", "teams")} playing ${when} have won ${line}+ corners `
    + `in each of their last ${STAT_MIN_RUN} or more.`,
    // The denominator is what makes the number readable: 6 of 20 and 6 of 200 are
    // different boards and the same headline.
    all.length > picked.length
      ? `That is ${picked.length} of the ${all.length} on ${STAT_MIN_LINE}+.`
      : "",
    stats.longest >= STAT_MIN_RUN * 2 ? `The longest is ${stats.longest} in a row.` : "",
  ], site, "/streaks"), stats);
};

/**
 * Today only.
 *
 * The board is a three-day window and a timeline is read now. "Playing today" is the same
 * data with the one filter a reader on a Saturday morning actually wants.
 *
 * Suppressed when the window IS today, because then it is the breadth post word for word.
 */
export const todayStat = ({ rows = [], days = STAT_DAYS, site = "", now = new Date(),
                            minSubjects = MIN_SUBJECTS } = {}) => {
  if (days <= 1) return null;
  const today = ukDay(now instanceof Date ? now.toISOString() : now);
  if (!today) return null;
  const picked = counted(rows).filter((r) => ukDay(r.next_fixture?.date) === today);
  if (picked.length < minSubjects) return null;
  const runs = picked.map(runOf).sort((a, b) => b - a);
  const codes = new Set();
  for (const r of picked) codes.add(countryCodeFor(r.league_id) || `cup:${r.league_id}`);
  const stats = { teams: picked.length, countries: codes.size, longest: runs[0],
                  clears: runs.reduce((a, b) => a + b, 0) };
  return candidate("today", build([
    `${plural(picked.length, "team", "teams")} playing today have won ${STAT_MIN_LINE}+ `
    + `corners in each of their last ${STAT_MIN_RUN} or more.`,
    stats.countries > 1 ? `Across ${plural(stats.countries, "country", "countries")}.` : "",
    `The longest run is ${stats.longest}.`,
  ], site, "/streaks"), stats);
};

/**
 * The other board: what a side wins against what its opponent concedes.
 *
 * TWO RECORDED AVERAGES, AND THAT IS ALL IT CLAIMS. Both numbers are venue-split season
 * averages over games already played, so the sentence is a fact about the past exactly
 * like the streak ones. It deliberately does NOT say the total is likely to be high, which
 * is the model's opinion and belongs behind the link.
 */
export const mismatchStat = ({ mismatches = [], days = STAT_DAYS, site = "",
                               bar = MISMATCH_BAR, minSubjects = MIN_SUBJECTS } = {}) => {
  const picked = (mismatches || []).filter((m) =>
    num(m?.team_for) !== null && num(m.team_for) >= bar
    && num(m?.opp_conceded) !== null && num(m.opp_conceded) >= bar
    && !!m?.next_fixture?.date);
  if (picked.length < minSubjects) return null;
  const codes = new Set();
  for (const m of picked) codes.add(countryCodeFor(m.league_id) || `cup:${m.league_id}`);
  const best = picked.reduce((a, b) =>
    (num(b.opp_conceded) > num(a.opp_conceded) ? b : a));
  const when = days === 1 ? "today" : `in the next ${days} days`;
  const stats = { teams: picked.length, countries: codes.size,
                  bar, mostLeaked: Number(num(best.opp_conceded).toFixed(1)) };
  return candidate("mismatch", build([
    `${plural(picked.length, "side", "sides")} playing ${when} average ${bar}+ corners a `
    + `game, against opponents who concede ${bar}+.`,
    stats.countries > 1 ? `In ${plural(stats.countries, "country", "countries")}.` : "",
    `The leakiest of those opponents has shipped ${stats.mostLeaked} a game.`,
  ], site, "/streaks"), stats);
};


// --------------------------------------------------------------------------
// The set
// --------------------------------------------------------------------------

/** In the order they are offered. Lead with the widest claim; the rest narrow it. */
export const BUILDERS = [
  ["breadth", breadthStat],
  ["today", todayStat],
  ["deep", deepRunStat],
  ["high", highLineStat],
  ["mismatch", mismatchStat],
];

/**
 * Drop a candidate whose headline count repeats one already offered.
 *
 * Two posts that differ only in a threshold are one post and a rounding error. On a board
 * where every run happens to be long, "20 teams on 5+" and "20 of them on 10+" are the
 * same sentence twice and read as padding.
 */
export const dedupe = (cands) => {
  const seen = new Set();
  return cands.filter((c) => {
    const k = `${c.stats?.teams}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
};

/**
 * Every statistic worth posting today, best first.
 *
 * Returns [] on a quiet board rather than a loosened one — the caller reports a quiet day,
 * which is a true thing to say and costs nothing.
 */
export const tweetStats = ({ rows = [], mismatches = [], days = STAT_DAYS, site = "",
                             now = new Date(), limit = 5, ...opts } = {}) => {
  const built = BUILDERS
    .map(([, fn]) => fn({ rows, mismatches, days, site, now, ...opts }))
    .filter(Boolean);
  return dedupe(built).slice(0, Math.max(1, limit));
};
