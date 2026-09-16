import { runFraction, runParts, runSummary, thinHistory, THIN_HISTORY } from "./angleTone";

// A chip said "Cercle Brugge 4+ corners" and nothing about whether that rested on four
// games or fourteen. The run lived in the `title` attribute, which a phone cannot show —
// so on the device most of this audience reads it on, the evidence was simply absent.

describe("the run on the chip", () => {
  test("a five-game run reads as a fraction", () => {
    expect(runFraction({ kind: "over_team", hits: 4, settled: 5 })).toBe("4/5");
  });

  test("a ten-game run is visibly a different claim", () => {
    expect(runFraction({ kind: "over_team", hits: 9, settled: 10 })).toBe("9/10");
  });

  test("the window stands in when nothing has settled", () => {
    expect(runFraction({ kind: "over_team", hits: 5, window: 5 })).toBe("5/5");
  });

  test("a bare count is never shown without what it is out of", () => {
    // "9" could be nine of ten or nine of twenty. The first is a streak, the second a coin.
    expect(runFraction({ kind: "over_team", hits: 9 })).toBeNull();
    expect(runFraction({ kind: "over_team", hits: 9, settled: 0 })).toBeNull();
  });

  test("a mismatch has no run and is not given a manufactured one", () => {
    // It is two averages pointed at each other with no hit rate at all; "0/0" would read
    // as a streak that has never landed.
    expect(runFraction({ kind: "mismatch", hits: 0, settled: 0 })).toBeNull();
    expect(runFraction({ kind: "chase", hits: 4, settled: 5 })).toBeNull();
  });

  test("an under streak still shows its run", () => {
    expect(runFraction({ kind: "under_team", hits: 8, settled: 10 })).toBe("8/10");
  });

  test("no angle at all is null, not a crash", () => {
    expect(runFraction(null)).toBeNull();
    expect(runFraction({})).toBeNull();
  });
});

describe("a side with barely any season on file", () => {
  test("is flagged rather than left looking merely unproven", () => {
    // "Not proven yet" and "almost nothing to prove it with" are different problems, and
    // only one of them gets better by waiting for the run to grow.
    expect(thinHistory({ games: 4 })).toBe(true);
  });

  test("a full season is not flagged", () => {
    expect(thinHistory({ games: 24 })).toBe(false);
  });

  test("the boundary matches the backend's bar", () => {
    expect(THIN_HISTORY).toBe(6);
    expect(thinHistory({ games: THIN_HISTORY })).toBe(false);
    expect(thinHistory({ games: THIN_HISTORY - 1 })).toBe(true);
  });

  test("an angle predating the field is not flagged on a missing value", () => {
    // Treating absent as zero would mark every cached row thin until the next rebuild,
    // which reads as the board breaking rather than as caution.
    expect(thinHistory({})).toBe(false);
    expect(thinHistory(null)).toBe(false);
  });
});

describe("how long the run has been going", () => {
  // "Cercle Brugge 3+" says nothing about whether that rests on a side scraping three of
  // five or one that has cleared it nine straight. Those are different claims and the
  // record was presenting them identically.

  test("the length rides with the fraction", () => {
    expect(runSummary({ hits: 9, settled: 10, streak_len: 4 })).toBe("9/10 · 4 in a row");
  });

  test("a record row and a board row read the same run", () => {
    // A board row nests it under streak.length; a frozen record row carries it flat. One
    // extraction reading both is what stops the two growing separate opinions.
    const nested = { hits: 5, settled: 5, streak: { length: 3 } };
    const flat = { hits: 5, settled: 5, streak_len: 3 };
    expect(runSummary(nested)).toBe(runSummary(flat));
    expect(runParts(nested)).toEqual(runParts(flat));
  });

  test("a row with no recorded run degrades to the fraction", () => {
    // Rows frozen before the run was stored have no run to report. Inventing one would be
    // worse than omitting it.
    expect(runSummary({ hits: 4, window: 5 })).toBe("4/5");
  });

  test("a zero run is treated as absent rather than as a claim", () => {
    // 0 would read as "no run at all" — a claim about the team, not about what was
    // written down.
    expect(runSummary({ hits: 4, settled: 5, streak_len: 0 })).toBe("4/5");
    expect(runParts({ hits: 4, settled: 5, streak_len: 0 }).run).toBeNull();
  });

  test("pushes are shown rather than folded away", () => {
    expect(runSummary({ hits: 4, settled: 5, voids: 1, streak_len: 2 }))
      .toBe("4/5 · 1 push · 2 in a row");
  });

  test("nothing to report is null, not an empty badge", () => {
    expect(runSummary({})).toBeNull();
    expect(runSummary(null)).toBeNull();
    expect(runParts({ hits: 9 })).toBeNull();
  });
});
