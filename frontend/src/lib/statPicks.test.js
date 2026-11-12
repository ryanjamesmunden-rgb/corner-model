import {
  MIN_PICK_ROWS, MAX_PICK_ROWS,
  pickLine, pickCount, hitRate, pickEv, pickRow, fixtureHead,
  picksFrom, picksPost, statRule,
} from "./statPicks";

const pick = (over = {}) => ({
  fixture_id: "f1", league_id: "bra-sb", league_name: "Serie B",
  kickoff: "2026-11-14T22:30:00+00:00",
  home_name: "Fortaleza", away_name: "Vila Nova",
  team: "Vila Nova", side: "away",
  line: 4.5, plus: 5, price: 2.1, book: "Bet365", price_source: "api",
  fair: 1.84, prob: 54.3, ev: 14.3,
  hits: 8, games: 10, scope: "away", avg: 6.2,
  opp_hits: 7, opp_games: 10, opp_scope: "home",
  market_key: "away_over_4.5", ...over,
});

const data = (picks, over = {}) => ({
  picks, window: 10, min_hit: 0.7, min_odds: 1.5, min_ev: 0,
  per_game: 2, band: [5, 6], ...over,
});

describe("how a bet is written", () => {
  it("uses the handicap-plus form this account already posts props in", () => {
    // "1.5+ Tackles", "0.5+ SOT", "2.5+ Shots" — a 4.5 corner line is the same shape.
    expect(pickLine(pick())).toBe("4.5+ Corners");
    expect(pickLine(pick({ line: 5.5 }))).toBe("5.5+ Corners");
  });

  it("writes nothing rather than a broken line when there is no line", () => {
    expect(pickLine(pick({ line: null }))).toBe("");
    expect(pickLine({})).toBe("");
  });
});

describe("the count, which is the whole point of the post", () => {
  it("prints hits over games, never a percentage", () => {
    // "80%" hides whether that was 4 from 5 or 40 from 50. The fraction cannot.
    expect(pickCount(pick())).toBe("(8/10 A)");
    expect(pickCount(pick({ scope: "home", hits: 6, games: 6 }))).toBe("(6/6 H)");
  });

  it("drops the letter when the rate was measured over all games", () => {
    // corner_counts widens to every game when the venue pool is thin and says so. A bare
    // count means "all games" — not "venue unknown".
    expect(pickCount(pick({ scope: "overall" }))).toBe("(8/10)");
  });

  it("says nothing at all when there is nothing to count", () => {
    expect(pickCount(pick({ hits: null }))).toBe("");
    expect(pickCount(pick({ games: 0 }))).toBe("");
    expect(hitRate(pick({ games: 0 }))).toBeNull();
    expect(hitRate(pick({ hits: null }))).toBeNull();
  });

  it("reads the denominator off the payload, not off a constant here", () => {
    // A change to the measuring window on the backend must not leave the post claiming a
    // denominator the data no longer has.
    expect(pickCount(pick({ hits: 11, games: 15, scope: "overall" }))).toBe("(11/15)");
    expect(hitRate(pick({ hits: 11, games: 15 }))).toBeCloseTo(0.733, 3);
  });
});

describe("the edge", () => {
  it("signs it and fixes it to one place", () => {
    expect(pickEv(pick())).toBe("EV +14.3%");
    expect(pickEv(pick({ ev: -2 }))).toBe("EV -2.0%");
    expect(pickEv(pick({ ev: 0 }))).toBe("EV 0.0%");
  });

  it("is absent rather than zero when the model has no edge to report", () => {
    expect(pickEv(pick({ ev: null }))).toBe("");
  });
});

describe("one row", () => {
  it("reads team, line, price, count, edge", () => {
    expect(pickRow(pick())).toBe("Vila Nova 4.5+ Corners @ 2.10 (8/10 A) EV +14.3%");
  });

  it("keeps the price to two places, as a price is written", () => {
    expect(pickRow(pick({ price: 2 }))).toContain("@ 2.00");
    expect(pickRow(pick({ price: 1.9 }))).toContain("@ 1.90");
  });

  it("leaves out what it does not have rather than printing a gap", () => {
    const row = pickRow(pick({ ev: null, hits: null }));
    expect(row).toBe("Vila Nova 4.5+ Corners @ 2.10");
  });
});

describe("the fixture heading", () => {
  it("carries a flag, both teams and the kick-off", () => {
    const head = fixtureHead(pick());
    expect(head).toContain("Fortaleza v Vila Nova");
    expect(head).toContain("10:30pm");
  });

  it("still produces a heading for a competition with no flag", () => {
    const head = fixtureHead(pick({ league_id: "zzz" }));
    expect(head).toContain("Fortaleza v Vila Nova");
  });
});

describe("building the post", () => {
  const two = [pick(), pick({ fixture_id: "f2", league_id: "eng-l2",
                              home_name: "MK Dons", away_name: "Burton",
                              team: "Burton", kickoff: "2026-11-14T15:00:00+00:00",
                              hits: 7, games: 10, scope: "overall", ev: 6.5,
                              price: 1.95, book: "1xBet" })];

  it("refuses a post below two rows", () => {
    expect(picksFrom(data([pick()]))).toBeNull();
    expect(picksFrom(data([]))).toBeNull();
    expect(picksFrom({})).toBeNull();
    expect(MIN_PICK_ROWS).toBe(2);
  });

  it("orders the card by kick-off, not by hit rate", () => {
    // A leaderboard of my own claims is a different object from a day's card, and the
    // reader needs to see what is about to go off.
    const post = picksFrom(data(two));
    expect(post.games.map((g) => g.rows[0].team)).toEqual(["Burton", "Vila Nova"]);
  });

  it("groups two lines on one fixture under one heading", () => {
    const post = picksFrom(data([pick(), pick({ team: "Fortaleza", side: "home",
                                                line: 5.5, market_key: "home_over_5.5",
                                                hits: 7, ev: 9 })]));
    expect(post.fixtures).toBe(1);
    expect(post.games[0].rows).toHaveLength(2);
  });

  it("drops a row with no price or no count rather than printing a half row", () => {
    const post = picksFrom(data([...two, pick({ fixture_id: "f3", price: null }),
                                 pick({ fixture_id: "f4", games: 0 })]));
    expect(post.n).toBe(2);
  });

  it("trims the WORST RATES and says how many went", () => {
    // The card announces itself as "every line landing 7+ from 10". Cutting by rate
    // applies that same rule; cutting by time would quietly make it "the next N games".
    const many = Array.from({ length: 15 }, (_, i) => pick({
      fixture_id: `f${i}`, hits: 10 - (i % 4), games: 10,
      kickoff: `2026-11-14T${String(10 + i).padStart(2, "0")}:00:00+00:00`,
    }));
    const post = picksFrom(data(many), { max: 6 });
    expect(post.n).toBe(6);
    expect(post.more).toBe(9);
    expect(post.games.every((g) => g.rows.every((p) => hitRate(p) >= 0.9))).toBe(true);
  });

  it("never trims below the minimum", () => {
    expect(picksFrom(data(two), { max: 0 }).n).toBe(MIN_PICK_ROWS);
  });

  it("collects the books so the footer can name them", () => {
    expect(picksFrom(data(two)).books.sort()).toEqual(["1xBet", "Bet365"]);
  });

  it("caps at twelve by default", () => {
    expect(MAX_PICK_ROWS).toBe(12);
  });
});

describe("the rule, written out", () => {
  it("turns the floors into the sentence the card is filtered by", () => {
    expect(statRule(data([]))).toBe(
      "landing 7+ from their last 10, at 1.50 or bigger, with a positive model edge");
  });

  it("rounds the hit floor UP to a whole number of games", () => {
    // 0.7 of 10 is 7; 0.7 of 15 is 10.5, and "landing 10+ from 15" is 66.7%, which is
    // below the bar it claims. Ceil keeps the sentence true.
    expect(statRule(data([], { window: 15, min_hit: 0.7 })))
      .toContain("landing 11+ from their last 15");
  });

  it("names a non-zero edge floor instead of calling it positive", () => {
    expect(statRule(data([], { min_ev: 5 }))).toContain("with an edge over 5%");
  });
});

describe("the post as text", () => {
  const post = picksFrom(data([
    pick(),
    pick({ fixture_id: "f2", league_id: "eng-l2", home_name: "MK Dons",
           away_name: "Burton", team: "Burton", kickoff: "2026-11-14T15:00:00+00:00",
           hits: 7, games: 10, scope: "overall", ev: 6.5, price: 1.95, book: "1xBet" }),
  ]));
  const text = picksPost({ post, site: "thecornermodel.com" });

  it("states the filter and the window before a single row", () => {
    // The format this imitates does the same, and it is why that format reads as research
    // rather than as tipping.
    expect(text).toContain("landing 7+ from their last 10");
    expect(text.indexOf("landing 7+")).toBeLessThan(text.indexOf("4.5+ Corners"));
  });

  it("opens on the save prompt", () => {
    expect(text).toContain("💾 Save this before kick-off");
  });

  it("prints every row under its fixture", () => {
    expect(text).toContain("Burton 4.5+ Corners @ 1.95 (7/10) EV +6.5%");
    expect(text).toContain("Vila Nova 4.5+ Corners @ 2.10 (8/10 A) EV +14.3%");
  });

  it("explains H and A once, at the bottom", () => {
    expect(text).toContain("H / A = that team's record at this venue");
    expect((text.match(/H \/ A =/g) || []).length).toBe(1);
  });

  it("leaves the venue key out when no row carries one", () => {
    const flat = picksFrom(data([pick({ scope: "overall" }),
                                 pick({ fixture_id: "f2", scope: "overall", hits: 7 })]));
    expect(picksPost({ post: flat })).not.toContain("H / A =");
  });

  it("names the books once rather than on every row", () => {
    // At twelve rows the book on each one doubles the length of the post.
    expect(text).toContain("Prices: ");
    expect(text).not.toMatch(/Corners @ [\d.]+ via /);
  });

  it("carries the site and the age line", () => {
    expect(text).toContain("thecornermodel.com");
    expect(text).toContain("18+ · begambleaware.org");
  });

  it("never leaves a run of blank lines", () => {
    expect(text).not.toMatch(/\n\n\n/);
  });

  it("is nothing at all for no post", () => {
    expect(picksPost({ post: null })).toBe("");
    expect(picksPost({})).toBe("");
  });
});
