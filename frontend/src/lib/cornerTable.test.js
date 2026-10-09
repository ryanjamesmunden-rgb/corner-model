import { rankTeams, cellFor, maxOf, barWidth, barFor, splitOf, isSplit, isCol, THIN,
         COLS, SPLITS }
  from "./cornerTable";

const team = (name, splits) => ({ team_id: name, name, splits });
const s = (games, won, conceded, shots, sot, covered = {}) =>
  ({ games, corners_won: won, corners_conceded: conceded, shots, shots_on_target: sot,
     covered: { shots: covered.shots ?? games, shots_on_target: covered.sot ?? games } });

// Eight corners at home, two away. The overall average is five, describing neither half.
const LOPSIDED = team("Lopsided", {
  overall: s(4, 5, 6, 12, 4), home: s(2, 8, 3, 18, 7), away: s(2, 2, 9, 6, 1),
});
const FLAT = team("Flat", {
  overall: s(4, 6, 4, 10, 3), home: s(2, 6, 4, 10, 3), away: s(2, 6, 4, 10, 3),
});
// Shots recorded in one game of four.
const THIN_SHOTS = team("Thin", {
  overall: s(4, 4, 4, 30, 14, { shots: 1, sot: 1 }),
  home: s(2, 4, 4, 30, 14, { shots: 1, sot: 1 }),
  away: s(2, 4, 4, null, null, { shots: 0, sot: 0 }),
});
// No shot data anywhere.
const DARK = team("Dark", {
  overall: s(4, 7, 5, null, null, { shots: 0, sot: 0 }),
  home: s(2, 7, 5, null, null, { shots: 0, sot: 0 }),
  away: s(2, 7, 5, null, null, { shots: 0, sot: 0 }),
});
const TEAMS = [LOPSIDED, FLAT, THIN_SHOTS, DARK];

const order = (split, col) => rankTeams(TEAMS, split, col).map((t) => t.name);

describe("ranking", () => {
  it("is highest first", () => {
    expect(order("overall", "corners_won")).toEqual(["Dark", "Flat", "Lopsided", "Thin"]);
  });

  it("changes with the venue, which is why the venue is a choice", () => {
    // Lopsided is third overall and first at home. One solid average table cannot say
    // that, and that is the whole reason this split exists.
    expect(order("home", "corners_won")[0]).toBe("Lopsided");
    expect(order("away", "corners_won")[0]).toBe("Dark");
  });

  it("changes with the column", () => {
    expect(order("overall", "shots")[0]).toBe("Lopsided");
    expect(order("overall", "corners_conceded")[0]).toBe("Lopsided");
    expect(order("overall", "corners_won")[0]).toBe("Dark");
  });

  it("does NOT let a thin sample lead, however big its number", () => {
    // THE ONE THAT WAS WRONG FIRST. Thin has 30 shots a game off ONE covered game, and
    // dimming that cell was not enough — it still topped the table, and the row that
    // leads a table is the row people read. watchlist.py already paid for this:
    // "a five-game average is EXTREME by construction, so thin rows do not merely
    // appear in the ranking, they lead it."
    const byShots = order("overall", "shots");
    expect(byShots[0]).toBe("Lopsided");          // 12.0 over four covered games
    expect(byShots.indexOf("Thin")).toBeGreaterThan(byShots.indexOf("Flat"));
  });

  it("but keeps the thin row visible, below the evidenced ones", () => {
    // Underneath, not dropped. They are still real games.
    const byShots = order("overall", "shots");
    expect(byShots).toContain("Thin");
    expect(byShots.indexOf("Thin")).toBeLessThan(byShots.indexOf("Dark"));
  });

  it("orders inside a tier on the number alone", () => {
    // Everybody is thin in a venue split of two games, so the tiering is a no-op here
    // and it is a plain descending ranking again: 8, 7, 6, 4.
    expect(order("home", "corners_won")).toEqual(["Lopsided", "Dark", "Flat", "Thin"]);
  });

  it("sinks a team with nothing in the ranked column", () => {
    // Treating a gap as zero is defensible at the bottom of a SHOTS table and indefensible
    // at the top of a CONCEDED one, so it is sorted as absent in both.
    expect(order("overall", "shots").at(-1)).toBe("Dark");
    expect(order("away", "shots").slice(-2).sort()).toEqual(["Dark", "Thin"]);
  });

  it("does not mutate what it was given", () => {
    const before = TEAMS.map((t) => t.name);
    rankTeams(TEAMS, "home", "shots");
    expect(TEAMS.map((t) => t.name)).toEqual(before);
  });

  it("survives junk", () => {
    expect(rankTeams()).toEqual([]);
    expect(rankTeams([{ name: "x" }], "home", "shots")).toHaveLength(1);
  });
});

describe("reading one cell", () => {
  it("gives the figure and what it was built on", () => {
    const c = cellFor(LOPSIDED.splits.home, COLS[0]);
    expect(c).toMatchObject({ value: 8, covered: 2, missing: false });
  });

  it("counts a shot column on its COVERAGE, not on games played", () => {
    // Thin played four and the provider covered one of them. The denominators differ,
    // and the only thing that can tell a four-game average from a twelve-game one is
    // the denominator.
    const shots = COLS.find((c) => c.v === "shots");
    expect(cellFor(THIN_SHOTS.splits.overall, shots).covered).toBe(1);
    expect(cellFor(THIN_SHOTS.splits.overall, COLS[0]).covered).toBe(4);
  });

  it("marks a thin figure and leaves a well-covered one alone", () => {
    const shots = COLS.find((c) => c.v === "shots");
    expect(cellFor(THIN_SHOTS.splits.overall, shots).thin).toBe(true);
    expect(cellFor({ shots: 11, covered: { shots: THIN } }, shots).thin).toBe(false);
    expect(cellFor({ shots: 11, covered: { shots: THIN - 1 } }, shots).thin).toBe(true);
  });

  it("calls a gap a gap rather than a zero", () => {
    // "Not recorded" and "none taken" look the same once a gap is filled with 0, and
    // only one of them is true.
    const shots = COLS.find((c) => c.v === "shots");
    const c = cellFor(DARK.splits.overall, shots);
    expect(c.missing).toBe(true);
    expect(c.value).toBeNull();
  });

  it("and a real zero is a number, not a gap", () => {
    const shots = COLS.find((c) => c.v === "shots");
    expect(cellFor({ shots: 0, covered: { shots: 9 } }, shots))
      .toMatchObject({ missing: false, value: 0 });
  });

  it("survives an empty row", () => {
    expect(cellFor().missing).toBe(true);
    expect(cellFor({}, COLS[2]).covered).toBe(0);
  });
});

describe("the bar behind the team name", () => {
  it("is scaled on the column being ranked", () => {
    // Not silently on corners while you read a shots table.
    expect(maxOf(TEAMS, "overall", "corners_won")).toBe(7);
    expect(maxOf(TEAMS, "home", "corners_won")).toBe(8);
  });

  it("is NOT scaled on a thin outlier", () => {
    // Thin's 30 shots come off one covered game, so it ranks fourth — and if it also set
    // the scale it would have the longest bar on the table while sitting fourth, which
    // makes the picture contradict the order. 12 is the best well-evidenced figure.
    expect(maxOf(TEAMS, "overall", "shots")).toBe(12);
  });

  it("falls back to every value when nothing is well covered", () => {
    // Better a scaled all-thin column than a table of flat-lined bars.
    expect(maxOf([THIN_SHOTS], "overall", "shots")).toBe(30);
  });

  it("is a plain share of that scale, clamped", () => {
    const max = maxOf(TEAMS, "overall", "shots");
    expect(barWidth(12, max)).toBe(1);
    expect(barWidth(6, max)).toBe(0.5);
    expect(barWidth(30, max)).toBe(1);
  });

  it("but draws NO bar for a thin row, so the picture agrees with the order", () => {
    // Clamping was the first attempt and still left a side ranked fourth with the
    // longest bar on the table, because clamped means full.
    const shots = COLS.find((c) => c.v === "shots");
    const max = maxOf(TEAMS, "overall", "shots");
    expect(barFor(THIN_SHOTS.splits.overall, shots, max)).toBe(0);
    expect(barFor(DARK.splits.overall, shots, max)).toBe(0);
    expect(barFor(LOPSIDED.splits.overall, shots, max)).toBe(1);
  });

  it("draws nothing for a figure that is not there", () => {
    expect(barWidth(null, 10)).toBe(0);
    expect(barWidth(undefined, 10)).toBe(0);
    expect(barWidth(5, 0)).toBe(0);
  });

  it("never divides by zero", () => {
    expect(maxOf([DARK], "overall", "shots")).toBe(1);
    expect(maxOf()).toBe(1);
  });
});

describe("the controls agree with the payload", () => {
  it("every split the UI offers is one the backend sends", () => {
    // The backend's CORNER_TABLE_SPLITS. If one side grows a venue and the other does
    // not, the toggle renders a tab that selects an empty object.
    expect(SPLITS.map((x) => x.v)).toEqual(["overall", "home", "away"]);
    expect(Object.keys(LOPSIDED.splits).sort()).toEqual(["away", "home", "overall"]);
  });

  it("every column the UI offers exists on a split row", () => {
    COLS.forEach((c) => {
      expect(Object.keys(LOPSIDED.splits.overall)).toContain(c.v);
    });
  });

  it("validators reject anything else", () => {
    expect(isSplit("home")).toBe(true);
    expect(isSplit("neutral")).toBe(false);
    expect(isCol("shots_on_target")).toBe(true);
    expect(isCol("vibes")).toBe(false);
  });

  it("splitOf never throws on a half-built team", () => {
    expect(splitOf(undefined, "home")).toEqual({});
    expect(splitOf({ name: "x" }, "home")).toEqual({});
  });
});
