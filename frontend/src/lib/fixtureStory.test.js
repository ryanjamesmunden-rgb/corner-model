import { fixtureStoryMarkets } from "./storyImage";

// What goes out in public and what does not is a product decision, so it is pinned here
// rather than left to whoever next edits the canvas code. The rule for a fixture story:
// the PROBABILITY is the claim worth posting, the model's PRICE is the reason to open the
// site. A change that leaks the price should fail a test, not ship.

const market = (group, line, prob, fair) => ({
  key: `${group}_over_${line}`, group, line, prob, fair_odds: fair,
});

// A realistic ladder: half-lines, which is how the model stores them.
const MARKETS = [
  market("total", 8.5, 71.0, 1.41),
  market("total", 9.5, 59.1, 1.69),
  market("total", 10.5, 46.7, 2.14),
  market("home", 4.5, 68.0, 1.47),
  market("home", 5.5, 54.0, 1.85),
  market("home", 6.5, 40.1, 2.49),
  market("away", 3.5, 61.0, 1.64),
  market("away", 4.5, 44.0, 2.27),
];
const LAMBDAS = { total: 10.4, home: 6.2, away: 4.4 };
const NAMES = { homeName: "Estudiantes LP", awayName: "Newells Old Boys" };

describe("which line each market leads with", () => {
  it("picks the line nearest the projection, not the first or the best-looking", () => {
    const rows = fixtureStoryMarkets(MARKETS, LAMBDAS, NAMES);
    expect(rows.map((r) => [r.group, r.line])).toEqual([
      ["total", 10], ["home", 6], ["away", 4],
    ]);
  });

  it("converts a half-line to the '+' form people actually say", () => {
    // "Over 9.5" and "10+" are the same bet; only one of them reads on a picture.
    const [total] = fixtureStoryMarkets(MARKETS, LAMBDAS, NAMES);
    expect(total.line).toBe(10);
    expect(Number.isInteger(total.line)).toBe(true);
  });

  it("labels the team markets with the team, not 'home' and 'away'", () => {
    const rows = fixtureStoryMarkets(MARKETS, LAMBDAS, NAMES);
    expect(rows.map((r) => r.label)).toEqual([
      "Match total", "Estudiantes LP", "Newells Old Boys",
    ]);
  });
});

describe("the probability goes out, the price is only carried", () => {
  it("keeps the probability on every row", () => {
    fixtureStoryMarkets(MARKETS, LAMBDAS, NAMES).forEach((r) => {
      expect(typeof r.prob).toBe("number");
      expect(r.prob).toBeGreaterThan(0);
    });
  });

  it("carries the real price so the blur has something true under it", () => {
    // A blur over a placeholder is a lie about what is being withheld.
    // 10+ is the "Over 9.5" row, so the price is that row's — 1.69, not 10.5's 2.14.
    const [total] = fixtureStoryMarkets(MARKETS, LAMBDAS, NAMES);
    expect(total.line).toBe(10);
    expect(total.price).toBe("1.69");
  });

  it("survives a market with no price rather than dropping the row", () => {
    const rows = fixtureStoryMarkets([market("total", 9.5, 59.1, null)], { total: 10 }, NAMES);
    expect(rows).toHaveLength(1);
    expect(rows[0].prob).toBe(59.1);
    expect(rows[0].price).toBeNull();
  });
});

describe("it refuses to make half a story", () => {
  it("returns nothing when there are no markets", () => {
    expect(fixtureStoryMarkets([], LAMBDAS, NAMES)).toEqual([]);
    expect(fixtureStoryMarkets(undefined, LAMBDAS, NAMES)).toEqual([]);
  });

  it("skips a group the model has no rows for", () => {
    const rows = fixtureStoryMarkets(MARKETS.filter((m) => m.group !== "away"), LAMBDAS, NAMES);
    expect(rows.map((r) => r.group)).toEqual(["total", "home"]);
  });

  it("skips a row with no probability rather than drawing a blank percentage", () => {
    const rows = fixtureStoryMarkets([market("total", 9.5, null, 1.69)], LAMBDAS, NAMES);
    expect(rows).toEqual([]);
  });

  it("does not fall over on missing lambdas", () => {
    expect(() => fixtureStoryMarkets(MARKETS, {}, NAMES)).not.toThrow();
    expect(fixtureStoryMarkets(MARKETS, {}, NAMES).length).toBeGreaterThan(0);
  });

  it("does not fall over on missing team names", () => {
    const rows = fixtureStoryMarkets(MARKETS, LAMBDAS, {});
    expect(rows.map((r) => r.label)).toEqual(["Match total", "home", "away"]);
  });
});
