/**
 * Where a price came from, and whether it is a real one.
 *
 * WHAT THIS REPLACES, AND WHY IT HAD TO. Six places tested `odds_source === "manual"` to
 * mean "a real price somebody could actually have taken". That was exactly right while
 * there were only two kinds of price in the database: typed in by a person, or generated
 * by a seeder as `fair_odds * uniform(0.90, 1.15)` — the model finding value in its own
 * jitter, which looks identical to an edge on screen. The check existed to keep the
 * second out of anything published.
 *
 * Fetched prices are now a third kind, and they break the equivalence. A price pulled
 * from the market is as real as a hand-typed one — arguably more so, since it is the best
 * of several books rather than one remembered number — but it is NOT "manual", so every
 * one of those six checks would have classed a fully priced board as having no real
 * prices at all. The daily card would have said there was nothing to post on a day with
 * sixty live prices on it.
 *
 * So the question each of those call sites is actually asking gets a name. "Is this a
 * price somebody could have taken" is REAL. "Did a person choose this number" is a
 * different and much rarer question, and `isChosenByHand` answers that one where it is
 * genuinely what is meant.
 *
 * NO SOURCE AT ALL IS NOT REAL. Documents written before the stamp existed come back with
 * `source: undefined`, which means unknown — and an unknown price must not be published
 * as a real one. Unknown and demo are treated the same way here on purpose: the cost of
 * being wrong is a fabricated edge in a post.
 */

/** A price a person typed in, having looked at the market. */
export const MANUAL = "manual";

/** A price fetched from the provider's bookmaker feed. See backend/odds_feed.py. */
export const API = "api";

/**
 * Sources that represent a price genuinely available in a market.
 *
 * `demo` is deliberately absent, and so is every unrecognised value: the seeders stamp
 * their jitter as "demo", and anything this set does not list is treated as not real.
 */
export const REAL_PRICE_SOURCES = new Set([MANUAL, API]);

/** Could somebody actually have taken this price? Anything unknown answers false. */
export function isRealPrice(source) {
  return REAL_PRICE_SOURCES.has(source);
}

/**
 * Did a person choose this number themselves?
 *
 * Narrower than isRealPrice, and only for the few places that mean this rather than "is
 * it real" — a prompt to enter a price, say, which should not fire because a feed already
 * covered the fixture.
 */
export function isChosenByHand(source) {
  return source === MANUAL;
}

/** Short label for a row, or "" where there is nothing worth saying. */
export function priceSourceLabel(source) {
  if (source === API) return "feed price";
  if (source === MANUAL) return "";
  return isRealPrice(source) ? "" : "demo price";
}
