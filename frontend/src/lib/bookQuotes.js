// Every book's price for one market, as the price slot shows it.
//
// WHAT THE SLOT WAS MISSING. The board quoted one number and named one bookmaker, which
// answers "can I take this" and not "is this a market, or one book out on its own". Those
// are different questions and the second decides whether an edge is worth believing: a
// 2.32 against 2.29 and 2.28 is three books agreeing, and a 5.30 with nothing beside it is
// a long rung one book has mis-set. On the first live ladder carrying quotes, the two
// biggest edges on a fixture — +27.9% and +22.1% — were both single-book prices, while
// every rung three or more books agreed on came in under +11%.
//
// SO THE CONTROL IS NOT DECORATION. The best price stays in the slot, because that is
// what a backer acts on; what opens underneath is the evidence that the price is real.
//
// TAP AND HOVER, NOT HOVER ALONE. A hover-only disclosure does not exist on a phone, and
// this board is read on one more than anywhere else. The component opens on click for
// everyone and additionally on hover where the pointer is fine; this file holds the part
// that can be tested, which is everything except the listener.

/** Below this many books, the best price has nothing meaningful standing behind it. */
export const THIN_MARKET = 2;

/**
 * How far clear the best price has to be before it is treated as an outlier rather than
 * an edge.
 *
 * MEASURED, NOT CHOSEN. On the ladders carrying quotes, rungs three or more books priced
 * sat inside 5% of each other almost without exception; the ones that did not were long
 * team lines a single book had left stale. 8% is comfortably outside the agreeing cluster
 * and well inside the gap to the outliers.
 */
export const OUTLIER_CLEAR = 8;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** Does this market have anything to open? Older rows carry no quotes at all. */
export const hasQuotes = (m = {}) => (m?.quotes || []).length > 0;

/**
 * The books for one market, best first, each with how far behind the best it is.
 *
 * `behind` is (best / price - 1) * 100 — the same arithmetic the backend's spread uses,
 * so the row-level figures and the summary cannot disagree. It reads as "the best price
 * is this much better than this one", which is the quantity somebody deciding whether to
 * bother opening another account actually needs.
 */
export const quoteList = (m = {}) => {
  const rows = (m?.quotes || [])
    .map((q) => ({ book: q?.book, price: num(q?.price) }))
    .filter((q) => q.book && q.price !== null && q.price > 0);
  if (!rows.length) return [];
  const best = rows[0].price;
  return rows.map((q, i) => ({
    ...q,
    isBest: i === 0,
    // The best price is behind itself by nothing; a later row says how much is given up.
    behind: i === 0 ? 0 : Math.round((best / q.price - 1) * 1000) / 10,
  }));
};

/**
 * Is the best price out on its own?
 *
 * TWO WAYS TO BE ALONE, and both matter. One book quoted it, so nothing corroborates it;
 * or several did and the best is miles clear of them, which is the same problem wearing a
 * disguise — the other books are the market, and the odd one out is usually a line that
 * has not been moved rather than a price nobody else noticed.
 */
export const isOutlier = (m = {}) => {
  const rows = quoteList(m);
  if (!rows.length) return false;
  if (rows.length < THIN_MARKET) return true;
  return rows[1].behind >= OUTLIER_CLEAR;
};

/**
 * The one-line summary that sits on the control.
 *
 * "5 books · best +0.6% clear" / "1 book only"
 */
export const quoteSummary = (m = {}) => {
  const rows = quoteList(m);
  if (!rows.length) return "";
  if (rows.length === 1) return `1 book only (${rows[0].book})`;
  return `${rows.length} books · best ${rows[1].behind > 0 ? "+" : ""}${rows[1].behind}% clear`;
};

/**
 * What the control should warn about, or "" when there is nothing to say.
 *
 * SPELLED OUT RATHER THAN LEFT TO THE COLOUR. A tint says "something is different here"
 * and nothing about what; on a board whose whole job is deciding what to back, the row
 * that could lose somebody money is the row that has to use words.
 */
export const quoteWarning = (m = {}) => {
  const rows = quoteList(m);
  if (!rows.length) return "";
  if (rows.length === 1) {
    return "Only one book quoted this line — nothing to check it against.";
  }
  if (rows[1].behind >= OUTLIER_CLEAR) {
    return `This price is ${rows[1].behind}% clear of every other book. `
      + "A line that far out is more often stale than a genuine edge.";
  }
  return "";
};

/**
 * Where a book the reader holds sits, if it is on the list at all.
 *
 * The feed takes the best of 33 books and the best is frequently not one anybody has an
 * account with, which makes a headline edge unactionable. Given a preferred book this
 * answers with its own price and what that costs against the top of the market.
 */
export const atBook = (m = {}, book = "") => {
  if (!book) return null;
  const want = String(book).trim().toLowerCase();
  return quoteList(m).find((q) => q.book.toLowerCase() === want) || null;
};

/** The EV the reader would actually get at their own book, rather than at the best. */
export const evAtBook = (m = {}, book = "") => {
  const row = atBook(m, book);
  const prob = num(m?.prob);
  if (!row || prob === null) return null;
  // ev_percent(book, p) = (book * p - 1) * 100, with p as a fraction. `prob` is a
  // percentage on the wire, which is the trap: using it directly reports an edge about
  // a hundred times too big.
  return Math.round((row.price * (prob / 100) - 1) * 1000) / 10;
};
