import { TONE, SOLID_RUN, toneFor, toneOf, toneClass, toneLabel, toneIcon } from "./angleTone";

// The board's whole job is telling you at a glance why a game is on it. These pin the two
// rules that make that work: one colour means exactly one thing, and no meaning is ever
// carried by colour alone.

describe("four meanings, four colours", () => {
  it("has exactly four tones", () => {
    expect(Object.keys(TONE).sort()).toEqual(["edge", "streak", "strong", "under"]);
  });

  it("gives every tone an icon and a label, because colour alone is not legal here", () => {
    // Worst all-pairs CVD separation in this palette is 6.9 (green vs rose under
    // deuteranopia), which is only permitted alongside a second channel.
    Object.values(TONE).forEach((t) => {
      expect(typeof t.icon).toBe("string");
      expect(t.icon.length).toBeGreaterThan(0);
      expect(typeof t.label).toBe("string");
      expect(t.label.length).toBeGreaterThan(0);
    });
  });

  it("never reuses one hue for two meanings", () => {
    const bars = Object.values(TONE).map((t) => t.bar);
    expect(new Set(bars).size).toBe(bars.length);
  });

  it("keeps cyan out of the status palette — it is the brand, not a meaning", () => {
    const all = JSON.stringify(TONE);
    expect(all).not.toMatch(/cyan/);
    expect(all).not.toMatch(/primary/);
  });
});

describe("an under is never green", () => {
  // Mistaking an under for an over is the expensive error, so direction wins over strength.
  it.each([
    ["under_match", true, 20],
    ["under_match", false, 0],
    ["under_team", true, 99],
  ])("%s stays the under tone at strong=%s run=%s", (kind, strong, run) => {
    expect(toneOf(kind, strong, run)).toBe(TONE.under);
  });

  it("says so in the label whatever the run length", () => {
    expect(toneLabel("under_match", true, 30)).toBe("under streak");
  });
});

describe("mismatches get their own colour now", () => {
  it("tones a mismatch as an edge rather than hiding it in grey", () => {
    expect(toneOf("mismatch", false, 0)).toBe(TONE.edge);
    expect(toneOf("chase", true, 4)).toBe(TONE.edge);
  });

  it("is visually distinct from a strong over", () => {
    expect(TONE.edge.bar).not.toBe(TONE.strong.bar);
  });
});

describe("strength is intensity within one hue, not a second hue", () => {
  it("uses the same green for a strong run and a solid one", () => {
    expect(toneOf("over_team", true, SOLID_RUN)).toBe(TONE.strong);
    expect(toneOf("over_team", true, SOLID_RUN - 3)).toBe(TONE.strong);
  });

  it("fills the chip only once the run is long enough", () => {
    expect(toneClass("over_team", true, SOLID_RUN)).toBe(TONE.strong.on);
    expect(toneClass("over_team", true, SOLID_RUN - 1)).toBe(TONE.strong.off);
  });

  it("treats an unproven over as its own state, not a dim green", () => {
    expect(toneOf("over_team", false, 2)).toBe(TONE.streak);
    expect(toneClass("over_team", false, 2)).toBe(TONE.streak.off);
  });
});

describe("labels stay honest about the evidence", () => {
  it.each([
    ["over_team", true, SOLID_RUN, "solid pick"],
    ["over_team", true, SOLID_RUN - 1, "strong streak"],
    ["over_team", false, 1, "live streak"],
    ["mismatch", false, 0, "mismatch"],
    ["chase", false, 0, "chase spot"],
  ])("%s/%s/%s reads as %s", (kind, strong, run, want) => {
    expect(toneLabel(kind, strong, run)).toBe(want);
  });
});

describe("edge cases do not throw", () => {
  it.each([[undefined], [null], [""], [123]])("handles kind=%s", (kind) => {
    expect(() => toneClass(kind, false, 0)).not.toThrow();
    expect(Object.values(TONE)).toContain(toneOf(kind, false, 0));
  });

  it("defaults a missing run length to unproven", () => {
    expect(toneOf("over_team", false)).toBe(TONE.streak);
  });

  it("exposes an icon for every angle kind", () => {
    ["over_team", "under_match", "mismatch", "chase"].forEach((k) => {
      expect(toneIcon(k, true, 7)).toBeTruthy();
    });
  });

  it("toneFor ignores strength and answers on kind alone", () => {
    expect(toneFor("mismatch")).toBe(TONE.edge);
    expect(toneFor("under_match")).toBe(TONE.under);
    expect(toneFor("over_team")).toBe(TONE.strong);
  });
});
