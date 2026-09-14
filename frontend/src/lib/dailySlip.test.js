// The morning slate.
//
// One failure here matters more than all the others put together: publishing the model's
// fair price in the slot a reader reads as a bookmaker's. It is invisible on the finished
// card — a number in a box looks like a number in a box — and it is wrong about the one
// figure on the graphic anybody was going to act on. Most of what follows guards that.

import {
  slipFrom, slipRow, slipPost, isBookPrice, dayKey, MIN_SLIP_ROWS, MAX_SLIP_ROWS,
} from "./dailySlip.js";

const TODAY = "2026-09-14";

/** A streak row shaped the way /api/share/rows hands them over. */
const row = ({
  name = "Holstein Kiel", opponent = "Hamburg", isHome = true, date = `${TODAY}T13:30:00+00:00`,
  line = "5+ corners", run = 8, prob = 71, fair = 1.41, book = null, ev = null,
  fixtureId = "99", league = "78", subject = "team", stake = null,
} = {}) => ({
  name, line_label: line, subject, league_id: league, stake,
  streak: { length: run },
  next_fixture: { date, opponent, is_home: isHome, fixture_id: fixtureId },
  projection: {
    prob, fair_odds: fair,
    ...(book === null ? {} : { book_odds: book, odds_source: "manual", ev }),
  },
});

describe("telling a real price from the model's", () => {
  test("a price somebody typed in is a book price", () => {
    expect(isBookPrice(row({ book: 1.8, ev: 4.2 }))).toBe(true);
  });

  test("fair odds on their own are not", () => {
    // The whole point. fair_odds is the break-even number; nobody is offering it.
    expect(isBookPrice(row({ fair: 1.41 }))).toBe(false);
  });

  test("a price with no manual source is not trusted even if it is there", () => {
    // A derived book_odds could appear from a future feature. It is still not a price a
    // person checked, so it does not get drawn in the slot that says one did.
    const r = row();
    r.projection.book_odds = 1.9;
    expect(isBookPrice(r)).toBe(false);
  });

  test("the row carries which kind of number it ended up with", () => {
    expect(slipRow(row({ book: 1.8, ev: 4.2 }))).toMatchObject({ price: 1.8, priceKind: "book" });
    expect(slipRow(row({ fair: 1.41 }))).toMatchObject({ price: 1.41, priceKind: "fair" });
  });

  test("EV is published only against a real price", () => {
    // An edge is a comparison between the model and a price. With no price there is nothing
    // to compare to, and a percentage there would be measuring the model against itself.
    expect(slipRow(row({ fair: 1.41 })).ev).toBeNull();
    expect(slipRow(row({ book: 1.8, ev: 4.2 })).ev).toBe(4.2);
  });
});

describe("which way round the fixture goes", () => {
  test("the named team at home is the home side", () => {
    expect(slipRow(row({ name: "Kiel", opponent: "HSV", isHome: true }))).toMatchObject({
      home: "Kiel", away: "HSV",
    });
  });

  test("and away is the other way round", () => {
    // Backwards here puts the fixture the wrong way round on a public graphic, which makes
    // every other number on the card look unreliable too.
    expect(slipRow(row({ name: "Kiel", opponent: "HSV", isHome: false }))).toMatchObject({
      home: "HSV", away: "Kiel",
    });
  });
});

describe("choosing the day's rows", () => {
  test("only games kicking off today", () => {
    const slip = slipFrom({
      rows: [row({ fixtureId: "1" }), row({ fixtureId: "2" }),
             row({ fixtureId: "3", date: "2026-09-17T18:00:00+00:00" })],
      day: TODAY,
    });
    expect(slip.rows.map((r) => r.fixtureId)).toEqual(["1", "2"]);
  });

  test("a real edge outranks a longer run", () => {
    // Same order the daily best-game post uses. Two posts an hour apart naming different
    // best games reads as a model that cannot make its mind up.
    const slip = slipFrom({
      rows: [row({ fixtureId: "long", run: 12 }),
             row({ fixtureId: "edge", run: 3, book: 2.1, ev: 6.5 })],
      day: TODAY,
    });
    expect(slip.rows[0].fixtureId).toBe("edge");
  });

  test("with no prices anywhere it falls back to the longest run", () => {
    const slip = slipFrom({
      rows: [row({ fixtureId: "short", run: 4 }), row({ fixtureId: "long", run: 11 })],
      day: TODAY,
    });
    expect(slip.rows[0].fixtureId).toBe("long");
  });

  test("a thin morning posts nothing rather than a mostly empty card", () => {
    // The same card the good days use, advertising that today is not one of them.
    expect(slipFrom({ rows: [row()], day: TODAY })).toBeNull();
    expect(slipFrom({ rows: [], day: TODAY })).toBeNull();
  });

  test("a row with no opponent or no market is not a row", () => {
    const noOpp = row({ fixtureId: "a" });
    noOpp.next_fixture.opponent = "";
    const noMarket = row({ fixtureId: "b", line: "" });
    expect(slipFrom({ rows: [noOpp, noMarket, row({ fixtureId: "c" })], day: TODAY })).toBeNull();
  });

  test("the count is capped so the rows stay readable", () => {
    const many = Array.from({ length: 9 }, (_, i) => row({ fixtureId: String(i) }));
    expect(slipFrom({ rows: many, day: TODAY, max: 99 }).n).toBe(MAX_SLIP_ROWS);
    expect(slipFrom({ rows: many, day: TODAY, max: 1 }).n).toBe(MIN_SLIP_ROWS);
  });
});

describe("what the card is allowed to call them", () => {
  test("angles, when no row carries a price anyone can take", () => {
    // Calling these bets is a claim about money that nothing here has made.
    const slip = slipFrom({ rows: [row({ fixtureId: "1" }), row({ fixtureId: "2" })], day: TODAY });
    expect(slip).toMatchObject({ label: "ANGLES", priced: 0 });
  });

  test("bets, once a real price is on the board", () => {
    const slip = slipFrom({
      rows: [row({ fixtureId: "1", book: 1.8, ev: 3 }), row({ fixtureId: "2" })],
      day: TODAY,
    });
    expect(slip).toMatchObject({ label: "BETS", priced: 1 });
  });

  test("the stake column appears only when a stake was actually logged", () => {
    const bare = slipFrom({ rows: [row({ fixtureId: "1" }), row({ fixtureId: "2" })], day: TODAY });
    expect(bare.hasStakes).toBe(false);
    const staked = slipFrom({
      rows: [row({ fixtureId: "1", stake: 1.5 }), row({ fixtureId: "2" })], day: TODAY,
    });
    expect(staked.hasStakes).toBe(true);
  });
});

describe("the post around the card", () => {
  const slip = () => slipFrom({
    rows: [row({ fixtureId: "11", name: "Kiel", opponent: "HSV" }),
           row({ fixtureId: "22", name: "Brann", opponent: "Viking" })],
    day: TODAY,
  });

  test("every row carries a link to the page it came from", () => {
    // The only part of a Telegram post that can bring somebody back to the site.
    const out = slipPost({ slip: slip(), site: "https://thecornermodel.com" });
    expect(out).toContain("https://thecornermodel.com/fixture/11");
    expect(out).toContain("https://thecornermodel.com/fixture/22");
  });

  test("it names both sides rather than only the team with the streak", () => {
    expect(slipPost({ slip: slip(), site: "" })).toContain("Kiel v HSV");
  });

  test("an unpriced slate says what its numbers are, once", () => {
    const out = slipPost({ slip: slip(), site: "" });
    expect(out).toContain("fair 1.41");
    expect(out.match(/break-even/g)).toHaveLength(1);
  });

  test("a fully priced slate does not apologise for prices it has", () => {
    const priced = slipFrom({
      rows: [row({ fixtureId: "1", book: 1.8, ev: 3 }), row({ fixtureId: "2", book: 2.0, ev: 4 })],
      day: TODAY,
    });
    const out = slipPost({ slip: priced, site: "" });
    expect(out).toContain("@ 1.8");
    expect(out).not.toContain("break-even");
  });

  test("nothing in means nothing out", () => {
    expect(slipPost({ slip: null, site: "x" })).toBe("");
  });
});

describe("which day it thinks it is", () => {
  test("local, not UTC", () => {
    // A UTC boundary puts a 00:30 kick-off on the wrong card for half the year.
    const d = new Date(2026, 8, 14, 0, 30);
    expect(dayKey(d)).toBe("2026-09-14");
  });

  test("months and days are padded", () => {
    expect(dayKey(new Date(2026, 0, 5, 12, 0))).toBe("2026-01-05");
  });
});
