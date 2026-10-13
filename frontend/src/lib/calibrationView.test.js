import { verdictTone, hasEnough, bandRows, caveats, headline, bandSentence }
  from "./calibrationView";

const band = (o = {}) => ({
  band: "65-70%", claims: 400, fixtures: 90, hits: 260, promised: 67.5,
  actual: 65.0, residual: -2.5, lo: 60.2, hi: 69.6, thin: false,
  calibrated: true, derived: 0, ...o,
});

const summary = (o = {}) => ({
  overall: { claims: 1200, fixtures: 180, promised: 55.0, actual: 54.0,
             residual: -1.0, thin: false, calibrated: true, derived: 0 },
  bands: [band()],
  ungraded: 0, derived_claims: 0, min_band: 25, verdict: "holding up so far", ...o,
});


describe("how confident the page may sound", () => {
  it("nothing readable is UNKNOWN, not good", () => {
    // A page that renders an empty table in a calm grey is making a claim by omission.
    expect(verdictTone(summary({ bands: [band({ thin: true })] }))).toBe("unknown");
    expect(verdictTone(summary({ bands: [] }))).toBe("unknown");
    expect(verdictTone(undefined)).toBe("unknown");
  });

  it("every readable band inside its interval is HOLDING", () => {
    expect(verdictTone(summary())).toBe("holding");
  });

  it("one band outside its interval is OFF", () => {
    expect(verdictTone(summary({ bands: [band(), band({ calibrated: false })] })))
      .toBe("off");
  });

  it("a thin band cannot make it OFF on its own", () => {
    // It has no interval worth being outside of.
    expect(verdictTone(summary({ bands: [band(), band({ thin: true, calibrated: false })] })))
      .toBe("holding");
  });
});


describe("the table keeps every band", () => {
  it("empty and thin bands are kept, and marked", () => {
    // Dropping them makes the table a list of the bands that filled up.
    const rows = bandRows(summary({ bands: [
      band(), band({ band: "80%+", claims: 0, actual: null, residual: null }),
      band({ band: "under 25%", claims: 4, thin: true }),
    ] }));
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.readable)).toEqual([true, false, false]);
  });

  it("survives an empty payload", () => {
    expect(bandRows(undefined)).toEqual([]);
    expect(bandRows({})).toEqual([]);
  });
});


describe("the caveats", () => {
  it("lead with the two denominators, because that is the one the eye misses", () => {
    const c = caveats(summary());
    expect(c[0]).toContain("1,200 lines from 180 fixtures");
    expect(c[0]).toContain("nearer the 180");
  });

  it("say so when the probabilities were derived rather than stored", () => {
    const c = caveats(summary({ derived_claims: 1200 }));
    expect(c.join(" ")).toContain("Every");
    expect(c.join(" ")).toContain("derived");
  });

  it("give the proportion when only some were derived", () => {
    expect(caveats(summary({ derived_claims: 600 })).join(" ")).toContain("50%");
  });

  it("say nothing about deriving when none were", () => {
    expect(caveats(summary()).join(" ")).not.toContain("derived");
  });

  it("report the ungraded fixtures as left out, not as misses", () => {
    expect(caveats(summary({ ungraded: 42 })).join(" "))
      .toContain("42 frozen fixtures have no result yet");
  });

  it("count the thin bands", () => {
    const c = caveats(summary({ bands: [band(), band({ thin: true, claims: 3 })] }));
    expect(c.join(" ")).toContain("1 band has fewer than 25");
  });

  it("do not count an EMPTY band as a thin one", () => {
    // An empty band is not a weak claim, it is no claim; listing it as a caveat would
    // pad the list with something a reader cannot act on.
    const c = caveats(summary({ bands: [band(), band({ thin: true, claims: 0 })] }));
    expect(c.join(" ")).not.toContain("band has fewer");
  });

  it("survive an empty payload", () => {
    expect(caveats(undefined)).toEqual([]);
    expect(caveats({})).toEqual([]);
  });
});


describe("the headline", () => {
  it("comes from the server, not from a second opinion computed here", () => {
    expect(headline(summary({ verdict: "the stated percentages are running HIGH" })))
      .toBe("the stated percentages are running HIGH");
  });

  it("refuses to conclude when nothing is readable", () => {
    expect(headline(summary({ bands: [band({ thin: true })] })))
      .toContain("Not enough settled fixtures");
  });

  it("survives an empty payload", () => {
    expect(headline(undefined)).toBe("");
  });
});


describe("a band in plain English", () => {
  it("names the promise, what happened, and both denominators", () => {
    const s = bandSentence(band());
    expect(s).toContain("about 67.5%");
    expect(s).toContain("65% of the time");
    expect(s).toContain("400 lines");
    expect(s).toContain("90 fixtures");
  });

  it("says nothing at all for a band with nothing in it", () => {
    // Better silent than "it happened null% of the time".
    expect(bandSentence(band({ claims: 0, actual: null }))).toBe("");
    expect(bandSentence(undefined)).toBe("");
  });
});

describe("the caveats read as English", () => {
  // The first version spliced four ternaries into one template and shipped
  // "Every probabilities one is derived from…" onto the page — in the caveat whose
  // entire job is to be believed.
  const s = (o) => caveats(summary(o)).join(" ");

  it("when all of them are derived", () => {
    expect(s({ derived_claims: 1200 }))
      .toContain("Every one of these probabilities is derived from the expected corners");
  });

  it("when some of them are", () => {
    expect(s({ derived_claims: 600 }))
      .toContain("50% of these probabilities are derived from the expected corners");
  });

  it("no caveat contains a doubled or orphaned word", () => {
    for (const d of [0, 600, 1200]) {
      for (const n of caveats(summary({ derived_claims: d }))) {
        expect(n).not.toMatch(/\b(\w+)\s+\1\b/i);
        expect(n).not.toMatch(/probabilities one is/);
      }
    }
  });
});
