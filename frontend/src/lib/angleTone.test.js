/**
 * The vivid colours are a STRENGTH LADDER on streaks — orange live, cyan strong, green
 * solid — because a streak is most of what the board is made of and how good it is, is
 * the thing worth knowing at a glance.
 *
 * Two rules sit outside the ladder and are the ones worth defending in tests:
 *   - an UNDER is red at any strength, because direction is not a confidence level and
 *     mistaking an under for an over is the expensive error;
 *   - mismatch and chase stay muted, so they cannot be mistaken for a streak.
 */
import { toneFor, toneLabel, SOLID_RUN } from "./angleTone";

const cls = (kind, strong, run) => {
  const t = toneFor(kind, strong, run);
  return strong ? t.on : t.off;
};

describe("the streak ladder", () => {
  test("a short live streak is orange", () => {
    expect(cls("over_team", false, 2)).toMatch(/amber/);
    expect(toneLabel("over_team", false, 2)).toBe("live streak");
  });

  test("a real run is cyan", () => {
    expect(cls("over_team", true, 3)).toMatch(/cyan/);
    expect(toneLabel("over_team", true, 4)).toBe("strong streak");
  });

  test("a long run is green — the solid pick", () => {
    expect(cls("over_team", true, SOLID_RUN)).toMatch(/emerald/);
    expect(cls("over_team", true, 19)).toMatch(/emerald/);
    expect(toneLabel("over_team", true, 12)).toBe("solid pick");
  });

  test("the ladder rungs are all different", () => {
    const live = cls("over_team", false, 2);
    const strong = cls("over_team", true, 3);
    const solid = cls("over_team", true, 9);
    expect(new Set([live, strong, solid]).size).toBe(3);
  });

  test("the solid threshold is inclusive, so a run exactly at it is green", () => {
    expect(cls("over_team", true, SOLID_RUN - 1)).toMatch(/cyan/);
    expect(cls("over_team", true, SOLID_RUN)).toMatch(/emerald/);
  });

  test("a match-total streak climbs the same ladder", () => {
    expect(cls("over_match", true, 19)).toMatch(/emerald/);
    expect(cls("over_match", true, 3)).toMatch(/cyan/);
    expect(cls("over_match", false, 1)).toMatch(/amber/);
  });
});

describe("unders never climb it", () => {
  test("an under is red at every strength and every run length", () => {
    for (const [strong, run] of [[false, 1], [true, 3], [true, 20]]) {
      for (const kind of ["under_team", "under_match"]) {
        expect(cls(kind, strong, run)).toMatch(/red/);
      }
    }
  });

  test("a long under run does NOT go green", () => {
    // the trap: 18-game under runs are common, and green means "back it"
    expect(cls("under_team", true, 18)).not.toMatch(/emerald/);
    expect(toneLabel("under_team", true, 18)).toBe("under streak");
  });

  test("an over and an under of equal strength never look alike", () => {
    expect(cls("over_team", true, 9)).not.toBe(cls("under_team", true, 9));
  });
});

describe("mismatch and chase stay out of the way", () => {
  test("neither borrows a ladder colour", () => {
    for (const kind of ["mismatch", "chase"]) {
      for (const strong of [true, false]) {
        expect(cls(kind, strong, 0)).not.toMatch(/emerald|cyan|amber|red/);
      }
    }
  });

  test("both are muted greys, and distinguishable from each other", () => {
    expect(cls("mismatch", true, 0)).toMatch(/zinc/);
    expect(cls("chase", true, 0)).toMatch(/zinc/);
    expect(cls("mismatch", true, 0)).not.toBe(cls("chase", true, 0));
  });

  test("a mismatch does not change with a run length it does not have", () => {
    expect(cls("mismatch", true, 0)).toBe(cls("mismatch", true, 12));
  });

  test("they are named for what they are", () => {
    expect(toneLabel("mismatch", true, 0)).toBe("mismatch");
    expect(toneLabel("chase", true, 0)).toBe("chase spot");
  });
});

describe("robustness", () => {
  test("a missing run length degrades to the lowest rung, never the highest", () => {
    expect(cls("over_team", true, undefined)).toMatch(/cyan/);
    expect(cls("over_team", true, undefined)).not.toMatch(/emerald/);
  });

  test("weak angles keep their colour and drop the fill", () => {
    expect(cls("under_team", false, 1)).toMatch(/bg-transparent/);
    expect(cls("over_team", true, 9)).toMatch(/bg-emerald/);
  });

  test("an unknown kind renders something rather than throwing", () => {
    expect(() => cls("something_new", true, 4)).not.toThrow();
    expect(cls("something_new", true, 4)).toEqual(expect.any(String));
  });
});
