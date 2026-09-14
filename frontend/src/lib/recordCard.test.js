import { stripOf, headlineOf, periodOf, cardFrom, STRIP_MAX,
         dayCardFrom, unitsFor, settledDays } from "./recordCard";

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

describe("a single day", () => {
  const D = (result, price = null, stake = null, day = 13, name = "Viking") =>
    ({ name, line_label: "5+", result, price, stake,
       kickoff: `2026-09-${String(day).padStart(2, "0")}T15:00:00Z` });
  const payload = (rows) => ({ posted: { claimed: {
    landed: rows.filter((r) => r.result === "win").length,
    settled: rows.filter((r) => r.result !== "void" && r.result !== "pending").length,
    voided: 0, pending: 0, rows } } });

  test("the day everyone wants to post", () => {
    const rows = [D("win", 1.80, 1.5), D("win", 1.44, 2), D("win", 2.10), D("win", 1.65)];
    const c = dayCardFrom(payload(rows), { date: "2026-09-13" });
    expect(c.big).toBe("4 from 4");
    expect(c.clean).toBe(true);
    expect(c.units).toBeCloseTo(1.2 + 0.88 + 1.1 + 0.65, 2);
  });

  test("a day card ALWAYS carries the running month", () => {
    // The whole reason this is safe to publish. A month card is whatever the month was; a
    // day card is chosen, and the chosen day is the good one. The month beside it is what
    // stops that being a lie — and it is the version nobody else will copy.
    const rows = [D("win", 1.8), D("win", 1.8), D("loss", 2.0, null, 12)];
    const c = dayCardFrom(payload(rows), { date: "2026-09-13" });
    expect(c.context).toBe("2 of 3 this month");
  });

  test("no units unless EVERY settled pick that day carries a price", () => {
    // Totalling only the priced rows publishes a figure over an unstated subset — a number
    // that looks complete and is not, which is worse than publishing none.
    const rows = [D("win", 1.80), D("win"), D("win", 2.10), D("win")];
    const c = dayCardFrom(payload(rows), { date: "2026-09-13" });
    expect(c.units).toBeNull();
    expect(c.unitsNote).toBe("2 of 4 logged without a price");
  });

  test("a losing day renders as readily as a winning one", () => {
    const rows = [D("loss", 1.8), D("loss", 2.0), D("win", 3.0)];
    const c = dayCardFrom(payload(rows), { date: "2026-09-13" });
    expect(c.big).toBe("1 from 3");
    expect(c.clean).toBe(false);
    expect(c.units).toBeCloseTo(-1 - 1 + 2, 2);
  });

  test("stakes are honoured, and default to a flat unit", () => {
    expect(unitsFor([D("win", 3.0, 2)]).units).toBe(4);
    expect(unitsFor([D("win", 3.0)]).units).toBe(2);
    expect(unitsFor([D("loss", 3.0, 2)]).units).toBe(-2);
  });

  test("a price at or below evens is not a price", () => {
    // 1.0 is how a blank field submits, and below evens is not a bet. Either would
    // compute a return.
    expect(unitsFor([D("win", 1.0)]).units).toBeNull();
    expect(unitsFor([D("win", 0.9)]).units).toBeNull();
  });

  test("a day that settled nothing gets no card", () => {
    expect(dayCardFrom(payload([D("win", 1.8)]), { date: "2026-09-01" })).toBeNull();
    expect(dayCardFrom({}, { date: "2026-09-13" })).toBeNull();
  });

  test("the days on offer are the ones with a settled pick, newest first", () => {
    const rows = [D("win", 1.8, null, 11), D("loss", 2, null, 13), D("void", null, null, 12)];
    expect(settledDays(payload(rows))).toEqual(["2026-09-13", "2026-09-11"]);
  });
});
