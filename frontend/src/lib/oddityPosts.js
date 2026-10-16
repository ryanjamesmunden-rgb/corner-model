// The daily post, written eleven different ways instead of one way with the number moved.
//
// WHAT WAS WRONG. tweetStats offered five candidates and four of them were this sentence:
//
//   N teams playing in the next 3 days have won 4+ corners in each of their last 5 or more.
//
// breadth, today, deep and high differ by a threshold. They are not four angles, they are
// one angle at four settings, and an account that posts the same sentence every morning
// gets scrolled past however true the number is. "Generic tweets with no variance" was the
// complaint and it was a fair reading of the output.
//
// A THRESHOLD IS NOT AN ANGLE. Each builder below answers a DIFFERENT QUESTION — one
// match, a season-long floor, a ceiling nobody has cleared, a venue split, one league
// against another, a side that wins corners and scores nothing. Two of them cannot read as
// each other because they are not about the same kind of thing, which is the only
// definition of variance that survives contact with a reader.
//
// THE CLUBS ARE THE HOOK AND THEY ARE NAMED HERE. This site holds 28 competitions across
// 20 countries — the Premier League and League Two sit in the same table as Japan, Brazil
// and Argentina. "A League Two side wins more corners than anyone in Serie A" is
// interesting BECAUSE of who it names, and no other site is in a position to say it.
//
// THE OLD RULE SAID NOBODY IS NAMED, and it is being kept where it applies and dropped
// where it does not. It protects the BOARD — who to back on Saturday is the product, and a
// post that answers its own hook has given it away. None of these is a selection. They are
// records of matches already played, and a record of what Vejle did in August sells
// nothing. See the forward-looking guard below for where that line is enforced.
//
// FOUR RULES, INHERITED FROM tweetStat AND NOT RELAXED:
//
//   - BACKWARD-LOOKING ONLY. "have won", "concede", "has not" are facts. "will", "are
//     due", "value", "banker" are tips, and this account carries no price, no stake and no
//     qualification. FORWARD_WORDS below is asserted against every candidate in the tests.
//   - EVERY SUPERLATIVE IS BOUNDED TO THIS SITE. "The widest split in Europe" is a claim
//     about leagues we do not hold. "The widest of the 548 teams here" is true, checkable,
//     and a better hook for exactly that reason.
//   - EVERY CLAIM CARRIES ITS DENOMINATOR. A floor of 6 over 20 games is remarkable; over
//     three it is a Tuesday.
//   - 280 BY X'S WEIGHTING, with the link charged once at its flat t.co cost. See xLimit.
//
// A MISSING FINDING IS DROPPED, NEVER SOFTENED. Early in a season almost nothing clears
// the sample bar, and the honest output then is fewer posts rather than the same posts
// with a lower bar — the rule the whole of tweetStat was built on and the one that makes
// any of these numbers worth reading.
import { fitToPost, xWeight } from "./xLimit.js";

/** Words that would turn a record into a tip. Asserted against every candidate. */
export const FORWARD_WORDS = [
  "will", "due", "expect", "value", "banker", "back them", "tip", "bet",
  "should", "likely", "chance", "odds", "price", "nap", "lock",
];

/**
 * A number, or null — and null, "" and undefined are NOT numbers.
 *
 * `Number(null)` is 0 and `Number("")` is 0, both finite, so the obvious one-liner turns
 * a missing measurement into a real zero. digest.js shipped that bug and printed "Reading
 * 0.0 at home" for a team whose average had not been computed; here it produced "Nobody
 * concede 0.0 corners a game, more than any team on the site", which is a published
 * falsehood with a club's name attached to it. A genuine 0 still passes — the away side
 * of a 16-0 corner count is a real measurement and has to survive.
 */
const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** One decimal, with the trailing ".0" kept — "8.0 corners" reads as a measurement. */
const dec = (v) => {
  const n = num(v);
  return n === null ? null : n.toFixed(1);
};

const host = (site) => String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");

/**
 * "Vejle (Denmark)" — who they are, for a reader who has never heard of them.
 *
 * ACROSS 28 LEAGUES THAT IS MOST READERS FOR MOST CLUBS, which is the thing that makes
 * this site's data unusual and also the thing that makes a bare club name useless. The
 * country goes in the bracket rather than the league, because "Denmark" places a club for
 * anybody and "Superliga" places it only for someone who already knew.
 */
export const who = (f) => {
  const name = String(f?.team || "").trim();
  if (!name) return "";
  const where = String(f?.country || "").trim();
  return where ? `${name} (${where})` : name;
};

/**
 * "a" or "an", for a league name dropped into a sentence.
 *
 * The first real run printed "A Eerste Divisie side", which is the kind of thing a reader
 * notices before they notice the statistic. A vowel-letter test is not a vowel-SOUND test
 * and never will be — it would say "an Union" and "a hour" given the chance — but every
 * competition in this database is a name, not a word, and across the 28 of them the
 * letter and the sound agree: Eerste, Eredivisie, A-League and Eliteserien all take "an",
 * Championship and Serie A take "a". Revisit it if a league called Uefa-something ever
 * lands here.
 */
export const article = (word) =>
  (/^[aeiou]/i.test(String(word || "").trim()) ? "An" : "A");

/** "14 September" — a date a reader can picture, with no year on a current season. */
export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/London", day: "numeric", month: "long",
    }).format(d);
  } catch {
    return "";
  }
};

/**
 * Wrap a body and a link at X's real limit.
 *
 * Sentences drop from the END, so every builder below is written with its claim first and
 * its context after — what survives a long club name is the part that matters.
 */
const build = (sentences, site, path = "") => {
  const where = host(site);
  const body = sentences.filter(Boolean).map((s) => String(s).trim()).filter(Boolean);
  if (!body.length) return "";
  // appendUrl: false — the link is IN the text, so xWeight charges it once at 23 rather
  // than reserving room for a second copy and dropping a sentence that fitted.
  return fitToPost((n) => {
    const text = body.slice(0, n).join(" ");
    return where ? `${text}\n\n${where}${path}` : text;
  }, body.length, { appendUrl: false });
};

const candidate = (key, text, facts) =>
  (text ? { key, text, facts, weight: xWeight(text) } : null);

/**
 * "the 548 teams here" — the bound every superlative needs. See rule 2.
 *
 * A NOUN PHRASE, NOT A CLAUSE, because the builders need it in several grammatical
 * positions and a fixed clause produced "more than any team of the 548 teams on the
 * site" when one of them already had a noun in front of it. Each sentence supplies its
 * own preposition.
 */
const thePool = (pool) => {
  const n = num(pool?.teams);
  return n ? `the ${n} teams here` : "every team here";
};


// ---------------------------------------------------------------------------
// One match
// ---------------------------------------------------------------------------

/** A siege. The margin is the story, not the count. */
export const routPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.biggest_rout;
  if (!f || num(f.corners_for) === null) return null;
  const margin = num(f.margin);
  if (margin === null || margin < 8) return null;   // below this it is just a good night
  const games = num(pool?.games);
  return candidate("rout", build([
    `${who(f)} won ${f.corners_for} corners to ${f.corners_against} against `
    + `${f.opponent}${when(f.date) ? ` on ${when(f.date)}` : ""}.`,
    `A margin of ${margin}.`,
    games ? `Across the ${games.toLocaleString("en-GB")} games on record here, nothing `
      + `else is close.` : "",
  ], site), f);
};

/** The biggest single haul, measured against what a normal night looks like. */
export const haulPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.biggest_haul;
  if (!f || num(f.corners_for) === null) return null;
  const games = num(pool?.games);
  return candidate("haul", build([
    `The most corners any side here has won in one game is ${f.corners_for}.`,
    `${who(f)} did it against ${f.opponent}${when(f.date) ? ` on ${when(f.date)}` : ""}, `
    + `and still only managed ${f.goals_for ?? 0} goal${f.goals_for === 1 ? "" : "s"}.`,
    games ? `${games.toLocaleString("en-GB")} games on record.` : "",
  ], site), f);
};

/** The busiest 90 minutes on the site. Both ends, because both teams earned it. */
export const wildestPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.wildest_game;
  if (!f || num(f.total) === null) return null;
  const games = num(pool?.games);
  return candidate("wildest", build([
    `${f.total} corners in one match.`,
    `${who(f)} ${f.corners_for}, ${f.opponent} ${f.corners_against}`
    + `${when(f.date) ? `, on ${when(f.date)}` : ""}.`,
    games ? `The busiest of ${games.toLocaleString("en-GB")} games on record here.` : "",
  ], site), f);
};


// ---------------------------------------------------------------------------
// A whole season
// ---------------------------------------------------------------------------

/**
 * The best WORST game on the site.
 *
 * "NOT THEIR AVERAGE — THEIR WORST" IS IN THE POST ON PURPOSE. It is the one claim here a
 * reader reliably misreads as an average, and the correction costs eight words.
 */
export const floorPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.highest_floor;
  if (!f || num(f.floor) === null || num(f.games) === null) return null;
  return candidate("floor", build([
    `${who(f)} have played ${f.games} games on record and their worst return is `
    + `${f.floor} corners.`,
    `Not their average — their worst.`,
    `Nobody among ${thePool(pool)} has a higher floor.`,
  ], site), f);
};

/** The opposite, and the one nobody expects to exist. */
export const ceilingPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.lowest_ceiling;
  if (!f || num(f.ceiling) === null || num(f.games) === null) return null;
  return candidate("ceiling", build([
    `${who(f)} have not won more than ${f.ceiling} corners in a game.`,
    `Not once in ${f.games}.`,
    `Their best night on record is a number most sides clear by half-time.`,
  ], site), f);
};

/** Home and away, by the same eleven players. */
export const venuePost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.widest_venue_gap;
  if (!f || num(f.gap) === null) return null;
  const home = dec(f.home_avg);
  const away = dec(f.away_avg);
  if (home === null || away === null) return null;
  return candidate("venue", build([
    `${who(f)} win ${home} corners a game at home and ${away} away.`,
    `A gap of ${dec(f.gap)}, ${f.stronger === "away" ? "the wrong way round, " : ""}`
    + `and the widest among ${thePool(pool)}.`,
    `Same eleven players.`,
  ], site), f);
};

/** Not one off night in the whole record. */
export const perfectPost = ({ findings = {}, site = "" } = {}) => {
  const f = findings.never_outcornered;
  if (!f || num(f.games) === null) return null;
  return candidate("perfect", build([
    `${who(f)} have finished with more corners than their opponent in every game on `
    + `record.`,
    `All ${f.games} of them.`,
    `Not one drawn count, not one off night — ${dec(f.for_avg)} a game against `
    + `${dec(f.against_avg)}.`,
  ], site), f);
};

/** Plenty of corners, nothing to show for it. */
export const futilityPost = ({ findings = {}, site = "" } = {}) => {
  const f = findings.all_corners_no_goals;
  if (!f || num(f.for_avg) === null || num(f.goals_avg) === null) return null;
  const games = num(f.games);
  return candidate("futility", build([
    `${who(f)} are among the biggest corner-winners on this site and do the least with `
    + `them: ${dec(f.for_avg)} corners a game, ${dec(f.goals_avg)} goals.`,
    games === null ? "" : `Over ${games} games that is `
      + `${Math.round(num(f.for_avg) * games)} corners and `
      + `${Math.round(num(f.goals_avg) * games)} goals.`,
  ], site), f);
};

/** The other end of the pitch. */
export const leakyPost = ({ findings = {}, pool = {}, site = "" } = {}) => {
  const f = findings.leakiest;
  if (!f || num(f.against_avg) === null) return null;
  const games = num(f.games);
  const total = games === null ? null : Math.round(num(f.against_avg) * games);
  const mine = dec(f.for_avg);
  return candidate("leaky", build([
    `${who(f)} concede ${dec(f.against_avg)} corners a game.`,
    `No side among ${thePool(pool)} concedes more.`,
    total === null ? "" : `${total} defended in ${games} games.`,
    mine === null ? "" : `They win ${mine} themselves.`,
  ], site), f);
};


// ---------------------------------------------------------------------------
// A league against another league
// ---------------------------------------------------------------------------

/** Two professional leagues, the same sport, three corners apart. */
export const leaguesPost = ({ findings = {}, site = "" } = {}) => {
  const f = findings.league_extremes;
  if (!f?.top || !f?.bottom) return null;
  const topName = f.top.country ? `${f.top.country}'s ${f.top.league}` : f.top.league;
  const lowName = f.bottom.country ? `${f.bottom.country}'s ${f.bottom.league}` : f.bottom.league;
  return candidate("leagues", build([
    `${topName} averages ${dec(f.top.per_match)} corners a match.`,
    `${lowName} averages ${dec(f.bottom.per_match)}.`,
    `Same sport, ${dec(f.gap)} corners apart, across the ${f.leagues} competitions here.`,
  ], site), f);
};

/**
 * The best hook here, and the one only this site can make.
 *
 * Nowhere else is a fourth-tier club's corner record sitting in the same table as Serie
 * A's. It reads as a joke until the numbers are attached, which is exactly the shape of
 * thing that gets argued with — and an argument is a better outcome than a scroll.
 */
export const punchingPost = ({ findings = {}, site = "" } = {}) => {
  const f = findings.punching_up;
  if (!f?.team || !f?.beats) return null;
  const t = f.team;
  const b = f.beats;
  if (num(t.for_avg) === null || num(b.for_avg) === null) return null;
  const tier = t.league ? `${article(t.league)} ${t.league} side` : "A lower-division side";
  const games = num(t.games);
  return candidate("punching", build([
    `${tier} wins more corners than anyone in ${b.league}.`,
    `${who(t)} average ${dec(t.for_avg)} a game${games === null ? "" : ` across ${games} games`}; `
    + `${b.league}'s busiest, ${b.team}, average ${dec(b.for_avg)}.`,
    f.beaten_leagues > 1
      ? `They would top ${f.beaten_leagues} of the ${f.of_top_flights} top flights here.`
      : "",
  ], site), f);
};


// ---------------------------------------------------------------------------
// The set
// ---------------------------------------------------------------------------

/**
 * In their default order, best hook first.
 *
 * THE ORDER IS AN EDITORIAL GUESS AND IS LABELLED AS ONE — it is how surprising each is
 * likely to be to somebody who has never seen the site, not how good a bet anything is,
 * because none of them is about a bet. `rotate` moves the lead day by day so the guess
 * does not harden into the same post every morning.
 */
export const BUILDERS = [
  ["punching", punchingPost],
  ["rout", routPost],
  ["floor", floorPost],
  ["leagues", leaguesPost],
  ["ceiling", ceilingPost],
  ["venue", venuePost],
  ["perfect", perfectPost],
  ["wildest", wildestPost],
  ["futility", futilityPost],
  ["haul", haulPost],
  ["leaky", leakyPost],
];

/**
 * Move the lead on by one a day, keeping the rest of the order.
 *
 * WHY A ROTATION AND NOT A SHUFFLE. A random pick cannot be tested, cannot be reproduced
 * when somebody asks why Tuesday's post was odd, and can hand out the same lead three days
 * running by chance — which is the complaint this file exists to answer. A cycle visits
 * every candidate before repeating any, which is what "variance" has to mean for something
 * that posts daily.
 *
 * KEYED ON THE DATE, NOT ON A COUNTER, so two runs on the same day agree and a missed day
 * does not shift the cycle out of step with itself.
 */
export const dayIndex = (now = new Date()) => {
  const d = now instanceof Date ? now : new Date(now);
  if (Number.isNaN(d.getTime())) return 0;
  return Math.floor(d.getTime() / 86400000);
};

export const rotate = (list, index = 0) => {
  if (!Array.isArray(list) || list.length < 2) return [...(list || [])];
  const n = ((Math.trunc(index) % list.length) + list.length) % list.length;
  return [...list.slice(n), ...list.slice(0, n)];
};

/** The club a candidate is about, for the one-club-a-day rule below. */
const subjectOf = (c) => {
  const f = c?.facts || {};
  const name = f.team?.team ?? f.team;      // punching nests its club one level down
  return typeof name === "string" ? name.trim().toLowerCase() : "";
};

/**
 * One club, one post a day.
 *
 * THE FIRST REAL RUN NAMED HERACLES TWICE in six candidates — once for the highest floor
 * and once for out-cornering a top flight. Both were true and both were interesting, and
 * together they read as the set padding itself out, which is the exact failure this
 * module exists to end. A good club tends to hold several records at once, so this is the
 * common case rather than a freak one.
 *
 * APPLIED AFTER THE ROTATION, so which of the two survives changes with the day. Over a
 * week both get posted; on any one morning only one does.
 *
 * League-level and match-level findings carry no single club subject and are never
 * dropped by this.
 */
export const oneClubEach = (cands) => {
  const seen = new Set();
  return cands.filter((c) => {
    const club = subjectOf(c);
    if (!club) return true;
    if (seen.has(club)) return false;
    seen.add(club);
    return true;
  });
};

/**
 * Every oddity worth posting today, rotated so the lead moves.
 *
 * Returns [] when the survey is too thin to say anything, which is a real answer and the
 * caller reports it as one.
 */
export const oddityPosts = ({ survey = {}, site = "", now = new Date(),
                              limit = 6 } = {}) => {
  const findings = survey?.findings || {};
  const pool = survey?.pool || {};
  const built = BUILDERS
    .map(([, fn]) => fn({ findings, pool, site }))
    .filter(Boolean);
  return oneClubEach(rotate(built, dayIndex(now))).slice(0, Math.max(1, limit));
};
