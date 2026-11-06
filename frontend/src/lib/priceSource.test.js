/**
 * Which prices may be published as real.
 *
 * WHAT THIS GUARDS, IN BOTH DIRECTIONS, and both directions have already happened once:
 *
 *   - A DEMO PRICE TREATED AS REAL puts a fabricated edge on a card. The seeders write
 *     `fair_odds * uniform(0.90, 1.15)`, so an EV against one is the model finding value
 *     in its own jitter. It is the most attractive-looking row on the menu and it is not
 *     a bet.
 *   - A REAL PRICE TREATED AS DEMO empties the card. The six call sites tested
 *     `=== "manual"`, which was exactly right until prices started arriving from the
 *     bookmaker feed stamped "api" — at which point a fully priced board would have
 *     reported no real prices at all, and the daily post would have said there was
 *     nothing to bet on a day with sixty live prices on it.
 */
import {
  API, MANUAL, REAL_PRICE_SOURCES, isChosenByHand, isRealPrice, priceSourceLabel,
} from "./priceSource.js";

describe("what counts as a price somebody could take", () => {
  it("accepts a price a person typed in", () => {
    expect(isRealPrice(MANUAL)).toBe(true);
  });

  it("accepts a price off the bookmaker feed", () => {
    // The whole reason this module exists. See odds_feed.py: it is the best of several
    // books, which is if anything a better number than one typed from memory.
    expect(isRealPrice(API)).toBe(true);
    expect(isRealPrice("api")).toBe(true);
  });

  it("refuses a seeded demo price", () => {
    expect(isRealPrice("demo")).toBe(false);
  });

  it("refuses an unknown or absent source rather than assuming the best", () => {
    // Documents written before the stamp existed come back undefined. Unknown is not
    // real: the cost of guessing wrong is a fabricated edge in a published post.
    for (const v of [undefined, null, "", "MANUAL", "manual ", "feed", 0, 1, {}, []]) {
      expect(isRealPrice(v)).toBe(false);
    }
  });

  it("lists exactly the two real sources", () => {
    expect([...REAL_PRICE_SOURCES].sort()).toEqual(["api", "manual"]);
    expect(REAL_PRICE_SOURCES.has("demo")).toBe(false);
  });
});

describe("the narrower question of who chose the number", () => {
  it("is true only for a hand-typed price", () => {
    expect(isChosenByHand(MANUAL)).toBe(true);
    expect(isChosenByHand(API)).toBe(false);
  });

  it("is not the same question as whether the price is real", () => {
    // If these two ever collapse into one, the distinction the module was written for
    // has been lost.
    expect(isRealPrice(API)).toBe(true);
    expect(isChosenByHand(API)).toBe(false);
  });
});

describe("the label", () => {
  it("says nothing for a hand-typed price, since that is the normal case", () => {
    expect(priceSourceLabel(MANUAL)).toBe("");
  });

  it("names a feed price so it is not taken for a chosen one", () => {
    expect(priceSourceLabel(API)).toBe("feed price");
  });

  it("warns on anything that is not real, including unknown", () => {
    expect(priceSourceLabel("demo")).toBe("demo price");
    expect(priceSourceLabel(undefined)).toBe("demo price");
  });
});
