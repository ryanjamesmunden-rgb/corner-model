import { roundsOf, clusterByDate, dayGap, isRealRound, roundTitle, roundRows,
         roundWindow, roundName, roundRow, roundPost, ROUND_MIN_GAMES,
         ROUND_SPAN_DAYS, ROUND_MIN_RUN, ROUND_MAX_ROWS } from "./leagueRound";
import { fitsInAPost, fitToPost } from "./xLimit";

const streak = (team, line, run, extra = {}) => ({
  team, line, line_label: `${line}+`, run, subject: "team", direction: "over",
  venue: "home", margin: 1.5, ...extra,
});

const game = (home, away, day, extra = {}) => ({
  fixture_id: `${home}-${away}`, home, away, day,
  date: `${day}T15:00:00+00:00`, round: "Round 12", ...extra,
});

/** A game carrying one qualifying run on the home side. */
const withRun = (home, away, day, line, run, extra = {}) => {
  const s = streak(home, line, run, extra.streakExtra || {});
  return { ...game(home, away, day, extra), streak: s, streaks: [s], streak_count: 1 };
};

const tree = (games, { league = "eng-ch", name = "Championship",
                       country = "England" } = {}) => ([
  { country, count: games.length, leagues: [
    { league_id: league, name, is_cup: false, count: games.length, games },
  ] },
]);


describe("counting the days", () => {
  it("is whole days between two dates", () => {
    expect(dayGap("2026-10-10", "2026-10-13")).toBe(3);
    expect(dayGap("2026-10-10", "2026-10-10")).toBe(0);
  });

  it("is not moved by a clock change", () => {
    // Taken at midnight local, a BST-to-GMT boundary shifts this by one and a Friday-to-
    // Monday cluster silently becomes a five-day one.
    expect(dayGap("2026-10-24", "2026-10-27")).toBe(3);
    expect(dayGap("2026-03-27", "2026-03-30")).toBe(3);
  });

  it("survives rubbish", () => {
    expect(dayGap(null, "2026-10-10")).toBeNull();
    expect(dayGap("nope", "2026-10-10")).toBeNull();
  });
});


describe("what counts as a round label", () => {
  // Keyed on the label, every fixture carrying the fallback would merge into one giant
  // fake round spanning the whole window.
  it("the provider's fallbacks are not rounds", () => {
    expect(isRealRound("Upcoming")).toBe(false);
    expect(isRealRound("Upcoming Round")).toBe(false);
    expect(isRealRound("upcoming")).toBe(false);
    expect(isRealRound("")).toBe(false);
    expect(isRealRound(null)).toBe(false);
  });

  it("a real one is", () => {
    expect(isRealRound("Round 12")).toBe(true);
    expect(isRealRound("Quarter-finals")).toBe(true);
  });

  it("a cluster is titled only when every game agrees", () => {
    const g = [game("A", "B", "2026-10-10"), game("C", "D", "2026-10-11")];
    expect(roundTitle(g)).toBe("Round 12");
    g[1].round = "Round 13";
    expect(roundTitle(g)).toBe("");
  });

  it("and never titled after a fallback", () => {
    const g = [game("A", "B", "2026-10-10", { round: "Upcoming" }),
               game("C", "D", "2026-10-11", { round: "Upcoming" })];
    expect(roundTitle(g)).toBe("");
  });
});


describe("clustering by date", () => {
  it("a weekend is one cluster", () => {
    const cs = clusterByDate([game("A", "B", "2026-10-10"),
                              game("C", "D", "2026-10-11"),
                              game("E", "F", "2026-10-12")]);
    expect(cs).toHaveLength(1);
    expect(cs[0]).toHaveLength(3);
  });

  it("a weekend and a midweek round are two", () => {
    // Two posting moments, not one five-day blur.
    const cs = clusterByDate([game("A", "B", "2026-10-10"),
                              game("C", "D", "2026-10-11"),
                              game("E", "F", "2026-10-14")]);
    expect(cs.map((c) => c.length)).toEqual([2, 1]);
  });

  it("the span is calendar days INCLUSIVE", () => {
    // ROUND_SPAN_DAYS of 4 means Fri to Mon — a gap of three. At a gap of four this
    // passes and the "round" is Friday to Tuesday, which is not a weekend. This is the
    // whole off-by-one risk in the file.
    const span = (gap) => clusterByDate([
      game("A", "B", "2026-10-10"),
      game("C", "D", dayPlus("2026-10-10", gap)),
    ]).length;
    expect(span(ROUND_SPAN_DAYS - 1)).toBe(1);
    expect(span(ROUND_SPAN_DAYS)).toBe(2);
  });

  it("does not depend on the order it was handed", () => {
    const shuffled = [game("E", "F", "2026-10-12"), game("A", "B", "2026-10-10"),
                      game("C", "D", "2026-10-11")];
    expect(clusterByDate(shuffled)).toHaveLength(1);
    expect(clusterByDate(shuffled)[0][0].day).toBe("2026-10-10");
  });

  it("drops a game with no day rather than clustering it at the epoch", () => {
    expect(clusterByDate([game("A", "B", "2026-10-10"),
                          { ...game("C", "D", "2026-10-11"), day: null }]))
      .toEqual([[expect.objectContaining({ day: "2026-10-10" })]]);
  });

  it("survives an empty payload", () => {
    expect(clusterByDate([])).toEqual([]);
    expect(clusterByDate()).toEqual([]);
  });
});

const dayPlus = (iso, n) => {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};


describe("which rounds qualify", () => {
  const four = (day = "2026-10-10") => [
    withRun("Reading", "Hull", day, 6, 8),
    withRun("Barnsley", "Wigan", day, 5, 6),
    withRun("Cardiff", "Derby", dayPlus(day, 1), 5, 5),
    withRun("Stoke", "Luton", dayPlus(day, 1), 5, 7),
  ];

  it("four games inside the window is a round", () => {
    const rs = roundsOf(tree(four()));
    expect(rs).toHaveLength(1);
    expect(rs[0].games).toHaveLength(4);
    expect(rs[0].league_name).toBe("Championship");
    expect(rs[0].country).toBe("England");
  });

  it("three is not", () => {
    expect(roundsOf(tree(four().slice(0, 3)))).toEqual([]);
    expect(ROUND_MIN_GAMES).toBe(4);
  });

  it("the span is reported inclusively", () => {
    const rs = roundsOf(tree(four()));
    expect(rs[0].first).toBe("2026-10-10");
    expect(rs[0].last).toBe("2026-10-11");
    expect(rs[0].span).toBe(2);
  });

  it("soonest first, not biggest first", () => {
    // The list is a schedule of posting moments; a bigger round a week out can wait, and
    // posting it early spends it.
    const soon = four("2026-10-10").slice(0, 4);
    const big = [...four("2026-10-17"), withRun("Hull", "Reading", "2026-10-17", 5, 9)];
    const rs = roundsOf(tree([...big, ...soon]));
    expect(rs.map((r) => r.first)).toEqual(["2026-10-10", "2026-10-17"]);
    expect(rs[1].games.length).toBeGreaterThan(rs[0].games.length);
  });

  it("two leagues on the same weekend are two rounds", () => {
    const t = [
      ...tree(four(), { league: "eng-ch", name: "Championship" }),
      ...tree(four(), { league: "ger-b2", name: "2. Bundesliga", country: "Germany" }),
    ];
    expect(roundsOf(t).map((r) => r.league_id).sort()).toEqual(["eng-ch", "ger-b2"]);
  });

  it("a round with a full card and no long run still qualifies, and says so", () => {
    // Otherwise it renders as an empty card, which looks like a loading failure.
    const flat = four().map((g) => ({ ...g, streak: null, streaks: [] }));
    const rs = roundsOf(tree(flat));
    expect(rs).toHaveLength(1);
    expect(rs[0].run_count).toBe(0);
    expect(rs[0].rows).toEqual([]);
  });

  it("survives an empty payload", () => {
    expect(roundsOf([])).toEqual([]);
    expect(roundsOf()).toEqual([]);
    expect(roundsOf([{ country: "X" }])).toEqual([]);
  });
});


describe("one row per game", () => {
  // A single fixture can carry six qualifying runs across three subjects and two venues,
  // so a post ranked purely by run length would be one game listed six times.
  it("a game with four runs contributes one row", () => {
    const g = withRun("Reading", "Hull", "2026-10-10", 6, 8);
    g.streaks = [streak("Reading", 6, 8), streak("Reading", 5, 8),
                 streak("Hull", 4, 7, { subject: "conceded" }),
                 streak("Reading", 19, 6, { subject: "match" })];
    g.streak_count = 4;
    expect(roundRows([g])).toHaveLength(1);
  });

  it("takes the server's own best, not a second ranking", () => {
    const g = withRun("Reading", "Hull", "2026-10-10", 6, 8);
    g.streak = streak("Reading", 6, 8);
    g.streaks = [streak("Reading", 5, 9)];      // longer, but not what the server picked
    expect(roundRows([g])[0].line).toBe(6);
  });

  it("falls back to the first of the list when there is no headline", () => {
    const g = withRun("Reading", "Hull", "2026-10-10", 6, 8);
    g.streak = null;
    expect(roundRows([g])[0].line).toBe(6);
  });

  it("drops a run shorter than the floor", () => {
    expect(roundRows([withRun("A", "B", "2026-10-10", 6, ROUND_MIN_RUN - 1)]))
      .toEqual([]);
    expect(roundRows([withRun("A", "B", "2026-10-10", 6, ROUND_MIN_RUN)]))
      .toHaveLength(1);
  });

  it("names the opponent, from whichever side the run belongs to", () => {
    const home = roundRows([withRun("Reading", "Hull", "2026-10-10", 6, 8)])[0];
    expect(home.opponent).toBe("Hull");
    const g = game("Reading", "Hull", "2026-10-10");
    const away = roundRows([{ ...g, streak: streak("Hull", 6, 8),
                              streaks: [streak("Hull", 6, 8)] }])[0];
    expect(away.opponent).toBe("Reading");
  });

  it("longest run first, margin breaking the tie", () => {
    const rows = roundRows([
      withRun("A", "B", "2026-10-10", 5, 6, { streakExtra: { margin: 0.4 } }),
      withRun("C", "D", "2026-10-10", 5, 9),
      withRun("E", "F", "2026-10-10", 5, 6, { streakExtra: { margin: 3.2 } }),
    ]);
    expect(rows.map((r) => r.team)).toEqual(["C", "E", "A"]);
  });
});


describe("naming the round", () => {
  const four = [
    withRun("Reading", "Hull", "2026-10-10", 6, 8),
    withRun("Barnsley", "Wigan", "2026-10-10", 5, 6),
    withRun("Cardiff", "Derby", "2026-10-11", 5, 5),
    withRun("Stoke", "Luton", "2026-10-12", 5, 7),
  ];

  it("the window is short weekdays", () => {
    const r = roundsOf(tree(four))[0];
    expect(roundWindow(r)).toBe("Sat–Mon");
  });

  it("a one-day round is one weekday, not a range to itself", () => {
    const same = four.map((g) => ({ ...g, day: "2026-10-10",
                                    date: "2026-10-10T15:00:00+00:00" }));
    expect(roundWindow(roundsOf(tree(same))[0])).toBe("Sat");
  });

  it("the name carries the round where one owns the window", () => {
    expect(roundName(roundsOf(tree(four))[0])).toBe("Championship, Round 12");
  });

  it("and is the league alone where none does", () => {
    const mixed = four.map((g, i) => ({ ...g, round: i ? "Round 13" : "Round 12" }));
    expect(roundName(roundsOf(tree(mixed))[0])).toBe("Championship");
  });

  it("survives an empty round", () => {
    expect(roundWindow(null)).toBe("");
    expect(roundWindow({})).toBe("");
    expect(roundName(null)).toBe("");
  });
});


describe("a row's wording", () => {
  it("says what the run IS, with its subject inside the phrase", () => {
    const r = roundRows([withRun("Reading", "Hull", "2026-10-10", 6, 8)])[0];
    expect(roundRow(r)).toContain("Reading win 6+");
    expect(roundRow(r)).toContain("8 in a row");
    expect(roundRow(r)).toContain("v Hull");
  });

  it("a conceded run says concede — it is the opposite bet", () => {
    // This exact bug has shipped on the browse row once: "Arsenal under 4" for a side
    // SHIPPING under four reads as backing Arsenal's own corners.
    const g = game("Arsenal", "Everton", "2026-10-10");
    const s = streak("Arsenal", 4, 6, { subject: "conceded", direction: "under",
                                        line_label: "under 4" });
    const r = roundRows([{ ...g, streak: s, streaks: [s] }])[0];
    expect(roundRow(r)).toContain("Arsenal concede under 4");
    expect(roundRow(r)).not.toBe("🚩 Arsenal under 4 · 6 in a row · v Everton");
  });

  it("a run of one is not called a run", () => {
    expect(roundRow({ team: "A", subject: "team", line_label: "5+", run: 1 }))
      .not.toContain("in a row");
  });

  it("survives a row with nothing in it", () => {
    expect(() => roundRow({})).not.toThrow();
    expect(() => roundRow(undefined)).not.toThrow();
  });
});


describe("the post", () => {
  const four = [
    withRun("Reading", "Hull", "2026-10-10", 6, 8),
    withRun("Barnsley", "Wigan", "2026-10-10", 5, 6),
    withRun("Cardiff", "Derby", "2026-10-11", 5, 5),
    withRun("Stoke", "Luton", "2026-10-12", 5, 7),
  ];
  const round = () => roundsOf(tree(four))[0];

  it("heads with the league, the round and the window", () => {
    const text = roundPost({ round: round() })(ROUND_MAX_ROWS);
    expect(text).toContain("Championship, Round 12");
    expect(text).toContain("Sat–Mon");
  });

  it("counts the GAMES in the round, not the rows printed", () => {
    // Twelve games with four runs worth naming is twelve games. Printing the row count
    // as the game count undersells a full card.
    const text = roundPost({ round: round() })(2);
    expect(text).toContain("4 games");
    expect(text.split("\n").filter((l) => l.startsWith("🚩") || l.startsWith("🔥")))
      .toHaveLength(2);
  });

  it("the tail says how many it held back", () => {
    expect(roundPost({ round: round() })(2)).toContain("+2 more on the site");
    expect(roundPost({ round: round() })(ROUND_MAX_ROWS))
      .not.toContain("more on the site");
  });

  it("a round with no long run says so rather than opening an empty composer", () => {
    const flat = four.map((g) => ({ ...g, streak: null, streaks: [] }));
    const text = roundPost({ round: roundsOf(tree(flat))[0] })(ROUND_MAX_ROWS);
    expect(text).toContain("Championship");
    expect(text).toContain(`No run of ${ROUND_MIN_RUN}+`);
    expect(text.trim()).not.toBe("");
  });

  it("fits in one X post once fitToPost has had it", () => {
    // The ceiling is where the trying STARTS; the full six rows need not fit.
    const r = roundsOf(tree([...four,
      withRun("Swansea", "Millwall", "2026-10-11", 7, 6),
      withRun("Norwich", "Watford", "2026-10-11", 6, 9),
      withRun("Preston", "QPR", "2026-10-12", 5, 8)]))[0];
    const text = fitToPost(roundPost({ round: r }), ROUND_MAX_ROWS);
    expect(fitsInAPost(text)).toBe(true);
    expect(text).toContain("Championship");
  });

  it("even a single over-long row comes back, rather than nothing", () => {
    const long = [withRun("A Club With A Very Long Name Indeed Yes",
                          "Another Club Whose Name Also Runs On", "2026-10-10", 6, 8)];
    const r = { ...round(), rows: roundRows(long), games: long };
    expect(fitToPost(roundPost({ round: r }), ROUND_MAX_ROWS)).not.toBe("");
  });

  it("survives no round at all", () => {
    expect(roundPost({})(3)).toBe("");
    expect(roundPost()(3)).toBe("");
  });
});
