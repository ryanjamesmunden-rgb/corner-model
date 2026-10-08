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
  FIRE_RUN, MIN_RUN, SHARE_MIN_RUN, fixtureStreaks, markFor, streakDetail, streakHeadline,
  streakRow,
  subjectLabel, streakSummary } from "./fixtureStreaks.js";

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


// CORNERS CONCEDED. The run belongs to the defence; the bet belongs to whoever is playing
// them. Every label on this subject has to carry that inversion, because the row otherwise
// reads as its exact mirror — backing the side that has been kept quiet.
describe("a conceded run", () => {
  const conc = (over = {}) => ({
    ...row("Brighton", { subject: "conceded", line: 5, run: 6, ...over }),
    opponent: "Arsenal",
  });

  test("the subject survives instead of being normalised to 'team'", () => {
    // THE SILENT FAILURE THIS REPLACED. `subject === "match" ? "match" : "team"` turned
    // a conceded row into a team row, and `subjectLabel` then said "their own corners"
    // over a leaky defence — the opposite claim, on a row that otherwise looks right.
    expect(streakRow(conc()).subject).toBe("conceded");
    expect(subjectLabel("conceded")).toBe("corners against them");
  });

  test("an unrecognised subject still falls back to team", () => {
    expect(streakRow(row("X", { subject: "nonsense" })).subject).toBe("team");
  });

  test("the claim carries the verb", () => {
    expect(streakRow(conc()).claim).toBe("Brighton concede 5+");
  });

  test("and the other subjects read as before", () => {
    expect(streakRow(row("Derby", { line: 6 })).claim).toBe("Derby 6+");
    expect(streakRow(row("Derby", { subject: "match", line: 10 })).claim).toBe("Derby 10+");
  });

  test("the detail names who actually wins those corners", () => {
    expect(streakDetail(streakRow(conc()))).toContain("Arsenal to win them");
  });

  test("a row with no opponent says less rather than naming the wrong side", () => {
    const noOpp = { ...conc() };
    delete noOpp.opponent;
    const r = streakRow(noOpp);
    expect(r.opponent).toBeNull();
    expect(streakDetail(r)).not.toContain("to win them");
  });

  test("it sorts and keys alongside the other subjects", () => {
    const rows = fixtureStreaks([
      row("Arsenal", { subject: "team", run: 9 }),
      conc({ run: 6 }),
    ]);
    expect(rows.map((r) => r.run)).toEqual([9, 6]);
    expect(new Set(rows.map((r) => r.key)).size).toBe(2);
  });
});


// THE PANEL AND THE POST DISAGREE ON PURPOSE. On screen a reader can weigh a three-game run;
// a post is read once and scrolled, so it keeps the stricter cut. This used to be one
// threshold of five applied to both, which hid most runs from the panel entirely — and the
// conceded subject, being the newest and the rarest to reach five, almost never appeared.
describe("how short a run the panel will show", () => {
  test("three is a run on screen", () => {
    expect(MIN_RUN).toBe(3);
    expect(fixtureStreaks([row("Derby", { run: 3 })])).toHaveLength(1);
  });

  test("two is not", () => {
    expect(fixtureStreaks([row("Derby", { run: 2 })])).toEqual([]);
  });

  test("the post's floor is higher, and it is a different number", () => {
    expect(SHARE_MIN_RUN).toBe(5);
    expect(SHARE_MIN_RUN).toBeGreaterThan(MIN_RUN);
  });

  test("a conceded run of three now reaches the panel", () => {
    // The case that prompted this: five in a row at the same line on the same venue is rare,
    // so a conceded streak almost never cleared the old floor.
    const rows = fixtureStreaks([
      { ...row("Brighton", { subject: "conceded", line: 5, run: 3 }), opponent: "Arsenal" },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].claim).toBe("Brighton concede 5+");
  });
});

describe("which pool the run came from", () => {
  // The panel carries overall runs beside venue ones now. `venue` used to be
  // `s.venue === "away" ? "away" : "home"`, which did not merely lose the distinction —
  // it asserted the wrong one, relabelling every overall run as a home run.
  const of = (venue) => fixtureStreaks([row("Bodo/Glimt", { venue })])[0];

  test("an overall run is not relabelled as a home one", () => {
    expect(of("overall").venue).toBe("overall");
    expect(of("overall").venueText).toBe("home and away");
    expect(of("overall").venueTag).toBe("Overall");
  });

  test("the venues still say what they always said", () => {
    expect(of("home").venueText).toBe("at home");
    expect(of("away").venueText).toBe("away");
  });

  test("an unknown venue falls back rather than inventing one", () => {
    expect(of("mars").venue).toBe("home");
  });

  test("the detail line reads properly for each", () => {
    expect(streakDetail(of("overall"))).toContain("their own corners home and away");
    expect(streakDetail(of("home"))).toContain("their own corners at home");
  });

  test("two rows that differ only by pool get different keys", () => {
    // Without the venue in the key these collide: React renders duplicate keys and the
    // rows stop being reliably distinct — the same bug as the label, in other clothes.
    const rows = fixtureStreaks([
      row("Bodo/Glimt", { venue: "home", run: 9 }),
      row("Bodo/Glimt", { venue: "overall", run: 14 }),
    ]);
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((r) => r.key)).size).toBe(2);
  });
});

describe("the summary of what is running in", () => {
  // The list answers "what is running" and answers "how much, and whose" only by being
  // counted by hand. A busy fixture now carries ten or twelve rows.
  const rows = () => fixtureStreaks([
    row("Bodo/Glimt", { subject: "team", run: 9, venue: "home" }),
    row("Bodo/Glimt", { subject: "team", run: 4, venue: "overall" }),
    row("Bodo/Glimt", { subject: "match", run: 6, venue: "home" }),
    row("Kristiansund BK", { subject: "conceded", run: 5, venue: "away" }),
    row("Kristiansund BK", { subject: "team", run: 3, venue: "away",
                             direction: "under" }),
  ]);

  test("nothing running is no summary, not a row of zeros", () => {
    expect(streakSummary([])).toBeNull();
  });

  test("the total counts every row the panel shows", () => {
    // A summary filtered differently from the list underneath is a number the reader
    // cannot reconcile with what they can see — and they will trust the number.
    const s = streakSummary(rows());
    expect(s.total).toBe(5);
    expect(s.total).toBe(rows().length);
  });

  test("it splits by team, busiest first", () => {
    expect(streakSummary(rows()).byTeam).toEqual([
      { key: "Bodo/Glimt", n: 3 }, { key: "Kristiansund BK", n: 2 },
    ]);
  });

  test("and by subject, in a fixed order so the block does not reshuffle", () => {
    expect(streakSummary(rows()).bySubject).toEqual([
      { key: "team", n: 3, label: "Corners won" },
      { key: "conceded", n: 1, label: "Corners against" },
      { key: "match", n: 1, label: "Match totals" },
    ]);
  });

  test("the venue split is there so the total can be read correctly", () => {
    // Several rows are the same side over two overlapping pools. Without this the total
    // reads as that many independent findings.
    expect(streakSummary(rows()).byVenue).toEqual([
      { key: "home", n: 2 }, { key: "away", n: 2 }, { key: "overall", n: 1 },
    ]);
  });

  test("overs and unders are counted apart", () => {
    const s = streakSummary(rows());
    expect(s.overs).toBe(4);
    expect(s.unders).toBe(1);
  });

  test("the longest run is found, not assumed to be first", () => {
    // The list happens to be sorted longest-first; a summary that depended on that would
    // break the day the order changed.
    const unsorted = [row("A", { run: 3 }), row("B", { run: 11 }), row("C", { run: 5 })]
      .map((r) => streakRow(r));
    expect(streakSummary(unsorted).longest.run).toBe(11);
  });
});
