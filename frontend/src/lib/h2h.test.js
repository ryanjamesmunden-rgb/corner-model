import {
  MIN_FOR_AVERAGE, cornerLine, hasH2H, meetingDate, meetingRows, recordLine,
  runLabel, scoreLine, summaryLine, unbeatenRows, venueMark,
} from "./h2h";

// The payload as the backend hands it over: already oriented to the CURRENT fixture's
// home side, so nothing here flips anything.
const meeting = (over = {}) => ({
  date: "2026-02-14T15:00:00Z",
  league_id: "eng-pl",
  league_name: "Premier League",
  venue: "home",
  goals_home_team: 2,
  goals_away_team: 1,
  corners_home_team: 7,
  corners_away_team: 4,
  total_corners: 11,
  result: "home_team",
  graded: true,
  ...over,
});

const payload = (over = {}) => ({
  home_name: "Arsenal",
  away_name: "Chelsea",
  meetings: [meeting()],
  corners: { played: 1, avg_total: 11, avg_home_team: 7, avg_away_team: 4, highest: 11, lowest: 11 },
  unbeaten: { home_team: [], away_team: [] },
  record: { played: 1, home_wins: 1, draws: 0, away_wins: 0, ungraded: 0 },
  window: "...",
  ...over,
});

describe("one meeting, in words", () => {
  it("names the sides in the current fixture's order", () => {
    expect(scoreLine(meeting(), "Arsenal", "Chelsea")).toBe("Arsenal 2-1 Chelsea");
  });

  it("prints the corners with their total", () => {
    expect(cornerLine(meeting())).toBe("7-4 · 11 corners");
  });

  it("marks where it was played", () => {
    expect(venueMark(meeting())).toBe("H");
    expect(venueMark(meeting({ venue: "away" }))).toBe("A");
  });

  it("has no score line when the cache holds no goals", () => {
    // THE CASE A `?? 0` WOULD RUIN: a missing score would render as 0-0, which is a
    // fabricated draw and also reads as "unbeaten".
    const blank = meeting({ goals_home_team: null, goals_away_team: null, graded: false });
    expect(scoreLine(blank, "Arsenal", "Chelsea")).toBeNull();
    // The corners are still real and still shown.
    expect(cornerLine(blank)).toBe("7-4 · 11 corners");
  });

  it("survives a row with no corner counts rather than printing undefined", () => {
    expect(cornerLine({})).toBeNull();
  });
});

describe("the date", () => {
  it("renders as a short day", () => {
    expect(meetingDate("2026-02-14T15:00:00Z", "en-GB")).toMatch(/14 Feb 2026/);
  });

  it("is blank rather than Invalid Date when there is none", () => {
    expect(meetingDate(null)).toBe("");
    expect(meetingDate("not a date")).toBe("");
  });
});

describe("the rows the panel renders", () => {
  it("carries the competition each meeting was played in", () => {
    // A 1-1 in a league game and a 1-1 in a second leg are different facts.
    const rows = meetingRows(payload({ meetings: [meeting({ league_name: "Champions League" })] }));
    expect(rows[0].competition).toBe("Champions League");
  });

  it("falls back to the id when a competition has no name", () => {
    const rows = meetingRows(payload({ meetings: [meeting({ league_name: "", league_id: "ucl" })] }));
    expect(rows[0].competition).toBe("ucl");
  });

  it("gives every row a stable key even when two share a date", () => {
    const rows = meetingRows(payload({ meetings: [meeting(), meeting()] }));
    expect(rows[0].key).not.toBe(rows[1].key);
  });

  it("is empty for a pairing with no history", () => {
    expect(meetingRows(payload({ meetings: [] }))).toEqual([]);
    expect(meetingRows(undefined)).toEqual([]);
  });
});

describe("unbeaten runs", () => {
  it("words an overall run without a venue", () => {
    expect(runLabel({ split: "overall", run: 4, played: 4 }))
      .toBe("Unbeaten in the last 4 meetings");
  });

  it("names the venue when there is one", () => {
    expect(runLabel({ split: "home", run: 3, played: 5 }))
      .toBe("Unbeaten in the last 3 meetings at home");
    expect(runLabel({ split: "away", run: 3, played: 5 }))
      .toBe("Unbeaten in the last 3 meetings away");
  });

  it("does not say 'meetings' for one", () => {
    expect(runLabel({ split: "overall", run: 1, played: 1 }))
      .toBe("Unbeaten in the last 1 meeting");
  });

  it("tags each run with whose it is", () => {
    const rows = unbeatenRows(payload({
      unbeaten: {
        home_team: [{ split: "overall", run: 4, played: 6 }],
        away_team: [{ split: "away", run: 3, played: 3 }],
      },
    }));
    expect(rows.map((r) => [r.team, r.run])).toEqual([["Arsenal", 4], ["Chelsea", 3]]);
  });

  it("puts the longest run first", () => {
    const rows = unbeatenRows(payload({
      unbeaten: {
        home_team: [{ split: "home", run: 3, played: 3 }],
        away_team: [{ split: "overall", run: 5, played: 7 }],
      },
    }));
    expect(rows[0].run).toBe(5);
  });

  it("carries what the run was out of", () => {
    // 3 from 3 and 3 from 9 are different claims and the short one sounds strongest.
    const rows = unbeatenRows(payload({
      unbeaten: { home_team: [{ split: "overall", run: 3, played: 9 }], away_team: [] },
    }));
    expect(rows[0].played).toBe(9);
  });

  it("is empty when neither side has one worth printing", () => {
    expect(unbeatenRows(payload())).toEqual([]);
  });
});

describe("the record", () => {
  it("reads as each side's wins and the draws between", () => {
    const h = payload({ record: { played: 6, home_wins: 3, draws: 1, away_wins: 2, ungraded: 0 } });
    expect(recordLine(h, "Arsenal", "Chelsea")).toBe("Arsenal 3 · 1 drawn · Chelsea 2 — 6 played");
  });

  it("is absent rather than 0-0-0 when nothing is graded", () => {
    // "0 · 0 drawn · 0" reads as three goalless draws, not as an absence of results.
    const h = payload({ record: { played: 0, home_wins: 0, draws: 0, away_wins: 0, ungraded: 2 } });
    expect(recordLine(h, "Arsenal", "Chelsea")).toBeNull();
  });
});

describe("the collapsed header", () => {
  it("leads with the corner average, which is what the site is for", () => {
    const h = payload({
      meetings: [meeting(), meeting()],
      corners: { played: 2, avg_total: 10.5, avg_home_team: 6, avg_away_team: 4.5, highest: 11, lowest: 10 },
    });
    expect(summaryLine(h)).toMatch(/^10.5 corners a game over 2 meetings/);
  });

  it("adds the strongest unbeaten run after it", () => {
    const h = payload({
      meetings: [meeting(), meeting()],
      corners: { played: 2, avg_total: 10.5, avg_home_team: 6, avg_away_team: 4.5, highest: 11, lowest: 10 },
      unbeaten: { home_team: [{ split: "overall", run: 4, played: 4 }], away_team: [] },
    });
    expect(summaryLine(h)).toBe("10.5 corners a game over 2 meetings · Arsenal unbeaten in 4");
  });

  it("counts the meetings instead of averaging one of them", () => {
    // One game is not a rate, and "11 corners a game" off a single meeting is the kind of
    // number that gets quoted back.
    const h = payload({ corners: { played: 1, avg_total: 11, avg_home_team: 7, avg_away_team: 4, highest: 11, lowest: 11 } });
    expect(MIN_FOR_AVERAGE).toBe(2);
    expect(summaryLine(h)).toBe("1 meeting on file");
  });

  it("says plainly when there is no history", () => {
    expect(summaryLine(payload({ meetings: [], corners: null }))).toBe("No meetings on file");
  });
});

describe("whether to render at all", () => {
  it("is true with meetings and false without", () => {
    expect(hasH2H(payload())).toBe(true);
    expect(hasH2H(payload({ meetings: [] }))).toBe(false);
    expect(hasH2H(undefined)).toBe(false);
  });
});
