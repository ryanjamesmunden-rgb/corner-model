import {
  angleLabel, coversLabel, deadMessage, hasPanel, runLabel, splitAngles,
  statedRecord, whyLabel,
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
    expect(d.title).toBe("Not publishing this round");
    expect(d.body).toMatch(/stale form/);
  });

  test("an empty calendar and a strict bar read differently", () => {
    // Flattening these into one message loses the only day that demonstrates the bar does
    // anything: football on, nothing good enough.
    const quiet = deadMessage({ dead: true, reason: "no_fixtures" });
    const strict = deadMessage({ dead: true, reason: "no_qualifier" });
    expect(quiet.title).not.toBe(strict.title);
    expect(strict.body).toMatch(/long enough to speak for itself/);
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

describe("why the fixture backs the streak up", () => {
  // The bar is what stops a quiet Tuesday filling with whatever was left on the board, so
  // the panel shows it rather than applying it silently.
  test("the model's read and the opponent's leakiness are both stated", () => {
    expect(whyLabel({ support: { prob: 71.2, opp_conceded: 7.1 } }))
      .toBe("model 71.2% · opp concedes 7.1/game");
  });

  test("the opponent's first-half scoring is not offered as a reason", () => {
    // Five measurements in this repo have failed to find an effect from it. It rides on
    // the row as context; listing it here would make it read as part of the bar.
    const why = whyLabel({ support: { prob: 71.2, opp_conceded: 7.1, opp_fh_rate: 62 } });
    expect(why).not.toMatch(/62/);
    expect(why).not.toMatch(/first|1H|fh/i);
  });

  test("a long run says it is its own argument", () => {
    // Listing the fixture numbers beside it would imply they are why it qualified, and for
    // these rows they are not — some have no opponent average at all, which is precisely
    // when the run has to carry it alone.
    const why = whyLabel({ route: "long_run", support: { run: 12, prob: 55, opp_conceded: 4.2 } });
    expect(why).toBe("12 in a row — long enough on its own");
    expect(why).not.toMatch(/4\.2|55/);
  });

  test("a long run with no recorded length still reads as one", () => {
    expect(whyLabel({ route: "long_run", support: {} }))
      .toBe("a run long enough on its own");
  });

  test("a corroborated row leads with the run, then the fixture", () => {
    expect(whyLabel({ route: "corroborated", support: { run: 6, prob: 71.2, opp_conceded: 7.1 } }))
      .toBe("6 in a row · model 71.2% · opp concedes 7.1/game");
  });

  test("a half-populated row says what it can", () => {
    expect(whyLabel({ support: { prob: 66 } })).toBe("model 66%");
  });

  test("no support at all is an empty string, not the word undefined", () => {
    expect(whyLabel({})).toBe("");
    expect(whyLabel(null)).toBe("");
  });
});


describe("which days the card is about", () => {
  // A card is a block of days, and a reader who cannot see which days is looking at a list
  // of games with no idea whether tonight is among them.
  // Asserted on SHAPE rather than on the exact month abbreviation: ICU renders September
  // as "Sept" in Node and "Sep" in some browsers, and pinning either would fail on a
  // machine where the code is perfectly correct.
  test("a span reads as a range, with both ends dated", () => {
    const label = coversLabel({ covers: { first: "2026-09-15", last: "2026-09-17" } }, "en-GB");
    expect(label).toMatch(/^Tue 15 Sept? – Thu 17 Sept?$/);
  });

  test("a single day does not read as a range of one", () => {
    const label = coversLabel({ covers: { first: "2026-09-15", last: "2026-09-15" } }, "en-GB");
    expect(label).toMatch(/^Tue 15 Sept?$/);
    expect(label).not.toContain("–");
  });


  test("no window is an empty string, not the word undefined", () => {
    expect(coversLabel(null)).toBe("");
    expect(coversLabel({})).toBe("");
    expect(coversLabel({ covers: { first: "2026-09-15" } })).toBe("");
  });

  test("an unreadable date falls back to the raw value rather than Invalid Date", () => {
    expect(coversLabel({ covers: { first: "nonsense", last: "nonsense" } })).toBe("nonsense");
  });
});
