import { emptyText, gameRow, gameRows, hasForm, summaryText } from "./competitionForm";

// A Champions League page that lists Serie A games answers the wrong question. These are
// the European games, and the sample is small enough that how it is worded matters more
// than usual.

const game = (over = {}) => ({
  fixture_id: "ucl-9", date: "2026-11-03T20:00:00Z", round: "League Stage - 4",
  opponent: "Feyenoord", home: false, won: 4, conceded: 5, total: 9,
  gf: 1, ga: 2, finished_as: "FT", ...over,
});

const form = (games, summary) => ({ games, summary });

describe("one game as a row", () => {
  it("reads the corners from this side's point of view", () => {
    // `won` arrives already resolved to this team whichever end it was at.
    expect(gameRow(game())).toMatchObject({ won: 4, conceded: 5, corners: "4-5" });
  });

  it("says which end of the tie it was", () => {
    expect(gameRow(game()).venue).toBe("A");
    expect(gameRow(game({ home: true })).venue).toBe("H");
  });

  it("dates it in UK time, so a 20:00 kick-off is filed where the reader expects", () => {
    expect(gameRow(game()).when).toBe("3 Nov");
  });

  it("keeps a goalless corner count", () => {
    // Zero corners is a real result and the easiest thing here to lose to a falsy check.
    expect(gameRow(game({ won: 0 }))).toMatchObject({ won: 0, corners: "0-5" });
  });

  it("drops the score rather than inventing nil-nil", () => {
    expect(gameRow(game({ gf: null, ga: null })).score).toBeNull();
    expect(gameRow(game()).score).toBe("1-2");
  });

  it("flags extra time, which is thirty more minutes of corners", () => {
    expect(gameRow(game({ finished_as: "AET" })).extra).toBe("AET");
    expect(gameRow(game({ finished_as: "FT" })).extra).toBeNull();
  });

  it("is nothing at all for a game with no corner count", () => {
    expect(gameRow(game({ won: null }))).toBeNull();
    expect(gameRow(null)).toBeNull();
    expect(gameRows({ games: [game(), game({ won: null })] })).toHaveLength(1);
  });
});

describe("the summary line", () => {
  it("describes a single game as a single game, never as an average", () => {
    // "5.0 corners a game" over one match is true and reads as a rate. On a sample this
    // thin that is the one reading it must not invite.
    const text = summaryText(form([game({ won: 8, conceded: 2 })],
                                  { games: 1, avg_won: 8, avg_conceded: 2,
                                    low: 8, high: 8 }));
    expect(text).toBe("One game in this competition: 8 corners won, 2 conceded");
    expect(text).not.toMatch(/a game/);
  });

  it("gives a per-game figure once there is a sample, with its count and range", () => {
    expect(summaryText(form([game(), game(), game()],
                            { games: 3, avg_won: 4.67, avg_conceded: 3.33,
                              low: 2, high: 8 })))
      .toBe("3 games in this competition · 4.7 won, 3.3 conceded a game (2–8)");
  });

  it("is empty rather than a sentence about nothing", () => {
    expect(summaryText(form([], null))).toBe("");
    expect(summaryText(null)).toBe("");
  });
});

describe("whether to draw the panel at all", () => {
  it("is drawn only when there is a game with a count behind it", () => {
    expect(hasForm(form([game()], { games: 1 }))).toBe(true);
    expect(hasForm(form([], null))).toBe(false);
    expect(hasForm(null)).toBe(false);
  });

  it("will not claim a side has played none, only that none is on file", () => {
    // The store keeps a window of results, so an empty list is a fact about the store.
    const text = emptyText("Inter", "Champions League");
    expect(text).toContain("No Champions League game on file for Inter");
    expect(text).not.toMatch(/has not played|have not played/);
  });
});
