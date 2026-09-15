import {
  angleLabel, deadMessage, hasPanel, runLabel, splitAngles, statedRecord,
} from "./angleOfDay";

// The thing being protected here is a sentence, not a layout. "88%" and "7 of 8" describe
// the same eight games; one is a track record and the other is a small sample, and the
// panel sits directly above a list of bets somebody is going to place.

describe("what the record may be stated as", () => {
  test("a small sample gets the fraction and no percentage", () => {
    const s = statedRecord({ landed: 7, missed: 1, settled: 8, hit_rate: 87.5,
                             show_rate: false, min_sample: 20 });
    expect(s.strong).toBeNull();
    expect(s.text).toBe("7 of 8 landed so far");
  });

  test("and says why, rather than leaving the reader to do the division", () => {
    // A bare "7 of 8" invites exactly the number that was withheld, minus the caveat.
    const s = statedRecord({ landed: 7, missed: 1, settled: 8, show_rate: false,
                             min_sample: 20 });
    expect(s.caveat).toMatch(/Too few settled/);
    expect(s.caveat).toMatch(/20/);
  });

  test("a sample past the floor gets the rate, with its denominator attached", () => {
    const s = statedRecord({ landed: 31, missed: 11, settled: 42, hit_rate: 73.8,
                             show_rate: true, min_sample: 20 });
    expect(s.strong).toBe("73.8%");
    expect(s.text).toContain("31 of 42");
  });

  test("the percentage is never invented when the server withheld it", () => {
    // show_rate false with a rate present is the exact shape that tempts a template into
    // printing it anyway.
    const s = statedRecord({ landed: 7, missed: 1, settled: 8, hit_rate: 87.5,
                             show_rate: false });
    expect(s.strong).toBeNull();
    expect(JSON.stringify(s)).not.toContain("87.5");
  });

  test("nothing settled is not nought per cent", () => {
    const s = statedRecord({ landed: 0, missed: 0, settled: 0, pending: 4,
                             hit_rate: null, show_rate: false });
    expect(s.strong).toBeNull();
    expect(s.text).toBe("4 still to play — nothing has settled yet");
  });

  test("an empty ledger says so without a number at all", () => {
    const s = statedRecord({ settled: 0, pending: 0 });
    expect(s.text).toBe("Nothing has settled yet");
  });

  test("no tally at all draws nothing", () => {
    expect(statedRecord(null)).toBeNull();
  });
});

describe("a dead day says which kind of dead", () => {
  test("stale data admits it is the data", () => {
    const d = deadMessage({ dead: true, reason: "stale" });
    expect(d.title).toBe("Not publishing today");
    expect(d.body).toMatch(/stale form/);
  });

  test("an empty calendar and a strict bar read differently", () => {
    // Flattening these into one message loses the only day that demonstrates the bar does
    // anything: football on, nothing good enough.
    const quiet = deadMessage({ dead: true, reason: "no_fixtures" });
    const strict = deadMessage({ dead: true, reason: "no_qualifier" });
    expect(quiet.title).not.toBe(strict.title);
    expect(strict.body).toMatch(/all five of its last five/);
  });

  test("an unknown reason still produces words", () => {
    expect(deadMessage({ dead: true, reason: "something new" }).title).toBeTruthy();
  });

  test("a live day has no dead message", () => {
    expect(deadMessage({ dead: false })).toBeNull();
    expect(deadMessage(null)).toBeNull();
  });
});

describe("the panel draws on a dead day", () => {
  // Hiding it when there is nothing to say means the only days anyone sees this panel are
  // the days it makes a call — and a reader who never sees the bar turn anything away has
  // no reason to believe there is one.
  test("a dead payload still counts as a panel", () => {
    expect(hasPanel({ dead: true, reason: "no_qualifier", angles: [] })).toBe(true);
  });

  test("a live payload with angles counts", () => {
    expect(hasPanel({ dead: false, angles: [{ name: "A" }] })).toBe(true);
  });

  test("nothing at all does not", () => {
    expect(hasPanel(null)).toBe(false);
    expect(hasPanel({ dead: false, angles: [] })).toBe(false);
  });
});

describe("the lead angle is the rule's first row, not a different pick", () => {
  test("the top is separated from the rest in order", () => {
    const { top, rest } = splitAngles({ angles: [{ name: "A" }, { name: "B" }, { name: "C" }] });
    expect(top.name).toBe("A");
    expect(rest.map((r) => r.name)).toEqual(["B", "C"]);
  });

  test("one angle leaves no remainder", () => {
    const { top, rest } = splitAngles({ angles: [{ name: "A" }] });
    expect(top.name).toBe("A");
    expect(rest).toEqual([]);
  });

  test("no angles leaves no top", () => {
    expect(splitAngles({ angles: [] }).top).toBeNull();
    expect(splitAngles(null).top).toBeNull();
  });
});

describe("what the angle says it is", () => {
  test("the label carries the team and the line", () => {
    expect(angleLabel({ name: "Middlesbrough", line_label: "6+" }))
      .toBe("Middlesbrough 6+");
  });

  test("a missing label falls back to the line itself", () => {
    expect(angleLabel({ name: "NEC", line: 5 })).toBe("NEC 5+");
  });

  test("no angle is an empty string, not the word undefined", () => {
    expect(angleLabel(null)).toBe("");
  });

  test("the run is the reason the angle is here, so it is spelled out", () => {
    expect(runLabel({ hits: 5, settled: 5, streak: { length: 4 } }))
      .toBe("5 of 5 · 4 in a row");
  });

  test("pushes are shown rather than folded into the record", () => {
    expect(runLabel({ hits: 4, settled: 5, voids: 1 })).toBe("4 of 5 · 1 push");
  });

  test("a bare window stands in when nothing has settled", () => {
    expect(runLabel({ hits: 5, window: 5 })).toBe("5 of 5");
  });
});
