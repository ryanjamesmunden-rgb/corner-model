import {
  RUNGS, consistencyHeadline, consistencyLabel, consistencyRow, consistencyRows,
  floorOf, hitsAt, ladderFor, valuesFor, SUBJECTS,
} from "./consistency";

/** A game row exactly as the fixture endpoint's `recent` emits it. */
const g = (won, conceded, extra = {}) => ({
  won, conceded, total: won + conceded, date: "2026-09-01T15:00:00Z",
  opponent: "X", home: true, ...extra,
});

const WON = SUBJECTS.find((s) => s.key === "won");

describe("the floor", () => {
  test("is the highest line every game cleared", () => {
    expect(floorOf([6, 4, 7, 5])).toBe(4);
  });

  test("of zero is a real result, not an absence", () => {
    // A side kept to nothing once HAS a floor of 0. Returning null for it would make a
    // genuine finding indistinguishable from having no games at all.
    expect(floorOf([0, 5, 6])).toBe(0);
  });

  test("with no games there is none", () => {
    expect(floorOf([])).toBeNull();
  });
});

describe("reading values off the games", () => {
  test("it takes the subject's own column", () => {
    const games = [g(6, 3), g(4, 8)];
    expect(valuesFor(games, (m) => m.won)).toEqual([6, 4]);
    expect(valuesFor(games, (m) => m.conceded)).toEqual([3, 8]);
    expect(valuesFor(games, (m) => m.total)).toEqual([9, 12]);
  });

  test("a game missing that number is dropped, not counted as zero", () => {
    // A zero would drag the floor to 0 and silently destroy the claim, which is the
    // strongest thing on the panel.
    expect(valuesFor([g(6, 3), { won: null, conceded: 4 }], (m) => m.won)).toEqual([6]);
    expect(valuesFor([g(6, 3), {}], (m) => m.won)).toEqual([6]);
  });
});

describe("hit counts", () => {
  test("carry the denominator with them", () => {
    expect(hitsAt([6, 4, 7, 5], 5)).toEqual({ line: 5, hits: 3, n: 4, pct: 75 });
  });

  test("count a game landing exactly on the line as a hit", () => {
    // These are `line+` claims — 5 clears 5+. An over on a whole number is not a push.
    expect(hitsAt([5], 5).hits).toBe(1);
  });

  test("no games is 0 of 0 rather than a division by zero", () => {
    expect(hitsAt([], 5)).toEqual({ line: 5, hits: 0, n: 0, pct: 0 });
  });
});

describe("the ladder", () => {
  test("opens on the floor, so the first rung always holds", () => {
    const l = ladderFor([6, 4, 7, 5]);
    expect(l[0]).toMatchObject({ line: 4, hits: 4, n: 4 });
    expect(l[0].pct).toBe(100);
  });

  test("climbs to show where reliability runs out", () => {
    const l = ladderFor([6, 4, 7, 5]);
    expect(l.map((x) => [x.line, x.hits])).toEqual([[4, 4], [5, 3], [6, 2], [7, 1]]);
  });

  test("it stops rather than printing rungs nothing reached", () => {
    // 8+ is 0/4 here and a rung of zeroes is noise on a strip meant to be glanced at.
    expect(ladderFor([6, 4, 7, 5]).some((x) => x.hits === 0)).toBe(false);
  });

  test("a floor of zero opens at one instead", () => {
    // "0+ every game" is true of every team that has ever played.
    expect(ladderFor([0, 4, 5])[0].line).toBe(1);
  });

  test("it is capped so the strip stays one row", () => {
    expect(ladderFor([3, 14]).length).toBeLessThanOrEqual(RUNGS + 1);
  });

  test("a single flat value still gives one rung", () => {
    expect(ladderFor([5, 5, 5]).map((x) => x.line)).toEqual([5, 6, 7, 8].slice(0, 1));
  });

  test("no games is no ladder", () => {
    expect(ladderFor([])).toEqual([]);
  });
});

describe("one subject's row", () => {
  test("it reports the claim, the spread and the average together", () => {
    const row = consistencyRow([g(6, 3), g(4, 5), g(7, 4)], WON);
    expect(row).toMatchObject({ key: "won", every: 4, low: 4, high: 7, range: 3, n: 3 });
    expect(row.avg).toBe(5.7);
  });

  test("the range is there because a floor and a mean do not separate these two", () => {
    // Same floor, same average, completely different bet.
    const steady = consistencyRow([g(4, 0), g(5, 0), g(4, 0), g(5, 0)], WON);
    const wild = consistencyRow([g(4, 0), g(9, 0), g(4, 0), g(1, 0)], WON);
    expect(steady.range).toBeLessThan(wild.range);
  });

  test("a floor of zero carries no claim", () => {
    const row = consistencyRow([g(0, 4), g(6, 4)], WON);
    expect(row.every).toBeNull();
    expect(row.low).toBe(0);
  });

  test("no games is no row at all", () => {
    expect(consistencyRow([], WON)).toBeNull();
    expect(consistencyRows([])).toEqual([]);
  });

  test("all three subjects come through for a normal set of games", () => {
    expect(consistencyRows([g(6, 3), g(5, 4)]).map((r) => r.key))
      .toEqual(["won", "conceded", "total"]);
  });
});

describe("the sentence", () => {
  test("names what held and where it stopped", () => {
    const row = consistencyRow([g(6, 0), g(4, 0), g(7, 0), g(5, 0)], WON);
    expect(consistencyLabel(row)).toBe("4+ every game · 5+ in 3 of 4");
  });

  test("says only what held when the next rung is empty", () => {
    const row = consistencyRow([g(5, 0), g(5, 0)], WON);
    expect(consistencyLabel(row)).toBe("5+ every game");
  });

  test("a floor of zero is stated as a range instead of a claim", () => {
    const row = consistencyRow([g(0, 0), g(7, 0)], WON);
    expect(consistencyLabel(row)).toBe("as low as 0 · up to 7");
  });

  test("nothing at all is an empty string, not 'undefined+'", () => {
    expect(consistencyLabel(null)).toBe("");
  });
});

describe("the panel header", () => {
  test("gives both floors, which is what the section is for", () => {
    const rows = consistencyRows([g(6, 5), g(5, 6), g(7, 5)]);
    expect(consistencyHeadline(rows)).toBe("wins 5+ every game · concedes 5+ every game");
  });

  test("names only the side that held one", () => {
    const rows = consistencyRows([g(6, 0), g(5, 4)]);
    expect(consistencyHeadline(rows)).toBe("wins 5+ every game");
  });

  test("says plainly when nothing held", () => {
    // Better than silence: "no line held in every game" is itself a finding about a side.
    const rows = consistencyRows([g(0, 0), g(9, 9)]);
    expect(consistencyHeadline(rows)).toBe("no line held in every game");
  });

  test("and nothing at all when there are no games", () => {
    expect(consistencyHeadline([])).toBe("");
  });
});
