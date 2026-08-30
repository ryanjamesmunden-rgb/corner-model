/**
 * Colour on the fixture board has to say DIRECTION before it says confidence.
 *
 * The reported bug: a fixture legitimately carries an over from one side's history and an
 * under from the other's, and the previous scheme painted both the same green — the board
 * appeared to recommend two opposing outcomes on one game, in identical colour. Whatever
 * else changes here, an over and an under must never render alike.
 */
import { toneFor } from "./angleTone";

const cls = (kind, strong) => {
  const t = toneFor(kind, strong);
  return strong ? t.on : t.off;
};

describe("direction is never ambiguous", () => {
  test("an over and an under on the same fixture look nothing alike", () => {
    // the exact case the user reported
    expect(cls("over_team", true)).not.toBe(cls("under_team", true));
    expect(cls("over_match", true)).not.toBe(cls("under_match", true));
  });

  test("no under ever renders green, at any strength", () => {
    for (const kind of ["under_team", "under_match"]) {
      for (const strong of [true, false]) {
        expect(cls(kind, strong)).toMatch(/red/);
        expect(cls(kind, strong)).not.toMatch(/emerald/);
      }
    }
  });

  test("an under stays red even when it is weak", () => {
    // direction outranks confidence: mistaking the direction is the expensive error
    expect(cls("under_team", false)).toMatch(/red/);
  });
});

describe("the three streak states the user asked for", () => {
  test("a solid over streak is green", () => {
    expect(cls("over_team", true)).toMatch(/emerald/);
  });

  test("an over streak that is running but not solid is orange", () => {
    expect(cls("over_team", false)).toMatch(/amber/);
  });

  test("an under streak is red", () => {
    expect(cls("under_team", true)).toMatch(/red/);
  });
});

describe("the other signals keep the palette already agreed on the Best Bets cards", () => {
  test("mismatch is cyan", () => {
    expect(cls("mismatch", true)).toMatch(/cyan/);
    expect(cls("mismatch", false)).toMatch(/cyan/);
  });

  test("chase is white", () => {
    expect(cls("chase", true)).toMatch(/zinc-100|zinc-300/);
  });

  test("neither borrows a direction colour, so they cannot be read as over or under", () => {
    for (const kind of ["mismatch", "chase"]) {
      expect(cls(kind, true)).not.toMatch(/emerald|red|amber/);
    }
  });
});

describe("strength still reads within the hue", () => {
  test("every kind is visually distinct strong vs weak", () => {
    for (const kind of ["over_team", "under_team", "mismatch", "chase", "over_match"]) {
      expect(cls(kind, true)).not.toBe(cls(kind, false));
    }
  });

  test("a weak angle drops its fill but keeps its colour", () => {
    // faded, not recoloured — otherwise the direction signal is lost exactly when the
    // reader is skimming
    expect(cls("under_team", false)).toMatch(/bg-transparent/);
    expect(cls("mismatch", false)).toMatch(/bg-transparent/);
    expect(cls("over_team", true)).toMatch(/bg-emerald/);
  });
});

describe("an unknown kind still renders something sane", () => {
  test("it falls through to the over treatment rather than crashing", () => {
    expect(() => cls("something_new", true)).not.toThrow();
    expect(cls("something_new", true)).toEqual(expect.any(String));
  });
});
