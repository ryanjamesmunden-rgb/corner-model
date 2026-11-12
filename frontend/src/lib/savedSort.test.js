import {
  GAME_SORTS, GAME_SORT_DEFAULT, gameMetric, sortSavedGames, unprojectedCount,
} from "./savedSort";

const game = (id, date, total) => ({
  fixture_id: id, date,
  projection: total === null ? null : { lambda_total: total },
});


const ids = (rows) => rows.map((r) => r.fixture_id || r.name);

describe("what each list is ranked on", () => {
  it("ranks a game on the projected match total", () => {
    expect(gameMetric(game("a", "2026-11-14", 11.4))).toBe(11.4);
  });


  it("answers null rather than zero when there is nothing to rank on", () => {
    expect(gameMetric(game("a", "2026-11-14", null))).toBeNull();
    expect(gameMetric({})).toBeNull();
  });
});

describe("highest and lowest", () => {
  const games = [
    game("quiet", "2026-11-14T15:00", 8.2),
    game("busy", "2026-11-15T15:00", 13.6),
    game("mid", "2026-11-16T15:00", 10.1),
  ];

  it("puts the biggest projection first on highest", () => {
    expect(ids(sortSavedGames(games, "highest"))).toEqual(["busy", "mid", "quiet"]);
  });

  it("puts the smallest first on lowest", () => {
    expect(ids(sortSavedGames(games, "lowest"))).toEqual(["quiet", "mid", "busy"]);
  });

  it("leaves kick-off order alone by default", () => {
    expect(ids(sortSavedGames(games, "kickoff"))).toEqual(["quiet", "busy", "mid"]);
    expect(ids(sortSavedGames(games, undefined))).toEqual(["quiet", "busy", "mid"]);
    expect(GAME_SORT_DEFAULT).toBe("kickoff");
  });

  it("does not mutate the list it was given", () => {
    const before = ids(games);
    sortSavedGames(games, "highest");
    expect(ids(games)).toEqual(before);
  });
});

describe("rows the model has no number for", () => {
  const games = [
    game("known-low", "2026-11-14T15:00", 8.0),
    game("far", "2026-12-20T15:00", null),
    game("known-high", "2026-11-15T15:00", 12.0),
    game("also-far", "2026-12-28T15:00", null),
  ];

  it("keeps them last on highest", () => {
    expect(ids(sortSavedGames(games, "highest")))
      .toEqual(["known-high", "known-low", "far", "also-far"]);
  });

  it("keeps them last on lowest too, not first", () => {
    // THE WHOLE CARE HERE. Sorting an absent projection as zero would put these at the
    // top of "lowest", so the list that looked like an answer would be made of rows the
    // model has no opinion about.
    expect(ids(sortSavedGames(games, "lowest")))
      .toEqual(["known-low", "known-high", "far", "also-far"]);
  });

  it("does not reshuffle them when the direction flips", () => {
    const hi = ids(sortSavedGames(games, "highest")).slice(-2);
    const lo = ids(sortSavedGames(games, "lowest")).slice(-2);
    expect(hi).toEqual(lo);
    expect(hi).toEqual(["far", "also-far"]);
  });

  it("counts them so the page can say so", () => {
    expect(unprojectedCount(games)).toBe(2);
    expect(unprojectedCount([])).toBe(0);
    expect(unprojectedCount(null)).toBe(0);
  });
});

describe("ties resolve to something fixed", () => {
  it("falls back to kick-off for two games projecting the same", () => {
    const games = [
      game("later", "2026-11-16T15:00", 10.0),
      game("earlier", "2026-11-14T15:00", 10.0),
    ];
    expect(ids(sortSavedGames(games, "highest"))).toEqual(["earlier", "later"]);
    expect(ids(sortSavedGames(games, "lowest"))).toEqual(["earlier", "later"]);
  });

});


describe("the control", () => {
  it("offers kick-off, highest and lowest, each with a hint", () => {
    expect(GAME_SORTS.map((s) => s.key)).toEqual(["kickoff", "highest", "lowest"]);
    for (const s of GAME_SORTS) expect(s.label).toBeTruthy();
  });

  it("defaults to the order the page has always had", () => {
    // Changing what somebody sees on arrival is a different decision from giving them a
    // control, and only one of those was asked for.
    expect(GAME_SORT_DEFAULT).toBe(GAME_SORTS[0].key);
  });
});

