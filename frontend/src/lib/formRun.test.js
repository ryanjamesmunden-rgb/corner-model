import {
  FORM_GAMES, RESULTS, formLabel, formRun, formSummary, resultOf, unbeatenRun,
} from "./formRun";

/** A game row as the fixture endpoint's `recent` emits it. */
const g = (gf, ga, over = {}) => ({
  gf, ga, won: 5, conceded: 4, total: 9,
  date: "2026-09-01T15:00:00Z", opponent: "X", home: true, ...over,
});

describe("one result", () => {
  test("reads from the team's own point of view", () => {
    expect(resultOf(g(2, 1))).toBe("W");
    expect(resultOf(g(1, 2))).toBe("L");
    expect(resultOf(g(1, 1))).toBe("D");
  });

  test("a game with no score on file is a gap, NOT a draw", () => {
    // THE ONE WAY THIS CAN BE WRONG AND LOOK RIGHT. Older cached rows carry corners and no
    // goals until the backfill reaches them, and `gf === ga` is true of two nulls — which
    // prints a confident D for a match nobody has the result of.
    expect(resultOf(g(null, null))).toBeNull();
    expect(resultOf({})).toBeNull();
    expect(resultOf(g(undefined, undefined))).toBeNull();
    expect(resultOf(g(2, null))).toBeNull();
  });

  test("a goalless draw is still a draw", () => {
    // 0-0 must survive the null check: zero is a real score.
    expect(resultOf(g(0, 0))).toBe("D");
  });
});

describe("the run going into the game", () => {
  // Newest first, as the endpoint sends them.
  const GAMES = [g(2, 1), g(1, 1), g(0, 2), g(3, 0), g(1, 0), g(0, 1)];

  test("reads left to right INTO the fixture, oldest first", () => {
    // "L W W D W" towards the game is a side finding form; the same five the other way is a
    // side losing it.
    expect(formRun(GAMES, 5).run).toEqual(["W", "W", "L", "D", "W"]);
  });

  test("it takes the most recent n, not the first n on file", () => {
    const { run } = formRun(GAMES, 5);
    expect(run).toHaveLength(5);
    expect(run[run.length - 1]).toBe("W");   // the most recent game
  });

  test("it shows ten by default", () => {
    expect(FORM_GAMES).toBe(10);
    // Six on file, so all six — the cap is a ceiling, not a requirement.
    expect(formRun(GAMES).run).toHaveLength(6);
  });

  test("ungraded games are dropped so every badge means a result", () => {
    const withGap = [g(2, 1), g(null, null), g(1, 1), g(0, 2), g(3, 0), g(1, 0)];
    const { run, played } = formRun(withGap, 5);
    expect(run).toEqual(["W", "W", "L", "D", "W"]);
    expect(played).toBe(5);
  });

  test("it says how many were available", () => {
    // What stops "W W" reading as a two-game unbeaten run when it is all that is on file.
    expect(formRun([g(1, 0), g(2, 0)]).played).toBe(2);
    expect(formRun([]).played).toBe(0);
  });

  test("no games is an empty run rather than a crash", () => {
    expect(formRun([]).run).toEqual([]);
    expect(formRun(undefined).run).toEqual([]);
  });
});

describe("the record", () => {
  test("counts each result and leaves out the ones that did not happen", () => {
    expect(formSummary(["W", "W", "D", "W", "L"])).toBe("3W 1D 1L");
    expect(formSummary(["W", "W", "W"])).toBe("3W");
  });

  test("nothing in is an empty string", () => {
    expect(formSummary([])).toBe("");
  });
});

describe("unbeaten", () => {
  test("counts back from the MOST RECENT game", () => {
    // Counting from the other end reports a run that ended weeks ago as one running into
    // this fixture — the same mistake the conceded streaks had to be stopped from making.
    expect(unbeatenRun(["W", "W", "L", "D", "W"])).toBe(2);
  });

  test("a defeat in the last game is a run of nothing", () => {
    expect(unbeatenRun(["W", "W", "W", "W", "L"])).toBe(0);
  });

  test("every game unbeaten is the whole run", () => {
    expect(unbeatenRun(["D", "W", "W", "D", "W"])).toBe(5);
  });

  test("an empty run is zero", () => {
    expect(unbeatenRun([])).toBe(0);
  });
});

describe("the one-line read", () => {
  test("names a run worth naming", () => {
    expect(formLabel(["W", "D", "W", "W", "D"])).toBe("unbeaten in 5");
    expect(formLabel(["L", "W", "W", "D", "W"])).toBe("unbeaten in 4");
  });

  test("and gives the record when there is no run", () => {
    // Two unbeaten is a pair of results, not a run — the same floor the rest of the site uses.
    expect(formLabel(["W", "W", "L", "D", "W"])).toBe("3W 1D 1L");
  });

  test("a side that just lost gets its record, not 'unbeaten in 0'", () => {
    expect(formLabel(["W", "W", "W", "W", "L"])).toBe("4W 1L");
  });

  test("nothing in is an empty string", () => {
    expect(formLabel([])).toBe("");
  });
});


// THIS SEASON ONLY. The pool mixes seasons on purpose — the sync tops up from last year
// while this one is thin — so a strip in August could be three games under a new manager and
// two under the old one, read as one run. A form strip is the most glanceable thing on the
// page and the least likely to be questioned, so it gets the strictest window.
describe("the season filter", () => {
  const MIXED = [
    g(2, 1, { season: 2026 }), g(1, 1, { season: 2026 }), g(0, 2, { season: 2026 }),
    g(3, 0, { season: 2025 }), g(1, 0, { season: 2025 }),
  ];

  test("last season's games are left out when a season is given", () => {
    const { run, played } = formRun(MIXED, 10, 2026);
    expect(run).toEqual(["L", "D", "W"]);
    expect(played).toBe(3);
  });

  test("and kept when none is", () => {
    // The caller not knowing the season must not silently empty the strip.
    expect(formRun(MIXED, 10).played).toBe(5);
    expect(formRun(MIXED, 10, null).played).toBe(5);
    expect(formRun(MIXED, 10, undefined).played).toBe(5);
  });

  test("an unknown season counts as current", () => {
    // Rows synced before the stamp shipped carry none, and dropping them would empty every
    // strip on the site for a week after a deploy.
    const unstamped = [g(2, 1), g(1, 1, { season: 2025 })];
    expect(formRun(unstamped, 10, 2026).played).toBe(1);
  });

  test("a side with no games this season shows an empty strip, not last year's", () => {
    const allOld = [g(2, 1, { season: 2025 }), g(1, 0, { season: 2025 })];
    expect(formRun(allOld, 10, 2026).run).toEqual([]);
  });
});
