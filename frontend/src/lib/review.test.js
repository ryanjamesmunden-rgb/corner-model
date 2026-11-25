import { gameRow, gameRows, headline, keyLabel, lastTimeText, lineText,
         RESULT_WORD, scoreline } from "./review";

const line = (over = {}) => ({ key: "home_over_4.5", group: "home", direction: "over",
                               line: 4.5, value: 7, result: "won", book_odds: 1.8,
                               prob: 68, fair_odds: 1.47, ev: 22.4, profit: 0.8, ...over });

const game = (over = {}) => ({
  fixture_id: "fx1", date: "2026-11-21T15:00:00Z", league_name: "League One",
  home_name: "Bradford", away_name: "Barnsley",
  home_corners: 7, away_corners: 4, total_corners: 11, corners_known: true,
  lines: [line(), line({ key: "total_over_9.5", ev: -4, result: "won", profit: 1.1 })],
  priced: 2, ev_plus: 1, ev_plus_landed: 1, ev_plus_profit: 0.8, ...over,
});

describe("the week's headline", () => {
  const data = (over = {}) => ({ days: 7, fixtures: 12, graded: 10, awaiting_corners: 2,
                                 lines: 180, ev_plus: 40, ev_plus_landed: 23,
                                 ev_plus_settled: 38, ev_plus_rate: 60.5,
                                 ev_plus_profit: 4.2, ...over });

  it("leads with the +EV rate, not the rate across the whole ladder", () => {
    // A 2+ team line at 1.07 lands almost always; a hit rate including it describes the
    // ladder and flatters the model.
    const h = headline(data());
    expect(h.rate).toBe(60.5);
    expect(h.evPlus).toBe(40);
    expect(h.lines).toBe(180);
  });

  it("refuses a rate until something has settled", () => {
    expect(headline(data({ ev_plus_settled: 0, ev_plus_rate: 0 })).rate).toBeNull();
  });

  it("separates games waiting on a corner count from games that were graded", () => {
    const h = headline(data());
    expect(h.graded).toBe(10) && expect(h.awaiting).toBe(2);
  });

  it("keeps an unknown profit null rather than calling it zero", () => {
    // A winner at a price nobody stored has no computable return.
    expect(headline(data({ ev_plus_profit: null })).profit).toBeNull();
  });

  it("survives an empty week", () => {
    expect(headline({}).games).toBe(0);
    expect(headline(undefined).rate).toBeNull();
  });
});

describe("one reviewed game", () => {
  it("leads with the lines the model called value, biggest edge first", () => {
    const row = gameRow(game({ lines: [line({ ev: 4 }), line({ key: "a", ev: 30 })] }));
    expect(row.evLines.map((l) => l.ev)).toEqual([30, 4]);
  });

  it("keeps the rest rather than hiding them", () => {
    // A review showing only the lines it liked can never show the model being wrong about
    // which line to like.
    const row = gameRow(game());
    expect(row.evLines).toHaveLength(1);
    expect(row.otherLines).toHaveLength(1);
    expect(row.otherLines[0].key).toBe("total_over_9.5");
  });

  it("treats a zero edge as not value", () => {
    expect(gameRow(game({ lines: [line({ ev: 0 })] })).evLines).toHaveLength(0);
  });

  it("says the corner count is missing rather than printing nil-nil", () => {
    const row = gameRow(game({ home_corners: null, away_corners: null,
                               total_corners: null, corners_known: false }));
    expect(scoreline(row)).toBe("corner count not in yet");
  });

  it("reads the score as corners, which is what the page is about", () => {
    expect(scoreline(gameRow(game()))).toBe("7-4, 11 corners");
  });

  it("survives a game nobody priced", () => {
    const row = gameRow(game({ lines: [], priced: 0, ev_plus: 0 }));
    expect(row.evLines).toEqual([]) && expect(row.otherLines).toEqual([]);
    expect(row.home).toBe("Bradford");
  });

  it("maps a whole payload, and an empty one", () => {
    expect(gameRows({ games: [game(), game()] })).toHaveLength(2);
    expect(gameRows({})).toEqual([]);
    expect(gameRows(null)).toEqual([]);
  });
});

describe("a line in words", () => {
  it("always prints the price beside the result", () => {
    // "It landed" without the number is the half of the fact that invites the reader to
    // supply the other half from memory.
    expect(lineText(line())).toBe("Home over 4.5 @ 1.80 — landed (+0.80u)");
  });

  it("says missed as plainly as landed", () => {
    expect(lineText(line({ result: "lost", profit: -1 })))
      .toBe("Home over 4.5 @ 1.80 — missed (-1.00u)");
  });

  it("names a push rather than calling it a loss", () => {
    expect(RESULT_WORD.void).toBe("push");
    expect(lineText(line({ result: "void", profit: 0 }))).toContain("push");
  });

  it("drops the money when the return cannot be computed", () => {
    expect(lineText(line({ profit: null }))).toBe("Home over 4.5 @ 1.80 — landed");
  });

  it("labels every market shape the stores hold", () => {
    expect(keyLabel("home_over_4.5")).toBe("Home over 4.5");
    expect(keyLabel("total_under_9.5")).toBe("Match under 9.5");
    expect(keyLabel("both_over_3.5")).toBe("Both teams over 3.5");
    expect(keyLabel("something_else")).toBe("something_else");
  });
});

describe("what the line did last time", () => {
  it("names the result and the price it was offered at", () => {
    expect(lastTimeText({ last: { result: "won", book_odds: 1.62 }, found: 1, landed: 1 }))
      .toBe("Last time landed at 1.62");
  });

  it("adds the run once there is more than one to count", () => {
    expect(lastTimeText({ last: { result: "lost", book_odds: 1.75 }, found: 4, landed: 2 }))
      .toBe("Last time missed at 1.75 · 2 of the last 4");
  });

  it("is null when the line has never been priced on this team", () => {
    // Never priced and never landed are different facts, and an empty string reads as
    // the second.
    expect(lastTimeText({ last: null, found: 0, landed: 0 })).toBeNull();
    expect(lastTimeText(null)).toBeNull();
  });

  it("handles a stored result with no price attached", () => {
    expect(lastTimeText({ last: { result: "won", book_odds: null }, found: 1, landed: 1 }))
      .toBe("Last time landed");
  });
});
