import {
  WEEKDAYS, PAST, TODAY, UPCOMING, UNKNOWN, OUTSIDE,
  parseDay, monthGrid, squareState, buildMonth, monthLabel, shiftMonth, canShift, mineLabel,
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

  it("says how many of my teams play, with the plural right", () => {
    expect(mineLabel({ mine: [game()] })).toBe("1 game");
    expect(mineLabel({ mine: [game(), game()] })).toBe("2 games");
    expect(mineLabel({ mine: [] })).toBe("");
    expect(mineLabel({})).toBe("");
  });

  it("parses a day key and refuses a bad one", () => {
    expect(parseDay("2026-11-14")).toEqual({ y: 2026, m: 11, d: 14 });
    expect(parseDay("2026-13-01")).toBeNull();
    expect(parseDay("")).toBeNull();
  });
});
