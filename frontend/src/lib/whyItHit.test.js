import { MIN_GROUP, SHOT_GAP, chaseSplit, shotSplit, splitByLine, whyItHit } from "./whyItHit";

const g = (won, { shots = 14, ht = "level" } = {}) => ({
  won, conceded: 4, total: won + 4, shots_for: shots, ht_state: ht,
  gf: 1, ga: 1, date: "2026-09-01T15:00:00Z", opponent: "X", home: true, season: 2026,
});

describe("splitting the games by the line", () => {
  test("hits and misses land in the right groups", () => {
    const { hit, miss } = splitByLine([g(7), g(5), g(6), g(3)], 6);
    expect(hit.map((x) => x.won)).toEqual([7, 6]);
    expect(miss.map((x) => x.won)).toEqual([5, 3]);
  });

  test("a game landing exactly on the line is a hit", () => {
    expect(splitByLine([g(6)], 6).hit).toHaveLength(1);
  });

  test("an uncovered game belongs to NEITHER group", () => {
    // Counting it as a miss would invent a failure the data does not record.
    const { hit, miss } = splitByLine([g(7), { won: null }], 6);
    expect(hit).toHaveLength(1);
    expect(miss).toHaveLength(0);
  });
});

describe("shots in the games that landed", () => {
  test("it compares the two groups' averages", () => {
    const games = [g(7, { shots: 20 }), g(8, { shots: 18 }),
                   g(3, { shots: 11 }), g(2, { shots: 13 })];
    expect(shotSplit(...Object.values(splitByLine(games, 6)))).toMatchObject({
      hit: 19, miss: 12, gap: 7, hitGames: 2, missGames: 2,
    });
  });

  test("a ZERO shot count is dropped, not averaged as zero", () => {
    // THE SAME TRAP THE CHART HAS TO DODGE. sync_real stores a missing shot count as 0
    // because the live lambda consumes it and must not see null — averaging it in would
    // drag a group down and invent a difference that is really a coverage gap.
    const { hit, miss } = splitByLine(
      [g(7, { shots: 20 }), g(8, { shots: 18 }), g(9, { shots: 0 }),
       g(3, { shots: 12 }), g(2, { shots: 12 })], 6);
    expect(shotSplit(hit, miss)).toMatchObject({ hit: 19, hitGames: 2 });
  });

  test("one game in a group is not a comparison", () => {
    expect(MIN_GROUP).toBe(2);
    const { hit, miss } = splitByLine([g(7), g(8), g(3)], 6);
    expect(shotSplit(hit, miss)).toBeNull();
  });

  test("and neither is an empty one", () => {
    expect(shotSplit([], [])).toBeNull();
  });
});

describe("who was chasing", () => {
  test("it counts half-time deficits in each group", () => {
    const games = [g(7, { ht: "trailing" }), g(8, { ht: "trailing" }),
                   g(3, { ht: "leading" }), g(2, { ht: "level" })];
    const { hit, miss } = splitByLine(games, 6);
    expect(chaseSplit(hit, miss)).toMatchObject({
      hitTrailing: 2, hitGames: 2, missTrailing: 0, missGames: 2,
    });
  });

  test("a game with no state on file is not counted either way", () => {
    // `ht: undefined` would hit the helper's default, so the field is deleted outright —
    // which is what a row synced before the state backfill actually looks like.
    const noState = g(8);
    delete noState.ht_state;
    const { hit, miss } = splitByLine(
      [g(7, { ht: "trailing" }), noState, g(3, { ht: "leading" }), g(2, { ht: "level" })], 6);
    expect(chaseSplit(hit, miss)).toBeNull();   // only one graded hit left
  });
});

describe("the sentences", () => {
  const CHASED = [
    g(7, { shots: 20, ht: "trailing" }), g(8, { shots: 19, ht: "trailing" }),
    g(9, { shots: 21, ht: "trailing" }), g(3, { shots: 12, ht: "leading" }),
    g(2, { shots: 11, ht: "leading" }),
  ];

  test("it names the shot gap with both counts behind it", () => {
    const rows = whyItHit(CHASED, 6);
    const shots = rows.find((r) => r.key === "shots");
    expect(shots.title).toBe("They shoot more in the games that land");
    expect(shots.detail).toContain("20 shots a game in the 3 that reached 6+");
    expect(shots.detail).toContain("against 11.5 in the 2 that did not");
  });

  test("it says when chasing is what did it", () => {
    const chased = whyItHit(CHASED, 6).find((r) => r.key === "chased");
    expect(chased.title).toBe("The games that landed were games they were chasing");
    expect(chased.detail).toContain("A side that has to come back takes corners.");
  });

  test("and when they did it from the front", () => {
    const front = [
      g(7, { shots: 18, ht: "leading" }), g(8, { shots: 19, ht: "leading" }),
      g(9, { shots: 20, ht: "level" }),
      g(3, { shots: 12, ht: "trailing" }), g(2, { shots: 11, ht: "trailing" }),
    ];
    expect(whyItHit(front, 6).find((r) => r.key === "led").detail)
      .toContain("not from coming back");
  });

  test("a flat shot count is reported as flat rather than left out", () => {
    // "Whatever separates them, it is not shots" is a finding, and a panel that only ever
    // spoke when it found a difference would be read as always finding one.
    const flat = [g(7, { shots: 14 }), g(8, { shots: 14 }),
                  g(3, { shots: 14 }), g(2, { shots: 14 })];
    const row = whyItHit(flat, 6).find((r) => r.key === "shots_flat");
    expect(row.detail).toContain("it is not how often they shot");
    expect(SHOT_GAP).toBe(2);
  });

  test("a gap under the threshold is not a difference", () => {
    const narrow = [g(7, { shots: 15 }), g(8, { shots: 15 }),
                    g(3, { shots: 14 }), g(2, { shots: 14 })];
    expect(whyItHit(narrow, 6).map((r) => r.key)).toEqual(["shots_flat"]);
  });

  test("nothing to compare is nothing said", () => {
    // A panel that always finds something to say is one nobody believes the fourth time.
    expect(whyItHit([g(7), g(8)], 6)).toEqual([]);
    expect(whyItHit([], 6)).toEqual([]);
    expect(whyItHit([g(7), g(3)])).toEqual([]);
  });
});
