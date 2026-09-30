import {
  MIN_SAMPLE, STRONG, WEAK, angleFactors, anglePanel, splitKeyFactors,
} from "./angleFactors";

const g = (won, conceded, over = {}) => ({
  won, conceded, total: won + conceded, gf: 1, ga: 1, shots_for: 14,
  date: "2026-09-01T15:00:00Z", opponent: "X", home: true, season: 2026, ...over,
});

const keys = (rows) => rows.map((r) => r.key);

/** Ten games where they reached 6+ eight times, never below 4. */
const STRONG_TEN = [8, 7, 6, 9, 4, 6, 7, 6, 7, 5].map((w) => g(w, 4));
/** Ten where the opponent shipped 6+ eight times. */
const LEAKY_TEN = [4, 3, 5, 2, 4, 3, 4, 3, 5, 4].map((w) => g(w, [8, 7, 6, 9, 4, 6, 7, 6, 7, 5][0]));

describe("the record at the line", () => {
  test("a strong record is a reason FOR", () => {
    const { for: f } = angleFactors({ games: STRONG_TEN, line: 6, teamName: "Grimsby" });
    expect(keys(f)).toContain("record");
    expect(f.find((r) => r.key === "record").title).toBe("Grimsby reached 6+ in 8 of 10");
  });

  test("a weak one is a reason AGAINST, and says so in words", () => {
    const { against } = angleFactors({ games: STRONG_TEN, line: 9, teamName: "Grimsby" });
    const row = against.find((r) => r.key === "record");
    expect(row.title).toBe("Grimsby reached 9+ in 1 of 10");
    expect(row.detail).toContain("above what they usually manage");
  });

  test("a middling one is neither, rather than padding", () => {
    // 5 of 10 at 7+ is 50% — between the two thresholds and worth saying nothing about.
    const { for: f, against } = angleFactors({ games: STRONG_TEN, line: 7 });
    expect(keys(f)).not.toContain("record");
    expect(keys(against)).not.toContain("record");
    expect(STRONG).toBe(0.7);
    expect(WEAK).toBe(0.4);
  });

  test("the floor is its own claim, because it survives a bad day and a rate does not", () => {
    // "never below 4" is a different statement from "4+ in 10 of 10".
    const { for: f } = angleFactors({ games: STRONG_TEN, line: 4 });
    const floor = f.find((r) => r.key === "floor");
    expect(floor.title).toBe("They have not been under 4 once");
    expect(floor.detail).toContain("lowest in these 10 games was 4");
  });

  test("and it is absent when one game broke it", () => {
    expect(keys(angleFactors({ games: STRONG_TEN, line: 5 }).for)).not.toContain("floor");
  });
});

describe("the defence they are meeting", () => {
  const oppLeaky = [8, 7, 6, 9, 4, 6, 7, 6, 7, 5].map((c) => g(3, c));
  const oppSolid = [2, 3, 1, 2, 4, 2, 3, 2, 1, 3].map((c) => g(3, c));

  test("a leaky one is a reason for", () => {
    const { for: f } = angleFactors({ games: STRONG_TEN, oppGames: oppLeaky, line: 6,
                                      oppName: "Brighton" });
    expect(f.find((r) => r.key === "opp_leaky").title)
      .toBe("Brighton concede 6+ in 8 of 10");
  });

  test("a solid one is a reason against", () => {
    const { against } = angleFactors({ games: STRONG_TEN, oppGames: oppSolid, line: 6,
                                       oppName: "Brighton" });
    expect(against.find((r) => r.key === "opp_solid").title)
      .toBe("Brighton rarely concede 6+");
  });

  test("it reads the opponent's CONCEDED column, not their attack", () => {
    // The trap: a leaky side that also wins few corners. Reading `won` would find nothing
    // and the panel would be silent on the fixture it exists for.
    const { for: f } = angleFactors({ games: STRONG_TEN, oppGames: oppLeaky, line: 6 });
    expect(keys(f)).toContain("opp_leaky");
  });
});

describe("where the line sits against the projection", () => {
  test("a line under the projection is a reason for", () => {
    const { for: f } = angleFactors({ games: STRONG_TEN, line: 5, lambda: 6.4 });
    expect(f.find((r) => r.key === "line_low").detail).toContain("6.4");
  });

  test("a line above it says plainly that it needs a better than usual game", () => {
    const { against } = angleFactors({ games: STRONG_TEN, line: 7, lambda: 6.0 });
    expect(against.find((r) => r.key === "line_high").detail)
      .toContain("needs more than their usual");
  });

  test("a line at the projection is neither", () => {
    const { for: f, against } = angleFactors({ games: STRONG_TEN, line: 6, lambda: 6.2 });
    expect(keys(f)).not.toContain("line_low");
    expect(keys(against)).not.toContain("line_high");
  });

  test("no projection means no row rather than a guess", () => {
    const { for: f, against } = angleFactors({ games: STRONG_TEN, line: 6 });
    expect(keys(f)).not.toContain("line_low");
    expect(keys(against)).not.toContain("line_high");
  });
});

describe("what the record is made of", () => {
  test("a thin sample is always AGAINST, never for", () => {
    // Three games at 3 of 3 is 100% of nothing much, and a panel that put it on the for
    // side would be reading a coincidence as evidence.
    const three = [7, 8, 6].map((w) => g(w, 4));
    const { for: f, against } = angleFactors({ games: three, line: 6 });
    expect(keys(against)).toContain("thin");
    expect(keys(f)).not.toContain("thin");
    expect(MIN_SAMPLE).toBe(5);
  });

  test("stale games are counted and named", () => {
    const mixed = [...STRONG_TEN.slice(0, 7),
                   ...[6, 7, 8].map((w) => g(w, 4, { season: 2025 }))];
    const { against } = angleFactors({ games: mixed, line: 6, currentSeason: 2026 });
    const stale = against.find((r) => r.key === "stale");
    expect(stale.title).toBe("3 of these are from last season");
    expect(stale.detail).toContain("not entirely about the side playing on the day");
  });

  test("and nothing is said when the window is all current", () => {
    const { against } = angleFactors({ games: STRONG_TEN, line: 6, currentSeason: 2026 });
    expect(keys(against)).not.toContain("stale");
  });
});

describe("the backend's own factors", () => {
  const ROWS = [
    { key: "chase", kind: "boost", title: "Chasing suits them" },
    { key: "early_goal", kind: "risk", title: "An early goal for them" },
    { key: "cards", kind: "watch", title: "A red would change it" },
  ];

  test("boosts go for and risks go against", () => {
    const { for: f, against } = splitKeyFactors(ROWS);
    expect(keys(f)).toEqual(["chase"]);
    expect(keys(against)).toContain("early_goal");
  });

  test("an unclassified caveat goes AGAINST, not for", () => {
    // An unclassified caveat is a reason for care and never a reason for confidence.
    expect(keys(splitKeyFactors(ROWS).against)).toContain("cards");
  });

  test("nothing in is two empty lists", () => {
    expect(splitKeyFactors()).toEqual({ for: [], against: [] });
  });
});

describe("the panel", () => {
  test("merges both sources into two lists", () => {
    const panel = anglePanel(
      // lambda 7.5 against a line of 6 — a full corner clear, which is what line_low asks
      // for. At 6.9 it is only 0.9 below and the row correctly stays silent.
      { games: STRONG_TEN, line: 6, lambda: 7.5, currentSeason: 2026 },
      [{ key: "chase", kind: "boost" }, { key: "early_goal", kind: "risk" }]);
    expect(keys(panel.for)).toEqual(expect.arrayContaining(["record", "line_low", "chase"]));
    expect(keys(panel.against)).toContain("early_goal");
  });

  test("no line means nothing to argue about", () => {
    // The panel is about a BET. Without one there is no claim to weigh.
    expect(angleFactors({ games: STRONG_TEN })).toEqual({ for: [], against: [] });
    expect(angleFactors({})).toEqual({ for: [], against: [] });
  });

  test("it never invents a verdict", () => {
    // Adding these up would be a new model with no measurement behind it, and
    // measure_chase_board spent a day showing this class of evidence does not rank.
    const panel = anglePanel({ games: STRONG_TEN, line: 6 }, []);
    expect(panel.score).toBeUndefined();
    expect(panel.verdict).toBeUndefined();
  });
});
