import {
  WEEKDAYS, PAST, TODAY, UPCOMING, UNKNOWN, OUTSIDE,
  parseDay, monthGrid, squareState, buildMonth, monthLabel, shiftMonth, canShift, mineLabel,
  dayLabel, emptyNote, mineDetail,
} from "./calendarMonth";

const game = (over = {}) => ({
  fixture_id: "f1", team_id: "t1", team: "Vila Nova", side: "away",
  list: "favourites", home_name: "Fortaleza", away_name: "Vila Nova",
  opponent: "Fortaleza", league_id: "bra-sb", league_name: "Serie B",
  kickoff: "2026-11-14T22:30:00+00:00", ...over,
});

const payload = (over = {}) => ({
  month: "2026-11", from: "2026-11-01", to: "2026-11-30",
  today: "2026-11-13", zone: "Europe/London", horizon: "2026-11-23",
  days: [
    { date: "2026-11-13", fixtures: 12, leagues: 5, mine: [] },
    { date: "2026-11-14", fixtures: 40, leagues: 9, mine: [game()] },
    { date: "2026-11-15", fixtures: 31, leagues: 8, mine: [game({ team: "Burton" }),
                                                           game({ team: "Oviedo" })] },
    { date: "2026-11-23", fixtures: 4, leagues: 2, mine: [] },
  ],
  ...over,
});

describe("the grid", () => {
  it("starts the week on Monday, as a football week is read", () => {
    // A weekend is Saturday and Sunday together at the end of a row, not split in two.
    expect(WEEKDAYS[0]).toBe("Mon");
    expect(WEEKDAYS[5]).toBe("Sat");
    expect(WEEKDAYS[6]).toBe("Sun");
  });

  it("leads in from the Monday before the first of the month", () => {
    // 1 Nov 2026 is a Sunday, so the row starts on 26 Oct.
    const keys = monthGrid("2026-11");
    expect(keys[0]).toBe("2026-10-26");
    expect(keys[6]).toBe("2026-11-01");
  });

  it("covers every day of the month", () => {
    const keys = monthGrid("2026-11");
    expect(keys).toContain("2026-11-01");
    expect(keys).toContain("2026-11-30");
    expect(keys.length % 7).toBe(0);
  });

  it("needs no lead-in for a month that starts on a Monday", () => {
    // 1 June 2026 is a Monday.
    expect(monthGrid("2026-06")[0]).toBe("2026-06-01");
  });

  it("drops a trailing row that holds none of the month", () => {
    // February 2027 starts on a Monday and has 28 days: four full rows, and a fifth and
    // sixth of nothing. Keeping them would put two empty bands under the month.
    const keys = monthGrid("2027-02");
    expect(keys).toHaveLength(28);
    expect(keys[27]).toBe("2027-02-28");
  });

  it("survives a month containing a daylight-saving change", () => {
    // THE BUG THIS AVOIDS. Local-time Date arithmetic across a DST boundary can land on
    // the same calendar day twice or skip one, which silently duplicates or loses a
    // square. October 2026 contains the UK clock change.
    const keys = monthGrid("2026-10");
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys).toContain("2026-10-25");
    expect(keys).toContain("2026-10-26");
  });

  it("answers empty for nonsense rather than drawing something", () => {
    expect(monthGrid("")).toEqual([]);
    expect(monthGrid("2026-13")).toEqual([]);
    expect(monthGrid("November")).toEqual([]);
  });
});

describe("what a square means", () => {
  const opts = { month: "2026-11", today: "2026-11-13", horizon: "2026-11-23" };

  it("marks today, the past and what is coming", () => {
    expect(squareState("2026-11-13", opts)).toBe(TODAY);
    expect(squareState("2026-11-12", opts)).toBe(PAST);
    expect(squareState("2026-11-20", { ...opts, fixtures: 9 })).toBe(UPCOMING);
  });

  it("greys a day past where the fixture list reaches", () => {
    // THE WHOLE REASON THIS FILE EXISTS. An empty Saturday in three weeks is "nobody has
    // published it yet", not "a free weekend", and drawing them the same way invents one.
    expect(squareState("2026-11-28", opts)).toBe(UNKNOWN);
  });

  it("never calls a day with games on it unknown, however far out", () => {
    expect(squareState("2026-11-28", { ...opts, fixtures: 2 })).toBe(UPCOMING);
  });

  it("treats a day inside the horizon with no games as a real free day", () => {
    expect(squareState("2026-11-17", opts)).toBe(UPCOMING);
  });

  it("falls back to upcoming when the horizon is not known", () => {
    // Better to under-claim than to grey the whole month out on a missing field.
    expect(squareState("2026-11-28", { ...opts, horizon: null })).toBe(UPCOMING);
  });

  it("marks the lead-in and lead-out days as outside", () => {
    expect(squareState("2026-10-26", opts)).toBe(OUTSIDE);
    expect(squareState("2026-12-01", opts)).toBe(OUTSIDE);
  });
});

describe("building the month", () => {
  const built = buildMonth(payload());

  it("lays the squares out in weeks of seven", () => {
    expect(built.weeks.every((w) => w.length === 7)).toBe(true);
    expect(built.squares).toHaveLength(built.weeks.length * 7);
  });

  it("hangs each day's games on its own square", () => {
    const sat = built.squares.find((s) => s.key === "2026-11-14");
    expect(sat.fixtures).toBe(40);
    expect(sat.mine).toHaveLength(1);
    expect(sat.mine[0].team).toBe("Vila Nova");
  });

  it("leaves a day the endpoint said nothing about empty rather than undefined", () => {
    const quiet = built.squares.find((s) => s.key === "2026-11-17");
    expect(quiet.fixtures).toBe(0);
    expect(quiet.mine).toEqual([]);
  });

  it("counts how much of the month the fixture list does not reach", () => {
    // Said as a number because four greyed squares at the end of a row are easy to miss.
    // The horizon is the 23rd, so the 24th to the 30th are unknown.
    expect(built.unknownDays).toBe(7);
  });

  it("totals my games and every fixture in the month", () => {
    expect(built.mineCount).toBe(3);
    expect(built.fixtureCount).toBe(87);
  });

  it("finds the day most of my teams play", () => {
    expect(built.busiest.key).toBe("2026-11-15");
    expect(built.busiest.mine).toHaveLength(2);
  });

  it("answers null for a payload it cannot draw", () => {
    expect(buildMonth({})).toBeNull();
    expect(buildMonth()).toBeNull();
    expect(buildMonth({ month: "nope" })).toBeNull();
  });

  it("draws an empty month rather than nothing at all", () => {
    const bare = buildMonth({ month: "2026-11", today: "2026-11-13", days: [] });
    expect(bare.mineCount).toBe(0);
    expect(bare.squares.length).toBeGreaterThan(27);
  });
});

describe("stepping between months", () => {
  it("moves forward and back across a year boundary", () => {
    expect(shiftMonth("2026-11", 1)).toBe("2026-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-11", 0)).toBe("2026-11");
  });

  it("refuses a step the endpoint would reject", () => {
    // The endpoint 400s outside its window, so an arrow that offers the step would only
    // ever produce an error.
    const at = { today: "2026-11-13", back: 2, ahead: 3 };
    expect(canShift("2027-02", 1, at)).toBe(false);   // four ahead
    expect(canShift("2027-01", 1, at)).toBe(true);    // three ahead
    expect(canShift("2026-09", -1, at)).toBe(false);  // three back
    expect(canShift("2026-10", -1, at)).toBe(true);   // two back
  });

  it("refuses rather than throwing when it does not know today", () => {
    expect(canShift("2026-11", 1, {})).toBe(false);
  });
});

describe("labels", () => {
  it("spells the month out rather than leaving it to the runtime", () => {
    // recordCard.js has the note: toLocaleDateString does not agree between a browser and
    // the Actions runner, and a label that changes by machine cannot be checked.
    expect(monthLabel("2026-11")).toBe("November 2026");
    expect(monthLabel("2027-01")).toBe("January 2027");
    expect(monthLabel("bad")).toBe("");
  });

  it("says why a game is on your calendar, and a saved one has no side", () => {
    // A saved game was starred as a FIXTURE, so it has no team and no side. Sent through
    // the team branch it rendered a stray " away" hanging off the league name.
    expect(mineDetail({ list: "saved" })).toBe("saved game");
    expect(mineDetail({ list: "favourites", team: "Vila Nova", side: "home" }))
      .toBe("Vila Nova at home");
    expect(mineDetail({ list: "favourites", team: "Fortaleza", side: "away" }))
      .toBe("Fortaleza away");
    expect(mineDetail({ list: "tracking", team: "Mirassol", side: "home" }))
      .toBe("Mirassol at home · tracking");
    expect(mineDetail({})).toBe("");
  });

  it("points at the bell, which is the control that fills this page", () => {
    // The star saves a GAME and the bell follows a TEAM — TeamStar's own note says so.
    // The empty state used to send people to the star, which fills the other list.
    const note = emptyNote({ teams: [] }, "November 2026");
    expect(note).toContain("🔔");
    expect(note).not.toContain("☆");
  });

  it("says how many of my teams play, with the plural right", () => {
    expect(mineLabel({ mine: [game()] })).toBe("1 game");
    expect(mineLabel({ mine: [game(), game()] })).toBe("2 games");
    expect(mineLabel({ mine: [] })).toBe("");
    expect(mineLabel({})).toBe("");
  });

  it("names the day a square stands for, weekday first", () => {
    // Monday-first, so Sunday must come out last rather than as the week's head.
    expect(dayLabel("2026-11-21")).toBe("Sat 21 November");
    expect(dayLabel("2026-11-23")).toBe("Mon 23 November");
    expect(dayLabel("2026-11-22")).toBe("Sun 22 November");
    expect(dayLabel("2027-01-01")).toBe("Fri 1 January");
    expect(dayLabel("nonsense")).toBe("");
  });

  it("never names a different day from the key it was given", () => {
    // THE BUG THIS GUARDS. The panel used to print the raw key, and the obvious repair —
    // `new Date(key).toLocaleDateString()` — is the other way to get it wrong: the keys
    // are UK calendar days, `new Date("2026-11-21")` is UTC midnight, and west of London
    // that formats as the 20th. The panel would then name a different day from the square
    // the reader had just tapped. Every day of a month, label's number against key's.
    for (const key of monthGrid("2026-11")) {
      expect(dayLabel(key).split(" ")[1]).toBe(String(Number(key.slice(8, 10))));
    }
  });

  it("tells 'you follow nobody' apart from 'they are not playing'", () => {
    // THE BUG. An empty grid used to print "No teams followed yet" either way — a claim
    // about the account, made without looking at it. Someone following six sides was told
    // to go and star some.
    expect(emptyNote({ teams: [] }, "November 2026"))
      .toMatch(/^No teams followed yet/);
    expect(emptyNote({}, "November 2026")).toMatch(/^No teams followed yet/);

    const note = emptyNote({ teams: [{ name: "Vila Nova" }, { name: "Fortaleza" }] },
                           "November 2026");
    expect(note).toBe("Following 2 teams (Vila Nova, Fortaleza) — none of them play "
                      + "in November 2026.");
  });

  it("names a few of the followed teams rather than all of them", () => {
    const teams = ["A", "B", "C", "D", "E"].map((name) => ({ name }));
    expect(emptyNote({ teams }, "")).toBe("Following 5 teams (A, B, C and 2 more) — "
                                          + "none of them play.");
    expect(emptyNote({ teams: [{ name: "Solo" }] }, "")).toBe(
      "Following 1 team (Solo) — none of them play.");
  });

  it("still counts a followed team the teams list has no name for", () => {
    // A followed id missing from db.teams comes back nameless. It is still somebody's
    // team and still the reason the grid is empty, so it must not vanish from the count.
    expect(emptyNote({ teams: [{ team_id: "x" }, { team_id: "y" }] }, "November 2026"))
      .toBe("Following 2 teams — none of them play in November 2026.");
  });

  it("parses a day key and refuses a bad one", () => {
    expect(parseDay("2026-11-14")).toEqual({ y: 2026, m: 11, d: 14 });
    expect(parseDay("2026-13-01")).toBeNull();
    expect(parseDay("")).toBeNull();
  });
});
