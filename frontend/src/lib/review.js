/**
 * The week in review: played games, the prices that were on them, and what landed.
 *
 * WHAT THIS SCREEN IS FOR, and it is not a results page. The record pages answer "is the
 * board any good" from frozen claims. This answers a different question: of all the PRICES
 * that were sitting on a game, which ones the model liked actually came in — and that is
 * the question you read weekly to work out what the model is getting wrong.
 *
 * THE HEADLINE IS THE +EV RATE, NOT THE HIT RATE. Every stored ladder has rungs nobody
 * would back — a 2+ team line at 1.07 lands almost always — so a hit rate across all of
 * them describes the ladder and flatters the model. The only number worth leading with is
 * how the lines the model called value actually did.
 *
 * A RATE REFUSES TO EXIST WITHOUT SETTLED GAMES, the same rule the rest of the site
 * follows. Nothing settled and everything missed are different facts.
 */

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** How each outcome is drawn. Word and sign, never colour alone. */
export const RESULT_TONE = {
  won: "text-emerald-600 dark:text-emerald-400",
  lost: "text-rose-600 dark:text-rose-400",
  void: "text-muted-foreground",
  half_won: "text-emerald-600 dark:text-emerald-400",
  half_lost: "text-rose-600 dark:text-rose-400",
};

export const RESULT_WORD = {
  won: "landed", lost: "missed", void: "push",
  half_won: "half", half_lost: "half",
};

/** "Home Team Over 4.5" from a market key, for a row that has no label of its own. */
export const keyLabel = (key) => {
  const m = /^(home|away|total|both)_(over|under)_(\d+(?:\.\d+)?)$/.exec(String(key || ""));
  if (!m) return String(key || "");
  const who = { home: "Home", away: "Away", total: "Match", both: "Both teams" }[m[1]];
  return `${who} ${m[2]} ${m[3]}`;
};

/**
 * The one line a week should be read by.
 *
 * Returns null for `rate` until something has settled, and null for `profit` when a
 * winner's price was never stored — a total that quietly treated an unknown price as zero
 * would understate a winning week, which is the one direction that matters here.
 */
export const headline = (data) => {
  const settled = num(data?.ev_plus_settled) || 0;
  return {
    days: num(data?.days),
    games: num(data?.fixtures) || 0,
    graded: num(data?.graded) || 0,
    awaiting: num(data?.awaiting_corners) || 0,
    lines: num(data?.lines) || 0,
    evPlus: num(data?.ev_plus) || 0,
    evPlusLanded: num(data?.ev_plus_landed) || 0,
    settled,
    rate: settled > 0 ? num(data?.ev_plus_rate) : null,
    profit: num(data?.ev_plus_profit),
  };
};

/**
 * One reviewed game as a row.
 *
 * `evLines` is what the screen leads with — the rungs the model called value — and
 * `otherLines` is everything else, folded away. Both are kept: a review that showed only
 * the lines it liked could never show the model being wrong about which line to like.
 */
export const gameRow = (g) => {
  const lines = Array.isArray(g?.lines) ? g.lines : [];
  const isEv = (l) => num(l?.ev) !== null && num(l.ev) > 0;
  return {
    fixtureId: g?.fixture_id,
    date: g?.date,
    league: g?.league_name || g?.league_id || "",
    home: g?.home_name || "",
    away: g?.away_name || "",
    homeCorners: num(g?.home_corners),
    awayCorners: num(g?.away_corners),
    total: num(g?.total_corners),
    known: Boolean(g?.corners_known),
    evLines: lines.filter(isEv).sort((a, b) => (num(b.ev) || 0) - (num(a.ev) || 0)),
    otherLines: lines.filter((l) => !isEv(l)),
    priced: num(g?.priced) || 0,
    evPlus: num(g?.ev_plus) || 0,
    evPlusLanded: num(g?.ev_plus_landed) || 0,
    profit: num(g?.ev_plus_profit),
  };
};

export const gameRows = (data) =>
  (Array.isArray(data?.games) ? data.games : []).map(gameRow);

/** "7-4, 11 corners" — or that the statistics never arrived, which is not 0-0. */
export const scoreline = (row) => {
  if (!row?.known || row.homeCorners === null || row.awayCorners === null) {
    return "corner count not in yet";
  }
  return `${row.homeCorners}-${row.awayCorners}, ${row.total} corners`;
};

/**
 * What a line did, in one phrase: "Home over 4.5 @ 1.80 — landed (+0.80)".
 *
 * The price is always printed beside the result, because "it landed" without the number
 * is the half of the fact that invites the reader to supply the other half from memory.
 */
export const lineText = (l) => {
  const odds = num(l?.book_odds);
  const word = RESULT_WORD[l?.result] || l?.result || "";
  const profit = num(l?.profit);
  const money = profit === null ? "" : ` (${profit > 0 ? "+" : ""}${profit.toFixed(2)}u)`;
  return `${keyLabel(l?.key)}${odds === null ? "" : ` @ ${odds.toFixed(2)}`} — ${word}${money}`;
};

/**
 * "4+ landed last time at 1.62" — the memory a price is shown with.
 *
 * Null rather than a sentence when nothing is known: a line that has never been priced on
 * this team and one that has never landed are different facts, and the empty string reads
 * as the second.
 */
export const lastTimeText = (hist) => {
  const last = hist?.last;
  if (!last) return null;
  const odds = num(last.book_odds);
  const word = last.result === "won" ? "landed" : last.result === "lost" ? "missed" : "pushed";
  const found = num(hist.found) || 0;
  const landed = num(hist.landed) || 0;
  const run = found > 1 ? ` · ${landed} of the last ${found}` : "";
  return `Last time ${word}${odds === null ? "" : ` at ${odds.toFixed(2)}`}${run}`;
};
