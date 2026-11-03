/**
 * The pick-context panel's view logic.
 *
 * WHAT THESE GUARD. The backend decides which lines are evidence and which are colour;
 * this layer decides what the reader SEES, and the way to lose the distinction is to
 * render both the same. So the tests pin that colour is never promoted into the shown
 * set, that an all-colour side reads as empty rather than full, and that an ambiguous
 * line keeps its mark.
 */
import {
  CONTEXT_FOOTNOTE,
  COLOUR,
  EVIDENCE,
  GROUP_LABEL,
  contextLine,
  contextView,
  defaultSide,
  thinNote,
} from "./pickContext";

const claim = (over = {}) => ({
  key: "corner_run",
  group: "corners",
  tier: EVIDENCE,
  text: "Boro have won 6+ corners in 7 straight games.",
  n: 7,
  subject: "team",
  ambiguous: false,
  ...over,
});

const ctx = (over = {}) => ({
  team: "Boro",
  opponent: "Charlton",
  venue: "home",
  games_on_file: 20,
  thin: false,
  headline: "Boro have won 6+ in 7 straight. Charlton have conceded 6+ in 5 of 5 away.",
  lines: [claim()],
  all: [claim()],
  compound: [],
  ...over,
});

describe("contextLine", () => {
  it("drops a claim with no sentence", () => {
    expect(contextLine({ text: "   ", group: "corners" })).toBeNull();
    expect(contextLine(null)).toBeNull();
  });

  it("carries the sample size rather than inferring it from the words", () => {
    expect(contextLine(claim({ n: 9 })).n).toBe(9);
    expect(contextLine(claim({ n: undefined })).n).toBeNull();
  });

  it("labels the group in the reader's words", () => {
    expect(contextLine(claim()).groupLabel).toBe(GROUP_LABEL.corners);
  });

  it("files an unknown group under form rather than inventing a heading", () => {
    const c = contextLine(claim({ group: "wat" }));
    expect(c.group).toBe("colour");
    expect(c.groupLabel).toBe(GROUP_LABEL.colour);
  });

  it("treats anything that is not evidence as colour", () => {
    expect(contextLine(claim({ tier: "something" })).tier).toBe(COLOUR);
    expect(contextLine(claim({ tier: undefined })).tier).toBe(COLOUR);
  });

  it("keeps an ambiguous mark attached", () => {
    expect(contextLine(claim({ ambiguous: true })).ambiguous).toBe(true);
    expect(contextLine(claim()).ambiguous).toBe(false);
  });
});

describe("contextView", () => {
  it("returns null for nothing", () => {
    expect(contextView(null)).toBeNull();
    expect(contextView("nope")).toBeNull();
  });

  it("shows evidence only", () => {
    const v = contextView(ctx({
      lines: [claim(), claim({ key: "unbeaten", group: "colour", tier: COLOUR,
                               text: "Boro are unbeaten in 9." })],
      all: [claim(), claim({ key: "unbeaten", group: "colour", tier: COLOUR,
                             text: "Boro are unbeaten in 9." })],
    }));
    expect(v.shown.map((c) => c.key)).toEqual(["corner_run"]);
    expect(v.colour.map((c) => c.key)).toEqual(["unbeaten"]);
  });

  it("never promotes colour when there is no evidence", () => {
    // The failure this exists to stop: an all-colour side rendering as a full panel of
    // reasons. It has no reasons, and saying so is the honest answer.
    const only = claim({ key: "unbeaten", group: "colour", tier: COLOUR,
                         text: "Boro are unbeaten in 9." });
    const v = contextView(ctx({ lines: [only], all: [only], headline: null }));
    expect(v.shown).toEqual([]);
    expect(v.empty).toBe(true);
    expect(v.colour).toHaveLength(1);
  });

  it("is not empty when a compound carries the case", () => {
    const comp = claim({ key: "compound_team", text: "Boro have X and Y." });
    const v = contextView(ctx({ lines: [], all: [], compound: [comp] }));
    expect(v.empty).toBe(false);
    expect(v.joined).toHaveLength(1);
  });

  it("refuses a compound that is not wholly evidence", () => {
    // A joined sentence cannot be read back apart, so a half-colour compound must not be
    // offered as a reason. The backend downgrades it; this keeps that decision.
    const comp = claim({ key: "compound_team", tier: COLOUR,
                         text: "Boro have X and are unbeaten in 9." });
    const v = contextView(ctx({ lines: [], all: [], compound: [comp] }));
    expect(v.joined).toEqual([]);
    expect(v.empty).toBe(true);
  });

  it("passes the headline through and tolerates its absence", () => {
    expect(contextView(ctx()).headline).toContain("Charlton");
    expect(contextView(ctx({ headline: null })).headline).toBeNull();
    expect(contextView(ctx({ headline: "  " })).headline).toBeNull();
  });

  it("reports a thin record", () => {
    const v = contextView(ctx({ thin: true, games_on_file: 9 }));
    expect(v.thin).toBe(true);
    expect(v.games).toBe(9);
  });

  it("falls back to readable names rather than blank space", () => {
    const v = contextView(ctx({ team: null, opponent: "" }));
    expect(v.team).toBe("This side");
    expect(v.opponent).toBe("the opponent");
  });

  it("normalises the venue", () => {
    expect(contextView(ctx({ venue: "away" })).venue).toBe("away");
    expect(contextView(ctx({ venue: "junk" })).venue).toBe("home");
  });

  it("survives a malformed payload without throwing", () => {
    const v = contextView({ lines: "nope", all: null, compound: 7 });
    expect(v.shown).toEqual([]);
    expect(v.empty).toBe(true);
  });
});

describe("defaultSide", () => {
  it("opens on the side with more evidence", () => {
    const strong = { lines: [claim(), claim({ key: "corner_rate" })] };
    const weak = { lines: [claim({ key: "unbeaten", tier: COLOUR })] };
    expect(defaultSide({ home: weak, away: strong })).toBe("away");
    expect(defaultSide({ home: strong, away: weak })).toBe("home");
  });

  it("gives a tie to the home side, which the page is titled after", () => {
    const same = { lines: [claim()] };
    expect(defaultSide({ home: same, away: same })).toBe("home");
  });

  it("does not throw on an absent payload", () => {
    expect(defaultSide(undefined)).toBe("home");
    expect(defaultSide({})).toBe("home");
  });
});

describe("the standing caveat", () => {
  it("says the lines explain rather than confirm", () => {
    expect(CONTEXT_FOOTNOTE).toMatch(/do not confirm/i);
    expect(CONTEXT_FOOTNOTE).toMatch(/graded record/i);
  });

  it("names the sample in the thin note", () => {
    expect(thinNote(9)).toBe("Only 9 games on file.");
    expect(thinNote(1)).toBe("Only 1 game on file.");
    expect(thinNote(null)).toBeNull();
  });
});
