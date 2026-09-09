import { angleWhy, gamesLabel, wrapText } from "./storyImage";

// The reasoning on this image is built from the row's own numbers rather than from the
// "Why this angle?" prose, because that prose is written by a model which is handed the
// line, the probability AND the fair odds and told to reference them. The last test here
// is the one that matters: this copy must not be able to leak a price.

const row = (over = {}) => ({
  name: "Bradford", team_for: 6.8, opp_conceded: 6.9, line: 4, fair_odds: 1.62,
  prob: 62, lambda: 12.2, real_samples: 9, league_id: "eng-l1", ...over,
});
const fx = (over = {}) => ({ opponent: "Cambridge Utd", is_home: true, ...over });

describe("the argument is the two numbers", () => {
  it("names both sides with their averages and the venue", () => {
    const [first] = angleWhy(row(), fx());
    expect(first).toBe("Bradford win 6.8 corners a game at home. Cambridge Utd concede 6.9.");
  });

  it("says away when the team is away", () => {
    expect(angleWhy(row(), fx({ is_home: false }))[0]).toContain("away");
  });

  it("cites the sample rather than leaving it as a claim", () => {
    expect(angleWhy(row(), fx()).at(-1)).toBe("Measured over 9 games, not a hunch.");
  });

  it("drops the sample line when there is no sample to cite", () => {
    const lines = angleWhy(row({ real_samples: 0 }), fx());
    expect(lines.some((l) => l.includes("Measured over"))).toBe(false);
  });

  it("scales the claim to how lopsided the matchup actually is", () => {
    expect(angleWhy(row({ team_for: 8.1, opp_conceded: 7.4 }), fx())[1]).toContain("extreme");
    expect(angleWhy(row({ team_for: 6.4, opp_conceded: 6.2 }), fx())[1]).toContain("gives them away");
    expect(angleWhy(row({ team_for: 5.6, opp_conceded: 5.4 }), fx())[1]).toContain("above par");
  });

  it("says nothing at all rather than printing NaN", () => {
    expect(angleWhy({}, fx())).toEqual([]);
    // null is the dangerous one: Number(null) is 0, so a naive isFinite check publishes
    // "0.0 corners a game" as if it were measured.
    expect(angleWhy(row({ team_for: null }), fx())).toEqual([]);
    expect(angleWhy(row({ opp_conceded: null }), fx())).toEqual([]);
    expect(angleWhy(row({ team_for: undefined }), fx())).toEqual([]);
  });

  it("survives a missing opponent without a blank in the sentence", () => {
    expect(angleWhy(row(), {})[0]).toContain("Their opponent concede");
  });
});

describe("it cannot leak the paid half", () => {
  it("never mentions the price or the projection", () => {
    // The PRICE is the product and is blurred on the slip; copy that named it would make
    // the blur pointless. The line and the probability are published deliberately — a
    // percentage with no line is 62% of nothing — but they are drawn by the slip from the
    // row, never smuggled in through this copy, so they must not appear here either.
    const text = angleWhy(row(), fx()).join(" ");
    expect(text).not.toContain("1.62");     // fair odds — the one thing being withheld
    expect(text).not.toContain("12.2");     // lambda
    expect(text).not.toContain("62");       // probability
    expect(text).not.toMatch(/\b4\+/);      // the line
  });

  it("stays clean for a row whose numbers happen to look like a price", () => {
    const text = angleWhy(row({ team_for: 1.62, opp_conceded: 2.5 }), fx()).join(" ");
    // 1.62 appears because it is the corner average, not because the price leaked.
    expect(text).toContain("1.6 corners a game");
  });
});

describe("wrapText", () => {
  // A fake context: every character is 10px wide, so line breaks are exactly predictable.
  const ctx = { measureText: (t) => ({ width: t.length * 10 }) };

  it("breaks on words to fit the width", () => {
    // "three four" is exactly 100px and therefore fits; 90 forces the third line.
    expect(wrapText(ctx, "one two three four", 90)).toEqual(["one two", "three", "four"]);
  });

  it("keeps a line that already fits as one line", () => {
    expect(wrapText(ctx, "short", 100)).toEqual(["short"]);
  });

  it("never drops a word, even one longer than the line", () => {
    // Canvas has no hyphenation; overflowing is better than silently losing text.
    expect(wrapText(ctx, "a supercalifragilistic b", 60)).toEqual(
      ["a", "supercalifragilistic", "b"]);
  });

  it("collapses runs of whitespace instead of emitting empty lines", () => {
    expect(wrapText(ctx, "  one   two  ", 100)).toEqual(["one two"]);
  });

  it("returns nothing for empty or missing text", () => {
    expect(wrapText(ctx, "", 100)).toEqual([]);
    expect(wrapText(ctx, null, 100)).toEqual([]);
    expect(wrapText(ctx, "   ", 100)).toEqual([]);
  });
});

describe("the recent-games label cannot overclaim the venue", () => {
  // `_real_avg_detail` silently falls back to every venue when the home/away pool is
  // thinner than three games. On the card that fallback gets an amber warning; on an
  // image there is no room for one, so the LABEL itself has to be true.
  it("says the venue when the venue split actually held", () => {
    expect(gamesLabel({ venue_asked: "home", venue_used: "home" }, 6)).toBe("LAST 6 AT HOME");
    expect(gamesLabel({ venue_asked: "away", venue_used: "away" }, 5)).toBe("LAST 5 AWAY");
  });

  it("admits the fallback instead of calling a mixed run 'at home'", () => {
    expect(gamesLabel({ venue_asked: "home", venue_used: "all" }, 6))
      .toBe("LAST 6, ALL VENUES");
  });

  it("claims no venue at all when none was asked for", () => {
    expect(gamesLabel({ venue_asked: "overall", venue_used: "all" }, 4)).toBe("LAST 4");
    expect(gamesLabel({}, 3)).toBe("LAST 3");
  });

  it("reports the count it is given, not a hardcoded five", () => {
    expect(gamesLabel({ venue_asked: "home", venue_used: "home" }, 2)).toBe("LAST 2 AT HOME");
  });
});
