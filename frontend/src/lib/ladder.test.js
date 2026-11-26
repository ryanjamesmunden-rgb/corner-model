import { bestRung, ladderOf, recordAt, rung, rungText } from "./ladder";

// A run is measured at the lowest line it never missed, so the line it is named for is
// the one the market prices most easily — 3+ at 1.27, which nobody backs. The rung above
// is where the price is, and the same ten games say whether the side reaches it.

const games = (...vals) => vals.map((value, i) => ({ value, opponent: `Opp ${i}`,
                                                     home: i % 2 === 0 }));

// Newest five are the run; the five after that predate it.
const ROW = {
  line: 3,
  last_games: games(7, 5, 9, 4, 6, /* --- before the run --- */ 8, 4, 7, 5, 6),
  projection: {
    ladder: [
      { line: 4, label: "4+", market_key: "home_over_3.5", prob: 66.6,
        fair_odds: 1.5, book_odds: 1.85, ev: 23.2 },
      { line: 5, label: "5+", market_key: "home_over_4.5", prob: 53.3,
        fair_odds: 1.88, book_odds: 2.4, ev: 27.9 },
    ],
  },
};

describe("a side's record at a line", () => {
  it("counts the games that reached it", () => {
    expect(recordAt(games(7, 5, 2, 4), 4)).toEqual({ hits: 3, games: 4 });
  });

  it("counts a game exactly on the line, because 4+ means four", () => {
    expect(recordAt(games(4), 4)).toEqual({ hits: 1, games: 1 });
  });

  it("keeps a goalless game in the denominator", () => {
    // Zero corners is a real game and the easiest thing here to lose to a falsy check.
    expect(recordAt(games(0, 6), 4)).toEqual({ hits: 1, games: 2 });
  });

  it("is nothing rather than zero when there is nothing to count", () => {
    expect(recordAt([], 4)).toBeNull();
    expect(recordAt(null, 4)).toBeNull();
    expect(recordAt(games(5), null)).toBeNull();
  });
});

describe("one rung", () => {
  it("splits the run's own games from the five before it", () => {
    // THE HONEST HALF. 9 of 10 where 5 of the 9 are the games that DEFINED the run is a
    // different claim from 9 of 10 that holds up either side of it.
    const r = ladderOf(ROW)[0];
    expect(r.whole).toEqual({ hits: 10, games: 10 });
    expect(r.pre).toEqual({ hits: 5, games: 5 });
  });

  it("carries the book's number, the model's and the edge between them", () => {
    const r = ladderOf(ROW)[0];
    expect(r).toMatchObject({ line: 4, book: 1.85, fair: 1.5, prob: 66.6, ev: 23.2 });
  });

  it("says when the price beats what the side's own record implies", () => {
    // Nine of ten, shrunk, is 1.20. A book offering 1.85 is paying well over the odds.
    const nine = { ...ROW, last_games: games(7, 5, 9, 4, 6, 8, 4, 7, 5, 2) };
    expect(ladderOf(nine)[0].beatsRecord).toBe(true);
  });

  it("and when it does not", () => {
    // Five of ten, shrunk, is 2.00; 1.85 is short of it.
    const half = { ...ROW, last_games: games(7, 2, 9, 2, 6, 2, 4, 2, 1, 2) };
    expect(ladderOf(half)[0].beatsRecord).toBe(false);
  });

  it("prices a record of nothing at a long price rather than dividing by zero", () => {
    const none = { ...ROW, last_games: games(1, 1, 1, 1, 1, 1, 1, 1, 1, 1) };
    expect(ladderOf(none)[0].beatsRecord).toBe(false);
  });

  it("survives a rung nobody has priced", () => {
    const unpriced = { ...ROW, projection: { ladder: [
      { line: 4, label: "4+", prob: 66.6, fair_odds: 1.5, book_odds: null, ev: null }] } };
    const r = ladderOf(unpriced)[0];
    expect(r.book).toBeNull();
    expect(r.beatsRecord).toBe(false);
  });

  it("is an empty list for a row with no ladder at all", () => {
    expect(ladderOf({})).toEqual([]);
    expect(ladderOf(null)).toEqual([]);
    expect(rung({}, ROW)).toBeNull();
  });
});

describe("the rung worth leading with", () => {
  it("takes the longer price when both qualify", () => {
    // The record has already been asked to carry the higher line, so lead with it.
    expect(bestRung(ROW).line).toBe(5);
  });

  it("will not lead with one the record does not reach", () => {
    // 4+ holds in 9 of 10; 5+ in only 6, which is not a record to put a longer price on.
    const thin = { ...ROW, last_games: games(7, 5, 9, 4, 6, 8, 4, 7, 4, 3) };
    expect(bestRung(thin).line).toBe(4);
  });

  it("is null when no rung is priced", () => {
    const unpriced = { ...ROW, projection: { ladder: [
      { line: 4, label: "4+", prob: 60, fair_odds: 1.6, book_odds: null }] } };
    expect(bestRung(unpriced)).toBeNull();
  });

  it("is null when the price never beats the record", () => {
    // Ten of ten shrinks to 1.09, so 1.02 does not clear it — and without the shrink it
    // would, because an unshrunk ten of ten prices at 1.00 and everything beats that.
    const short = { ...ROW, projection: { ladder: [
      { line: 4, label: "4+", prob: 95, fair_odds: 1.05, book_odds: 1.02 }] } };
    expect(bestRung(short)).toBeNull();
  });
});

describe("how it reads", () => {
  it("names the line, the price and both halves of the record", () => {
    expect(rungText(ladderOf(ROW)[0]))
      .toBe("4+ at 1.85 · 10 of 10, 5 of 5 before the run");
  });

  it("says a model price is a model price", () => {
    const unpriced = { ...ROW, projection: { ladder: [
      { line: 4, label: "4+", prob: 66.6, fair_odds: 1.5, book_odds: null }] } };
    expect(rungText(ladderOf(unpriced)[0])).toContain("fair 1.50");
  });

  it("is empty for nothing", () => {
    expect(rungText(null)).toBe("");
  });
});
