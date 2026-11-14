import {
  ANGLE_MIN_EV, THIN_BOOKS,
  plusOf, evPercent, teamFor, rungLines, angleRungs, fixtureUrl,
  gamePost, ladderPost, angleThread,
} from "./anglePost";

// The real Leganes ladder, as the board returned it on 13 Nov.
const m = (line, book_odds, fair_odds, prob, over = {}) => ({
  key: `home_over_${line}`, group: "home", label: `Home Team Over ${line}`,
  line, book_odds, fair_odds, prob, ev: null,
  price_source: "api", book: "Betano",
  quotes: [{ book: "Betano", price: book_odds }, { book: "1xBet", price: book_odds - 0.03 }],
  ...over,
});

const row = (over = {}) => ({
  fixture_id: "lega1", status: "ok",
  league_id: "esp-2", league_name: "Segunda Division",
  date: "2026-11-13T19:30:00+00:00",
  home_name: "Leganes", away_name: "Burgos",
  best: m(5.5, 2.30, 2.11, 47.5),
  alternatives: [m(4.5, 1.72, 1.62, 61.6), m(6.5, 3.40, 2.88, 34.7)],
  ladder: [m(7.5, 5.00, 4.14, 24.1), m(8.5, 8.00, 6.23, 16.1),
           m(3.5, 1.31, 1.32, 75.5)],
  ...over,
});

describe("how a line is written on X", () => {
  it("uses the plus form, not the handicap", () => {
    // The Telegram post says "Over 9.5"; this account's X posts say "5+". Both are its
    // own, for different channels, and each is written once.
    expect(plusOf(4.5)).toBe(5);
    expect(plusOf(8.5)).toBe(9);
  });

  it("agrees with the backend on a whole line", () => {
    // build_markets settles on int(line) + 1, so "over 5" is the 6+ bet. Math.ceil would
    // say 5 and quote the wrong bet.
    expect(plusOf(5)).toBe(6);
    expect(plusOf(null)).toBeNull();
  });
});

describe("the edge", () => {
  it("is computed from the price being printed, not copied", () => {
    // The board's ev was computed against the price it stored. A human editing the price
    // — the normal case, since the best quote is often at a book they do not hold —
    // would otherwise leave an EV describing a number no longer on screen.
    expect(evPercent(2.30, 47.5)).toBe(9.3);
    expect(evPercent(1.72, 61.6)).toBe(6);
    expect(evPercent(3.40, 34.7)).toBe(18);
    expect(evPercent(5.00, 24.1)).toBe(20.5);
  });

  it("reads prob as the PERCENTAGE it is on the wire", () => {
    // Used as a fraction this reports an edge about a hundred times too big, which on a
    // public post is unrecoverable.
    expect(evPercent(2.0, 50)).toBe(0);
    expect(evPercent(2.0, 0.5)).toBe(-99);
  });

  it("answers null rather than guessing", () => {
    expect(evPercent(null, 50)).toBeNull();
    expect(evPercent(2.0, null)).toBeNull();
  });
});

describe("one rung, exactly as it is posted", () => {
  it("matches the pasted format line for line", () => {
    expect(rungLines({ team: "Leganes", line: 4.5, price: 1.72, fair: 1.62, prob: 61.6 }))
      .toEqual(["🚩 5+ Leganes [1.72]", "📊 Model: 1.62 (62%) EV: +6.0%"]);
  });

  it("uses no pipe, unlike the Telegram format", () => {
    // telegramPick writes "Model price: 1.76 (57%) | EV: +11.0%". This is a different
    // post for a different channel and must not borrow that line.
    const [, stat] = rungLines({ team: "Leganes", line: 5.5, price: 2.30,
                                 fair: 2.11, prob: 47.5 });
    expect(stat).toBe("📊 Model: 2.11 (48%) EV: +9.3%");
    expect(stat).not.toContain("|");
    expect(stat).not.toContain("Model price");
  });

  it("rounds the probability to a whole number the way the pasted post does", () => {
    const pairs = [[61.6, "62%"], [47.5, "48%"], [34.7, "35%"],
                   [24.1, "24%"], [16.1, "16%"]];
    for (const [prob, want] of pairs) {
      expect(rungLines({ team: "X", line: 4.5, price: 2, fair: 2, prob })[1])
        .toContain(`(${want})`);
    }
  });

  it("prints the price to two places, as a price is written", () => {
    expect(rungLines({ team: "X", line: 4.5, price: 8, fair: 6.23, prob: 16.1 })[0])
      .toBe("🚩 5+ X [8.00]");
  });

  it("leaves no trailing space on either line", () => {
    for (const l of rungLines({ team: "Leganes", line: 4.5, price: 1.72,
                                fair: 1.62, prob: 61.6 })) {
      expect(l).toBe(l.trimEnd());
    }
  });

  it("signs a negative edge rather than hiding it", () => {
    expect(rungLines({ team: "X", line: 4.5, price: 1.3, fair: 1.5, prob: 66.7 })[1])
      .toContain("EV: -13.3%");
  });

  it("is nothing at all without a line or a price", () => {
    expect(rungLines({ team: "X", price: 2 })).toEqual([]);
    expect(rungLines({ team: "X", line: 4.5 })).toEqual([]);
    expect(rungLines({})).toEqual([]);
  });
});

describe("which side the ladder is about", () => {
  it("names the team the group belongs to", () => {
    expect(teamFor("home", "Leganes", "Burgos")).toBe("Leganes");
    expect(teamFor("away", "Leganes", "Burgos")).toBe("Burgos");
    expect(teamFor("total", "Leganes", "Burgos")).toBe("");
  });
});

describe("collecting the ladder", () => {
  const rungs = angleRungs(row());

  it("takes every rung of that side from best, alternatives and the full ladder", () => {
    expect(rungs.map((r) => r.plus)).toEqual([5, 6, 7, 8, 9]);
  });

  it("orders it shortest line first, because the ladder IS the argument", () => {
    // 5+ through 9+ in order shows the edge widening as the line lengthens. Sorting by
    // edge would put 9+ on top and turn an argument into a leaderboard.
    expect(rungs.map((r) => r.ev)).toEqual([6, 9.3, 18, 20.5, 28.8]);
    expect(rungs[0].plus).toBeLessThan(rungs[rungs.length - 1].plus);
  });

  it("drops the rungs that do not clear the floor", () => {
    // 3.5 at 1.31 against a fair 1.32 is a negative edge and not part of the claim.
    expect(rungs.find((r) => r.plus === 4)).toBeUndefined();
  });

  it("never lists one rung twice when it appears in two of the lists", () => {
    const dupe = row({ alternatives: [m(4.5, 1.72, 1.62, 61.6)],
                       ladder: [m(4.5, 1.72, 1.62, 61.6)] });
    expect(angleRungs(dupe).filter((r) => r.plus === 5)).toHaveLength(1);
  });

  it("stays on one side of the fixture", () => {
    const both = row({ ladder: [m(4.5, 3.0, 2.0, 50, { group: "away",
                                                       key: "away_over_4.5" })] });
    expect(angleRungs(both, { group: "home" }).every((r) => r.group === "home")).toBe(true);
    expect(angleRungs(both, { group: "away" }).map((r) => r.team)).toEqual(["Burgos"]);
  });

  it("counts the books behind each price without dropping anything", () => {
    // The longest rungs carry the biggest edges and are the ones most often quoted by one
    // book alone. The post keeps them; nothing downstream should have to guess which.
    expect(rungs.every((r) => r.books === 2)).toBe(true);
    const lone = angleRungs(row({ best: m(5.5, 2.30, 2.11, 47.5,
                                          { quotes: [{ book: "Betano", price: 2.30 }] }) }));
    expect(lone.find((r) => r.plus === 6).books).toBe(1);
  });

  it("comes back empty rather than throwing for a row with nothing on it", () => {
    expect(angleRungs({})).toEqual([]);
    expect(angleRungs()).toEqual([]);
  });
});

describe("the fixture link", () => {
  it("points at the page the claim can be checked on", () => {
    expect(fixtureUrl("https://thecornermodel.com", "lega1"))
      .toBe("thecornermodel.com/fixture/lega1");
    expect(fixtureUrl("thecornermodel.com/", "lega1"))
      .toBe("thecornermodel.com/fixture/lega1");
  });

  it("is empty rather than broken when it cannot be built", () => {
    expect(fixtureUrl("", "lega1")).toBe("");
    expect(fixtureUrl("thecornermodel.com", "")).toBe("");
  });
});

describe("the two tweets", () => {
  const t = angleThread(row(), { site: "thecornermodel.com" });

  it("opens with the game, in the account's own three lines", () => {
    expect(t.game).toContain("📅 Friday 13th November");
    expect(t.game).toContain("Segunda Division @ 7:30pm");
    expect(t.game).toContain("🏟️ Leganes v Burgos");
  });

  it("puts the fixture link on the first tweet", () => {
    expect(t.game).toContain("thecornermodel.com/fixture/lega1");
  });

  it("writes the ladder exactly as it was pasted", () => {
    expect(t.ladder).toBe(
      "🚩 5+ Leganes [1.72]\n📊 Model: 1.62 (62%) EV: +6.0%\n\n"
      + "🚩 6+ Leganes [2.30]\n📊 Model: 2.11 (48%) EV: +9.3%\n\n"
      + "🚩 7+ Leganes [3.40]\n📊 Model: 2.88 (35%) EV: +18.0%\n\n"
      + "🚩 8+ Leganes [5.00]\n📊 Model: 4.14 (24%) EV: +20.5%\n\n"
      + "🚩 9+ Leganes [8.00]\n📊 Model: 6.23 (16%) EV: +28.8%");
  });

  it("leaves the link off the reply, where the tweet above already carries it", () => {
    expect(t.ladder).not.toContain("thecornermodel.com");
    // ...and puts it on when the ladder goes out alone.
    expect(ladderPost({ rungs: t.rungs, url: t.url })).toContain("thecornermodel.com/fixture/lega1");
  });

  it("reports the top of the ladder and how thin it is", () => {
    expect(t.n).toBe(5);
    expect(t.bestEv).toBe(28.8);
    expect(t.topLine).toBe(9);
    expect(t.thinRungs).toBe(0);
  });

  it("counts a ladder built on single quotes, so it is visible before it goes out", () => {
    const lone = row({ best: m(5.5, 2.30, 2.11, 47.5,
                               { quotes: [{ book: "Betano", price: 2.30 }] }) });
    expect(angleThread(lone, { site: "s.com" }).thinRungs).toBe(1);
    expect(THIN_BOOKS).toBe(2);
  });

  it("is null for a fixture with no angle on that side", () => {
    expect(angleThread(row({ best: null, alternatives: [], ladder: [] }))).toBeNull();
    expect(angleThread({}, { group: "home" })).toBeNull();
  });

  it("defaults to a floor of zero — every positive edge is part of the claim", () => {
    expect(ANGLE_MIN_EV).toBe(0);
    expect(angleThread(row(), { minEv: 20 }).n).toBe(2);
  });
});
