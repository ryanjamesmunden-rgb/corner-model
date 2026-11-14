// The two-tweet ladder post: the game, then every EV+ rung on one team's corners.
//
// THE FORMAT IS THE ACCOUNT'S OWN, pasted by its owner:
//
//   🚩 5+ Leganes [1.72]
//   📊 Model: 1.62 (62%) EV: +6.0%
//
//   🚩 6+ Leganes [2.30]
//   📊 Model: 2.11 (48%) EV: +9.3%
//
// AND IT IS NOT THE TELEGRAM ONE. telegramPick writes "📊 Model price: 1.76 (57%) | EV:
// +11.0%" — a different label and a pipe. Two near-identical formats is exactly how one
// of them drifts, so each is written once, here and there, and neither borrows the
// other's line.
//
// WHY THE EV IS RECOMPUTED RATHER THAN COPIED. The board carries an `ev` computed against
// the price it stored, and this post prints a price. If a human edits the price — which
// is the normal case, since the board's best quote is often at a book they do not hold —
// a copied EV would describe a number that is no longer on the screen. ev_percent is four
// characters of arithmetic and it cannot go stale.
//
// THE WHOLE LADDER GOES OUT, NOT A SHORTLIST. That is what was asked for and it is a
// defensible post: a reader seeing 5+ through 9+ can see the edge GROW with the line,
// which is the actual claim — the model thinks this team's corner distribution has a
// fatter tail than the book does. A single rung asserts; the ladder shows. What it also
// does is publish the longest rungs, which are the ones most often quoted by one book
// alone, so `books` rides on every row and `thinRungs` counts them.
import { postHeader, postDate, postTime } from "./shareText.js";

/** Rungs under this edge are not part of the claim. */
export const ANGLE_MIN_EV = 0.0;
/** Below this many books behind a price, the rung is flagged rather than dropped. */
export const THIN_BOOKS = 2;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** 4.5 -> "5+". How the line is said on X, where the account posts the plus form. */
export const plusOf = (line) => {
  const n = num(line);
  return n === null ? null : Math.trunc(n) + 1;
};

/**
 * The edge, in percent: `price * prob - 100`.
 *
 * `prob` is a PERCENTAGE on the wire and that is the first trap: used as a fraction it
 * reports an edge about a hundred times too big, which on a public post is unrecoverable.
 *
 * THE SECOND TRAP IS BINARY FLOATING POINT, AND REORDERING DOES NOT FIX IT. 2.30 * 47.5
 * is exactly 109.25 in decimal and 109.24999999999999 in a double, so a figure that
 * should read +9.3% comes out +9.2% — on the account's own pasted example. A price has
 * two decimals and a probability one, so their product has at most three of real
 * precision; snapping it to six clears the noise without touching any value that was
 * genuinely there.
 *
 * AND THE HALF ROUNDS AWAY FROM ZERO, BOTH WAYS. Math.round sends -13.25 to -13.2,
 * because it breaks ties towards +∞ — so a losing rung would be written a tenth kinder
 * than a winning one of the same size.
 */
const roundTo = (x, places) => {
  const f = 10 ** places;
  const v = x * f;
  return (v < 0 ? -Math.round(-v) : Math.round(v)) / f;
};

export const evPercent = (price, prob) => {
  const b = num(price);
  const p = num(prob);
  if (b === null || p === null) return null;
  return roundTo(roundTo(b * p, 6) - 100, 1);
};

/** The side of the fixture a market group belongs to. */
export const teamFor = (group, homeName = "", awayName = "") =>
  (group === "home" ? homeName : group === "away" ? awayName : "");

/**
 * One rung, as the post prints it.
 *
 * Two lines, no trailing spaces: the pasted original had one after the "]" and a trailing
 * space is invisible, unreproducible and stripped by every client anyway.
 */
export const rungLines = (r = {}) => {
  const plus = plusOf(r.line);
  const price = num(r.price);
  const fair = num(r.fair);
  const prob = num(r.prob);
  if (plus === null || price === null) return [];
  const ev = r.ev === undefined ? evPercent(price, prob) : num(r.ev);
  const out = [`🚩 ${plus}+ ${r.team} [${price.toFixed(2)}]`];
  const bits = [];
  if (fair !== null) bits.push(`Model: ${fair.toFixed(2)}`);
  if (prob !== null) bits.push(`(${Math.round(prob)}%)`);
  if (ev !== null) bits.push(`EV: ${ev > 0 ? "+" : ""}${ev.toFixed(1)}%`);
  if (bits.length) out.push(`📊 ${bits.join(" ")}`);
  return out;
};

/**
 * Every rung of one side's ladder that clears the floor, shortest line first.
 *
 * SHORTEST FIRST AND NOT BY EDGE. The ladder is the argument — 5+ through 9+ in order
 * shows the edge widening as the line lengthens, which is the thing being claimed.
 * Sorting by edge would put 9+ on top and turn an argument into a leaderboard.
 */
export const angleRungs = (row = {}, { group = "home", minEv = ANGLE_MIN_EV } = {}) => {
  const home = row.home_name || "";
  const away = row.away_name || "";
  const team = teamFor(group, home, away);
  const all = [row.best, ...(row.alternatives || []), ...(row.ladder || [])];
  const seen = new Set();
  const rows = [];
  for (const m of all) {
    if (!m || m.group !== group) continue;
    const key = m.key || `${m.group}_over_${m.line}`;
    if (seen.has(key)) continue;
    const price = num(m.book_odds);
    const prob = num(m.prob);
    if (price === null || prob === null) continue;
    const ev = evPercent(price, prob);
    if (ev === null || ev < minEv) continue;
    seen.add(key);
    const quotes = m.quotes || [];
    rows.push({
      key,
      team,
      group,
      line: num(m.line),
      plus: plusOf(m.line),
      price,
      prob,
      fair: num(m.fair_odds),
      ev,
      book: m.book || "",
      source: m.price_source || "",
      // HOW MANY BOOKS STAND BEHIND IT. The longest rungs carry the biggest edges and are
      // the ones most often quoted by a single book; the post does not drop them, but
      // nothing downstream should have to guess which they are.
      books: quotes.length,
      quotes,
    });
  }
  rows.sort((a, b) => (a.line ?? 0) - (b.line ?? 0));
  return rows;
};

/** "thecornermodel.com/fixture/abc123" — where the claim can be checked. */
export const fixtureUrl = (site = "", fixtureId = "") => {
  const host = String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
  if (!host || !fixtureId) return "";
  return `${host}/fixture/${fixtureId}`;
};

/**
 * Tweet one: the game.
 *
 * postHeader is reused rather than rewritten so the day, the flag and the clock agree
 * with every other post the app sends — see its own note on why two copies of three lines
 * is a bug waiting to happen.
 */
export const gamePost = ({ row = {}, site = "", heading = "" } = {}) => {
  if (!row || !row.fixture_id) return "";
  const head = postHeader({
    fixture: { date: row.date, league_id: row.league_id, league_name: row.league_name,
               home_name: row.home_name, away_name: row.away_name },
  });
  const url = fixtureUrl(site, row.fixture_id);
  return [heading, ...head, "", url].filter((l) => l !== null && l !== undefined)
    .join("\n").replace(/\n{3,}/g, "\n\n").trim();
};

/**
 * Tweet two: the ladder, in the account's exact format.
 *
 * `url` is OPTIONAL here because this is the reply in a thread — the fixture link is
 * already on the tweet above it, and repeating it in a reply costs characters that the
 * rungs need. Passed when the post is going out on its own.
 */
export const ladderPost = ({ rungs = [], url = "" } = {}) => {
  const blocks = (rungs || []).map(rungLines).filter((b) => b.length);
  if (!blocks.length) return "";
  const text = blocks.map((b) => b.join("\n")).join("\n\n");
  return url ? `${text}\n\n${url}` : text;
};

/**
 * Both tweets for one side of one fixture, or null when there is no angle on it.
 *
 * ONE SIDE PER THREAD. A fixture where both teams clear the floor is two separate
 * arguments about two different corner distributions, and running them down one tweet
 * would read as five picks on one game — which the ledger prices at -4.4% over 112u
 * against +13.0% for one or two.
 */
export const angleThread = (row = {}, { group = "home", site = "", minEv = ANGLE_MIN_EV,
                                        heading = "" } = {}) => {
  const rungs = angleRungs(row, { group, minEv });
  if (!rungs.length) return null;
  const url = fixtureUrl(site, row.fixture_id);
  const best = rungs.reduce((a, b) => (b.ev > a.ev ? b : a), rungs[0]);
  return {
    fixtureId: row.fixture_id,
    team: rungs[0].team,
    group,
    match: [row.home_name, row.away_name].filter(Boolean).join(" v "),
    league: row.league_name || "",
    leagueId: row.league_id || "",
    kickoff: row.date || null,
    day: postDate(row.date),
    time: postTime(row.date),
    rungs,
    n: rungs.length,
    bestEv: best.ev,
    topLine: best.plus,
    // Rungs whose price nobody else quoted. Not a filter — a count, so the caller can
    // decide, and so a thread made entirely of them is visible before it goes out.
    thinRungs: rungs.filter((r) => r.books > 0 && r.books < THIN_BOOKS).length,
    unquoted: rungs.filter((r) => !r.books).length,
    url,
    game: gamePost({ row, site, heading }),
    ladder: ladderPost({ rungs }),
  };
};
