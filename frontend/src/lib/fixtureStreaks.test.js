// The runs shown on a fixture page.
//
// THE BUG THIS FILE NOW EXISTS TO PREVENT. The first version was written against the
// STREAK BOARD's row shape — everything nested under `streak`, with a settled record and
// the last legs. `data.streaks` does not come from there: it comes from fixture_streaks,
// which is flat and carries none of that. The filter dropped every row and the panel
// rendered nothing on every fixture, which is indistinguishable from a quiet page. So
// these fixtures are built from the ENDPOINT's shape, and one of them asserts the wrong
// shape produces nothing — because that was the failure, and it was silent.
//
// The rest guard what the panel is allowed to claim:
//   - "5+" means a team's own corners OR the match total, two bets a factor of two apart.
//   - The fire meaning something different here from everywhere else.
//   - An under relabelled as an over, which loses in the opposite direction to intent.
import {
  FIRE_RUN, MIN_RUN, fixtureStreaks, markFor, streakDetail, streakHeadline, streakRow,
  subjectLabel,
} from "./fixtureStreaks.js";

/** A row exactly as backend fixture_streaks emits it — flat, from live_streak. */
const row = (team, { line = 5, run = 6, subject = "team", direction = "over",
                     venue = "home", games = 20, since = "2026-08-12" } = {}) => ({
  team, subject, direction, line,
  line_label: direction === "under" ? `under ${line}` : `${line}+`,
  run, since, venue, games,
});


describe("it reads the endpoint's shape, not the board's", () => {
  test("a real fixture_streaks row renders", () => {
    const rows = fixtureStreaks([row("Arsenal", { run: 9 })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].team).toBe("Arsenal");
    expect(rows[0].run).toBe(9);
  });

  test("the STREAK BOARD's shape yields nothing, which is the bug that shipped", () => {
    // Nested under `streak`, as /api/streaks returns. Silent when wrong — the panel just
    // does not appear, on every fixture, and looks like a quiet page.
    const boardShape = { name: "Arsenal", team_id: "eng-pl-1",
                         streak: { line: 5, line_label: "5+", length: 9 } };
    expect(fixtureStreaks([boardShape])).toEqual([]);
  });
});


describe("whose corners", () => {
  test("a team line and a match total are told apart", () => {
    // "5+" is the same two characters for a team's own corners and for the match total,
    // and the match number is roughly twice the team one.
    expect(subjectLabel("team")).toBe("their own corners");
    expect(subjectLabel("match")).toBe("in the match");
  });

  test("the detail line says which, and where", () => {
    const [r] = fixtureStreaks([row("Arsenal", { subject: "match", venue: "away" })]);
    expect(streakDetail(r)).toContain("in the match away");
  });

  test("the sample sits beside the run", () => {
    // "9 in a row" with no denominator is a claim with no scale.
    const [r] = fixtureStreaks([row("Arsenal", { games: 20 })]);
    expect(streakDetail(r)).toContain("20 games on file");
  });
});


describe("the mark", () => {
  test("it is the threshold the rest of the site uses", () => {
    expect(FIRE_RUN).toBe(8);
  });

  test("fire at the threshold, flag below it", () => {
    expect(markFor(FIRE_RUN)).toBe("🔥");
    expect(markFor(FIRE_RUN - 1)).toBe("🚩");
  });

  test("junk is a flag, not a crash or a fire", () => {
    expect(markFor(undefined)).toBe("🚩");
    expect(markFor(null)).toBe("🚩");
  });
});


describe("what reaches the panel", () => {
  test("the label comes straight from the API", () => {
    const [r] = fixtureStreaks([row("Sunderland", { direction: "under", line: 9 })]);
    expect(r.label).toBe("under 9");
    expect(r.direction).toBe("under");
  });

  test("a row below the backend's own floor is refused", () => {
    expect(fixtureStreaks([row("X", { run: MIN_RUN - 1 })])).toEqual([]);
  });

  test("a row with no label is dropped rather than guessed at", () => {
    expect(fixtureStreaks([{ team: "X", run: 9 }])).toEqual([]);
  });

  test("longest first", () => {
    const rows = fixtureStreaks([row("A", { run: 6 }), row("B", { run: 11 }),
                                 row("C", { run: 8 })]);
    expect(rows.map((r) => r.team)).toEqual(["B", "C", "A"]);
  });

  test("both sides and both directions can coexist", () => {
    // fixture_streaks emits up to eight rows: two teams x team/match x over/under.
    const rows = fixtureStreaks([
      row("Arsenal", { subject: "team", direction: "over", run: 9 }),
      row("Arsenal", { subject: "match", direction: "over", run: 7, line: 10 }),
      row("Chelsea", { subject: "team", direction: "under", run: 6, venue: "away" }),
    ]);
    expect(rows).toHaveLength(3);
    expect(new Set(rows.map((r) => r.key)).size).toBe(3);
  });

  test("an empty payload is an empty panel, not a crash", () => {
    expect(fixtureStreaks([])).toEqual([]);
    expect(fixtureStreaks()).toEqual([]);
  });
});


describe("the header", () => {
  test("it counts the runs and says how many are hot", () => {
    const rows = fixtureStreaks([row("A", { run: 11 }), row("B", { run: 6 })]);
    expect(streakHeadline(rows)).toBe("2 streaks running into this game · 1 on 8+");
  });

  test("no hot run means no claim about one", () => {
    expect(streakHeadline(fixtureStreaks([row("A", { run: 6 })])))
      .toBe("1 streak running into this game");
  });

  test("nothing running says nothing", () => {
    expect(streakHeadline([])).toBe("");
  });
});
