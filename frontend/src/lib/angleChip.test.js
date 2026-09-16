import { runFraction, thinHistory, THIN_HISTORY } from "./angleTone";

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
