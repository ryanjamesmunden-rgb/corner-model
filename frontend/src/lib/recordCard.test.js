import { stripOf, headlineOf, periodOf, cardFrom, STRIP_MAX } from "./recordCard";

const R = (result, day = 1) =>
  ({ result, kickoff: `2026-09-${String(day).padStart(2, "0")}T15:00:00Z` });

describe("the strip of outcomes", () => {
  test("a card that would hide every miss is made to show one", () => {
    // THE FAILURE THIS EXISTS FOR. The trim takes the most recent N, and the most recent N
    // can be a clean sweep. The headline would still read "3 of 30" and the picture
    // underneath would say unbeaten — which is the impression people actually take away.
    const rows = [R("loss"), R("loss"), ...Array.from({ length: 30 }, () => R("win"))];
    const strip = stripOf(rows, 5);
    expect(strip).toHaveLength(5);
    expect(strip).toContain("loss");
  });

  test("it does not manufacture a miss that never happened", () => {
    const strip = stripOf(Array.from({ length: 30 }, () => R("win")), 5);
    expect(strip).toEqual(["win", "win", "win", "win", "win"]);
  });

  test("a miss already inside the cut is left alone", () => {
    const rows = [R("win"), R("win"), R("loss"), R("win"), R("win")];
    expect(stripOf(rows, 3)).toEqual(["loss", "win", "win"]);
  });

  test("voids ride along but never stand in for a miss", () => {
    // A void returns the stake. Counting one as the card's proof of honesty would be
    // showing a non-result where a loss should be.
    const rows = [R("loss"), ...Array.from({ length: 10 }, () => R("void"))];
    const strip = stripOf(rows, 4);
    expect(strip).toContain("loss");
  });

  test("a short record is shown whole", () => {
    expect(stripOf([R("win"), R("loss")], 24)).toEqual(["win", "loss"]);
    expect(stripOf([], 24)).toEqual([]);
  });
});

describe("the headline", () => {
  test("is a fraction, because a percentage alone cannot be checked", () => {
    const h = headlineOf({ landed: 31, settled: 47 });
    expect(h.big).toBe("31 of 47");
    expect(h.rate).toBe(66);
  });

  test("refuses to exist before anything has settled", () => {
    // "0 of 0" is a claim about a record that has not been made. The honest answer to an
    // empty period is not to publish the graphic.
    expect(headlineOf({ landed: 0, settled: 0 })).toBeNull();
    expect(headlineOf({})).toBeNull();
  });

  test("a losing record is reported as readily as a winning one", () => {
    expect(headlineOf({ landed: 2, settled: 10 }).big).toBe("2 of 10");
  });
});

test("the period comes from the games, not from today", () => {
  expect(periodOf([R("win", 1), R("win", 14)])).toBe("1 Sep – 14 Sep");
  expect(periodOf([R("win", 9)])).toBe("9 Sep");
  expect(periodOf([])).toBe("");
});

describe("building a card from a results payload", () => {
  const payload = (over = {}) => ({
    posted: { claimed: { landed: 31, settled: 47, voided: 2, pending: 1,
      rows: [R("loss", 1), ...Array.from({ length: 40 }, (_, i) => R("win", (i % 28) + 1))],
      ...over } },
  });

  test("uses claimed only — an angle logged after kick-off is not a prediction", () => {
    const c = cardFrom({ ...payload(),
      posted: { ...payload().posted, recalled: { landed: 99, settled: 99, rows: [] } } });
    expect(c.big).toBe("31 of 47");
  });

  test("carries the thing almost nobody else can say", () => {
    expect(cardFrom(payload()).basis).toMatch(/snapshot frozen before kick-off/i);
  });

  test("carries the legal line, every time", () => {
    const c = cardFrom(payload());
    expect(c.legal).toMatch(/18\+/);
    expect(c.legal).toMatch(/begambleaware/i);
    expect(c.legal).toMatch(/do not predict/i);
  });

  test("never carries a profit or units figure", () => {
    // Posted angles are stored with a line and NO price, and the record is graded off a
    // snapshot that records the line too. Any units number here would be invented odds
    // applied after the result was known.
    const c = cardFrom(payload());
    const text = JSON.stringify(c).toLowerCase();
    expect(text).not.toMatch(/\bunits?\b|\bprofit\b|\broi\b|[+-]\d+(\.\d+)?u\b/);
  });

  test("a story fits more results than a feed post", () => {
    expect(STRIP_MAX.story).toBeGreaterThan(STRIP_MAX.feed);
    expect(cardFrom(payload(), { shape: "story" }).strip.length)
      .toBeGreaterThan(cardFrom(payload(), { shape: "feed" }).strip.length);
  });

  test("nothing settled means no card at all", () => {
    expect(cardFrom(payload({ landed: 0, settled: 0, rows: [] }))).toBeNull();
    expect(cardFrom({})).toBeNull();
  });
});
