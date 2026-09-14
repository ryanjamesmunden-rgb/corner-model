// The morning board.
//
// Two failures matter more than the rest. One is the quality bar drifting out of step with
// the backend's, so the card shows spots the graded record would never have bet while
// carrying that record in its header. The other is publishing an ROI that no price stands
// behind — server._record answers 0.0 when nothing was priced, and "0%" on a graphic reads
// as "broke even" rather than "nobody wrote the odds down".

import {
  slateFrom, slateRow, slatePost, qualifies, reasonFor, recordFrom, recordLine,
  dayKeyOf, slateTime, MIN_SLATE_ROWS, MAX_SLATE_ROWS, MIN_VENUE_GAMES,
} from "./chaseSlate.js";

const TODAY = "2026-09-14";

/** A chase row shaped the way _chase_board builds them. */
const spot = ({
  name = "Holstein Kiel", opponent = "Hamburger SV", isHome = true,
  date = `${TODAY}T13:30:00+00:00`, line = 5, hit = 4, of = 5, prob = 71,
  fair = 1.41, book = null, ev = null, fixtureId = "99", league = "ger-2-bundesliga",
  teamFor = 6.2, oppConc = 5.8, lam = 6.4,
} = {}) => ({
  name, league_id: league, league_name: "2. Bundesliga",
  team_for: teamFor, opp_conceded: oppConc, lambda: lam, line,
  consistency: hit, consistency_of: of, prob, fair_odds: fair,
  book_odds: book, ev,
  next_fixture: { date, opponent, is_home: isHome, fixture_id: fixtureId },
});

const ledger = (summary) => ({ summary });

describe("the quality bar, mirrored from the backend", () => {
  test("four of five at the venue clears it", () => {
    expect(qualifies(spot({ hit: 4, of: 5 }))).toBe(true);
    expect(qualifies(spot({ hit: 5, of: 5 }))).toBe(true);
  });

  test("three of five does not", () => {
    expect(qualifies(spot({ hit: 3, of: 5 }))).toBe(false);
  });

  test("a perfect record off too few games is not a rate", () => {
    // 3 of 3 is 100% and means nothing. The backend's floor is four venue games and this
    // has to agree with it, or the card shows spots the graded ledger never bet.
    expect(qualifies(spot({ hit: 3, of: 3 }))).toBe(false);
    expect(qualifies(spot({ hit: 4, of: MIN_VENUE_GAMES }))).toBe(true);
  });

  test("missing numbers fail closed rather than passing", () => {
    expect(qualifies({})).toBe(false);
    expect(qualifies(spot({ of: 0 }))).toBe(false);
  });
});

describe("what a row says", () => {
  test("the market names the team, not just the line", () => {
    // A bare "5+ corners" beside a fixture reads as the match total, which is about twice
    // the number and an entirely different bet.
    expect(slateRow(spot()).market).toBe("Holstein Kiel 5+ corners");
  });

  test("home and away come out the right way round", () => {
    expect(slateRow(spot({ isHome: true }))).toMatchObject({
      home: "Holstein Kiel", away: "Hamburger SV", venue: "home" });
    expect(slateRow(spot({ isHome: false }))).toMatchObject({
      home: "Hamburger SV", away: "Holstein Kiel", venue: "away" });
  });

  test("the reason names the venue the numbers are split on", () => {
    // Without the word they read as season averages, which are different numbers.
    const r = reasonFor(slateRow(spot({ isHome: true })));
    expect(r).toContain("6.2 for home");
    expect(r).toContain("opp concede 5.8");
    expect(r).toContain("cleared 4 of 5");
  });

  test("an away spot says away", () => {
    expect(reasonFor(slateRow(spot({ isHome: false })))).toContain("6.2 for away");
  });

  test("consistency is published as the rate it is", () => {
    expect(slateRow(spot({ hit: 4, of: 5 })).consistency).toBe(80);
  });

  test("a real price and the model's are kept apart", () => {
    expect(slateRow(spot())).toMatchObject({ price: 1.41, priceKind: "fair", ev: null });
    expect(slateRow(spot({ book: 1.9, ev: 5.5 })))
      .toMatchObject({ price: 1.9, priceKind: "book", ev: 5.5 });
  });
});

describe("choosing the board", () => {
  const many = (n, extra = {}) => Array.from({ length: n }, (_, i) =>
    spot({ fixtureId: `f${i}`, prob: 80 - i, ...extra }));

  test("only spots that clear the bar, on the day asked for", () => {
    const rows = [
      spot({ fixtureId: "good1" }), spot({ fixtureId: "good2" }), spot({ fixtureId: "good3" }),
      spot({ fixtureId: "weak", hit: 2, of: 5 }),
      spot({ fixtureId: "tomorrow", date: "2026-09-15T13:30:00+00:00" }),
    ];
    expect(slateFrom({ rows, day: TODAY }).rows.map((r) => r.fixtureId))
      .toEqual(["good1", "good2", "good3"]);
  });

  test("ordered by the model's probability, like the backend", () => {
    const rows = [spot({ fixtureId: "low", prob: 61 }), spot({ fixtureId: "high", prob: 78 }),
                  spot({ fixtureId: "mid", prob: 70 })];
    expect(slateFrom({ rows, day: TODAY }).rows.map((r) => r.fixtureId))
      .toEqual(["high", "mid", "low"]);
  });

  test("capped at ten", () => {
    expect(slateFrom({ rows: many(14), day: TODAY }).n).toBe(MAX_SLATE_ROWS);
  });

  test("a thin day yields fewer rather than being topped up", () => {
    // The backend says this in as many words. A card that always shows ten is a card whose
    // bottom rows mean nothing, and nobody reading it can tell which.
    const rows = [...many(4), ...Array.from({ length: 6 }, (_, i) =>
      spot({ fixtureId: `bad${i}`, hit: 1, of: 5 }))];
    const slate = slateFrom({ rows, day: TODAY });
    expect(slate.n).toBe(4);
    expect(slate.rows.every((r) => r.of >= MIN_VENUE_GAMES)).toBe(true);
  });

  test("below three it is not a board at all", () => {
    expect(slateFrom({ rows: many(2), day: TODAY })).toBeNull();
    expect(slateFrom({ rows: [], day: TODAY })).toBeNull();
    expect(slateFrom({ rows: many(MIN_SLATE_ROWS), day: TODAY }).n).toBe(MIN_SLATE_ROWS);
  });
});

describe("the section's own record", () => {
  test("an ROI is refused when nothing carried a price", () => {
    // server._record answers roi 0.0 with no prices, because zero over nothing has to be
    // something. On a graphic that reads as "broke even", not "nobody wrote the odds down".
    const rec = recordFrom(ledger({ settled: 20, won: 13, win_rate: 65, staked: 0,
                                    profit: 0, roi: 0, unpriced: 20 }));
    expect(rec).toMatchObject({ settled: 20, won: 13, rate: 65, roi: null, profit: null });
    expect(recordLine(rec)).toBe("13 of 20 settled  ·  65%");
  });

  test("and published where prices existed", () => {
    const rec = recordFrom(ledger({ settled: 20, won: 13, win_rate: 65, staked: 12,
                                    profit: 3.4, roi: 28.3, unpriced: 8 }));
    expect(rec).toMatchObject({ roi: 28.3, profit: 3.4, staked: 12 });
    expect(recordLine(rec)).toContain("+3.4u from 12 priced");
  });

  test("a loss keeps its sign", () => {
    const rec = recordFrom(ledger({ settled: 9, won: 3, win_rate: 33.3, staked: 9,
                                    profit: -2.5, roi: -27.8 }));
    expect(recordLine(rec)).toContain("-2.5u");
  });

  test("nothing settled is no record rather than a zero one", () => {
    // "0 of 0 · 0%" is a claim about a record that has not been made yet.
    expect(recordFrom(ledger({ settled: 0, won: 0, win_rate: 0 }))).toBeNull();
    expect(recordFrom(null)).toBeNull();
    expect(recordFrom({})).toBeNull();
    expect(recordLine(null)).toBe("");
  });

  test("the slate carries it through, and copes without one", () => {
    const rows = Array.from({ length: 3 }, (_, i) => spot({ fixtureId: `f${i}` }));
    expect(slateFrom({ rows, day: TODAY, ledger: ledger({ settled: 5, won: 4, win_rate: 80 }) })
      .record).toMatchObject({ won: 4 });
    expect(slateFrom({ rows, day: TODAY }).record).toBeNull();
  });
});

describe("the post around the card", () => {
  const slate = () => slateFrom({
    day: TODAY,
    ledger: ledger({ settled: 20, won: 13, win_rate: 65, staked: 12, profit: 3.4, roi: 28.3 }),
    rows: [spot({ fixtureId: "11", name: "Kiel", opponent: "HSV", prob: 75 }),
           spot({ fixtureId: "22", name: "Brann", opponent: "Viking", prob: 70 }),
           spot({ fixtureId: "33", name: "Rayo", opponent: "Sociedad", prob: 66 })],
  });

  test("every row carries its reason and its link", () => {
    const out = slatePost({ slate: slate(), site: "https://thecornermodel.com" });
    expect(out).toContain("cleared 4 of 5");
    expect(out).toContain("https://thecornermodel.com/fixture/11");
    expect(out).toContain("https://thecornermodel.com/fixture/33");
  });

  test("the record sits under the heading", () => {
    expect(slatePost({ slate: slate(), site: "" })).toContain("13 of 20 settled");
  });

  test("an unpriced board says what its numbers are, once", () => {
    const out = slatePost({ slate: slate(), site: "" });
    expect(out).toContain("fair 1.41");
    expect(out.match(/break-even/g)).toHaveLength(1);
  });

  test("nothing in, nothing out", () => {
    expect(slatePost({ slate: null, site: "x" })).toBe("");
  });
});

describe("which day it thinks it is", () => {
  test("decided on the clock the times are printed on", () => {
    expect(dayKeyOf("2026-09-14T23:30:00Z")).toBe("2026-09-15");
    expect(slateTime("2026-09-14T23:30:00Z")).toBe("00:30");
  });

  test("and unchanged in winter, when London is UTC", () => {
    expect(dayKeyOf("2026-01-14T23:30:00Z")).toBe("2026-01-14");
    expect(slateTime("2026-01-14T23:30:00Z")).toBe("23:30");
  });

  test("rubbish is not a date", () => {
    expect(dayKeyOf("not a date")).toBe("");
    expect(slateTime("nope")).toBe("");
  });
});
