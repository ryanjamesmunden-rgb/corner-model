import {
  BAND, MIN_TIP_EV, MAX_TIP_ROWS, MIN_TIP_ROWS, END_SHARE,
  plusOf, bandLines, bandLabel, overLabel, tipLabel, subjectOf,
  rungFault, bandRungs, tipRow, tipsFrom, tipsAt, tipsPost,
} from "./tipsReel";

// A board row shaped the way /share/rows?boards=value hands it over.
const rung = (over = {}) => ({
  key: "home_over_4.5", group: "home", label: "Home Team Over 4.5",
  line: 4.5, book_odds: 2.1, fair_odds: 1.8, prob: 55.6, ev: 16.7,
  tier: "strong", price_source: "api", book: "Bet365", ...over,
});

const row = (over = {}) => ({
  fixture_id: "f1", status: "ok", home_name: "Tondela", away_name: "Alverca",
  league_id: "por-2", league_name: "Segunda Liga",
  date: "2026-11-14T20:15:00+00:00", lambda_total: 10.4,
  odds_source: "api", best: rung(), alternatives: [], ...over,
});

const NOW = new Date("2026-11-13T12:00:00Z").getTime();
const build = (rows, opts = {}) => tipsFrom(rows, { now: NOW, ...opts });

describe("the plus-line a stored line is a bet on", () => {
  it("reads 4.5 as the 5+ bet", () => {
    expect(plusOf(4.5)).toBe(5);
    expect(plusOf(5.5)).toBe(6);
  });

  it("reads a WHOLE line the way the backend settles it, not the way ceil would", () => {
    // Math.ceil(5) is 5; the backend's `int(line) + 1` makes "over 5" the 6+ bet. A band
    // filter that disagreed would select rungs the ledger measured under another name.
    expect(plusOf(5)).toBe(6);
    expect(plusOf(4)).toBe(5);
  });

  it("answers null rather than a number for nothing", () => {
    expect(plusOf(null)).toBeNull();
    expect(plusOf("")).toBeNull();
    expect(plusOf("abc")).toBeNull();
  });

  it("converts the band back to the lines it filters on", () => {
    expect(bandLines([5, 6])).toEqual([4.5, 5.5]);
  });
});

describe("how the band and the bet are written", () => {
  it("names the band in the ledger's vocabulary", () => {
    expect(bandLabel([5, 6])).toBe("5+ and 6+");
    expect(bandLabel([5, 6, 7])).toBe("5+, 6+ and 7+");
    expect(bandLabel([5])).toBe("5+");
  });

  it("writes the LINE the way the channel posts it", () => {
    // The owner's own post reads "Over 9.5", not "10+". Both name the same bet; this is
    // the form that goes out.
    expect(overLabel(4.5)).toBe("Over 4.5");
    expect(overLabel(9.5)).toBe("Over 9.5");
  });

  it("puts the team's name on a team line and 'match' on a total", () => {
    expect(tipLabel(rung(), "Tondela", "Alverca")).toBe("Tondela Over 4.5 corners");
    expect(tipLabel(rung({ group: "away" }), "Tondela", "Alverca"))
      .toBe("Alverca Over 4.5 corners");
    expect(tipLabel(rung({ group: "total", line: 9.5 }), "Tondela", "Alverca"))
      .toBe("Over 9.5 match corners");
  });

  it("says which side the bet is on", () => {
    expect(subjectOf(rung(), "Tondela", "Alverca")).toBe("Tondela");
    expect(subjectOf(rung({ group: "away" }), "Tondela", "Alverca")).toBe("Alverca");
    expect(subjectOf(rung({ group: "total" }), "Tondela", "Alverca")).toBe("");
  });
});

describe("what makes a rung publishable", () => {
  it("passes a band team line with a real, attributed price over the floor", () => {
    expect(rungFault(rung())).toBe("");
  });

  it("refuses a match total, however big the edge", () => {
    expect(rungFault(rung({ group: "total", line: 9.5, ev: 40 }))).toBe("not_a_team_line");
  });

  it("refuses a team line outside the band", () => {
    expect(rungFault(rung({ line: 2.5 }))).toBe("outside_band");   // 3+
    expect(rungFault(rung({ line: 3.5 }))).toBe("outside_band");   // 4+
    expect(rungFault(rung({ line: 6.5 }))).toBe("outside_band");   // 7+
  });

  it("refuses a demo price and an unstamped one", () => {
    // THE ONE THAT WOULD FABRICATE AN EDGE. The seeders write fair_odds * uniform(0.90,
    // 1.15), so an EV against one of those is the model finding value in its own jitter.
    expect(rungFault(rung({ price_source: "demo" }))).toBe("no_real_price");
    expect(rungFault(rung({ price_source: undefined }))).toBe("no_real_price");
  });

  it("refuses a priced rung with no bookmaker behind it", () => {
    // RULE 3's second half. The feed takes the best of 33 books; a +19% edge at a book the
    // viewer has no account with is not a bet they can place, and quoting it as though it
    // were is the most plausible way this clip could mislead somebody.
    expect(rungFault(rung({ book: "" }))).toBe("no_book");
    expect(rungFault(rung({ book: null }))).toBe("no_book");
  });

  it("refuses a price that is not a price", () => {
    expect(rungFault(rung({ book_odds: null }))).toBe("no_price");
    expect(rungFault(rung({ book_odds: 1 }))).toBe("no_price");
  });

  it("refuses an edge under the floor and takes one exactly on it", () => {
    expect(rungFault(rung({ ev: 4.9 }))).toBe("below_floor");
    expect(rungFault(rung({ ev: MIN_TIP_EV }))).toBe("");
    expect(rungFault(rung({ ev: null }))).toBe("no_ev");
  });

  it("answers for nothing at all rather than throwing", () => {
    expect(rungFault(null)).toBe("no_rung");
    expect(rungFault(undefined)).toBe("no_rung");
  });
});

describe("the band rungs a fixture offers", () => {
  it("collects them from best and alternatives, biggest edge first", () => {
    const r = row({
      best: rung({ key: "home_over_4.5", ev: 8 }),
      alternatives: [rung({ key: "away_over_5.5", group: "away", line: 5.5, ev: 19 }),
                     rung({ key: "total_over_9.5", group: "total", line: 9.5, ev: 30 })],
    });
    expect(bandRungs(r).map((x) => x.key)).toEqual(["away_over_5.5", "home_over_4.5"]);
  });

  it("comes back empty when nothing in the four is in the band", () => {
    expect(bandRungs(row({ best: rung({ line: 2.5 }), alternatives: [] }))).toEqual([]);
  });
});

describe("one pick per fixture", () => {
  it("takes the fixture's biggest band edge and leaves the rest", () => {
    // THE LEDGER'S OWN FINDING, pinned. Fixtures sent with three or more angles returned
    // -4.4% over 112u; one or two returned +13.0% over 512.5u. Three rungs of one ladder
    // is one opinion sold three times.
    const { reel } = build([
      row({ fixture_id: "a",
            best: rung({ key: "home_over_4.5", ev: 12 }),
            alternatives: [rung({ key: "home_over_5.5", line: 5.5, ev: 9 }),
                           rung({ key: "away_over_4.5", group: "away", ev: 7 })] }),
      row({ fixture_id: "b", home_name: "Burton", away_name: "Notts",
            date: "2026-11-15T15:00:00+00:00" }),
    ]);
    expect(reel.n).toBe(2);
    expect(reel.rows.map((r) => r.key)).toEqual(["a:home_over_4.5", "b:home_over_4.5"]);
  });
});

describe("rows that never reach the clip, and why", () => {
  it("counts every drop by its reason rather than as one lump", () => {
    const { reel, faults } = build([
      row({ fixture_id: "a" }),
      row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" }),
      row({ fixture_id: "c", status: "kicked_off" }),
      row({ fixture_id: "d", best: rung({ line: 2.5 }) }),
      row({ fixture_id: "e", best: rung({ price_source: "demo" }) }),
      row({ fixture_id: "f", best: rung({ ev: 1.2 }) }),
      row({ fixture_id: "g", best: rung({ book: "" }) }),
    ]);
    expect(reel.n).toBe(2);
    expect(faults).toEqual({
      kicked_off: 1, outside_band: 1, no_real_price: 1, below_floor: 1, no_book: 1,
    });
  });

  it("drops a fixture that has already started even when the board still says ok", () => {
    // The board is read minutes before this runs and the clip is watched minutes after.
    const { reel, faults } = build([
      row({ fixture_id: "a", date: "2026-11-13T11:00:00+00:00" }),
      row({ fixture_id: "b" }),
      row({ fixture_id: "c", date: "2026-11-15T15:00:00+00:00" }),
    ]);
    expect(faults.kicked_off).toBe(1);
    expect(reel.n).toBe(2);
  });
});

describe("nothing to animate is not a clip", () => {
  it("returns no reel below two picks, and says how many were eligible", () => {
    const out = build([row({ fixture_id: "a" })]);
    expect(out.reel).toBeNull();
    expect(out.eligible).toBe(1);
  });

  it("returns no reel for an empty board", () => {
    expect(build([]).reel).toBeNull();
    expect(build(null).reel).toBeNull();
  });
});

describe("order and trim", () => {
  const many = Array.from({ length: 11 }, (_, i) => row({
    fixture_id: `f${i}`,
    home_name: `Team ${i}`,
    // Later index = earlier kick-off, so kick-off order and edge order disagree.
    date: `2026-11-${String(26 - i).padStart(2, "0")}T15:00:00+00:00`,
    best: rung({ ev: 6 + i }),
  }));

  it("selects by edge and shows in kick-off order", () => {
    const { reel } = build(many, { max: 4 });
    expect(reel.n).toBe(4);
    // The four biggest edges are f7..f10; shown earliest kick-off first, which is f10.
    expect(reel.rows.map((r) => r.home)).toEqual(["Team 10", "Team 9", "Team 8", "Team 7"]);
  });

  it("reports what cleared the bar and did not fit", () => {
    const { reel } = build(many, { max: 4 });
    expect(reel.more).toBe(7);
  });

  it("drops the smallest edges, not the furthest-away games", () => {
    // THE TRIM THAT WOULD BE A DIFFERENT WEEKEND. Dropping by date would quietly turn a
    // shortlist of the board's best prices into "the next four games", which is a
    // different claim made with the same rows.
    const { reel } = build(many, { max: 3 });
    expect(reel.rows.every((r) => r.ev >= 14)).toBe(true);
  });

  it("never trims below the minimum", () => {
    const { reel } = build(many, { max: 0 });
    expect(reel.n).toBe(MIN_TIP_ROWS);
  });

  it("caps at eight rows by default, which is what fits a phone", () => {
    const { reel } = build(many);
    expect(MAX_TIP_ROWS).toBe(8);
    expect(reel.n).toBe(8);
  });
});

describe("what the card is allowed to claim", () => {
  it("states the filter, so the rows do not read as 'the best bets on the board'", () => {
    const { reel } = build([row({ fixture_id: "a" }),
                            row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })]);
    expect(reel.bandLabel).toBe("5+ and 6+");
    expect(reel.basis).toBe("5+ and 6+ team corner lines, best book price, edge over 5%");
  });

  it("carries the overall record when it is given one, and nothing when it is not", () => {
    const rows = [row({ fixture_id: "a" }),
                  row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })];
    expect(build(rows, { record: { landed: 61, settled: 107 } }).reel.context)
      .toBe("61 of 107 overall");
    // A clip that refused to exist because a second endpoint was slow would be the wrong
    // trade — but it draws no record rather than one it does not have.
    expect(build(rows).reel.context).toBe("");
  });

  it("times the prices and tells the viewer to check", () => {
    // RULE 4. FEED_PRICE_STALE_HOURS is 12 on the backend, and a clip lives on a feed for
    // weeks: these are prices that EXISTED, not prices that are available.
    const { reel } = build([row({ fixture_id: "a" }),
                            row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })],
                           { pricedAt: "2026-11-13T11:20:00+00:00" });
    expect(reel.pricedNote)
      .toBe("Oldest price here read 11:20am GMT — check before backing");
  });

  it("stamps the card with the OLDEST price on it, not the freshest", () => {
    // "Nothing here is older than this" is the claim that matters; stamping the clip with
    // the freshest price would describe one row and imply it of all of them.
    const { reel } = build([
      row({ fixture_id: "a", priced_at: "2026-11-13T11:45:00+00:00" }),
      row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00",
            priced_at: "2026-11-13T07:05:00+00:00" }),
    ]);
    expect(reel.pricedAt).toBe("2026-11-13T07:05:00+00:00");
    expect(reel.pricedNote).toContain("7:05am");
  });

  it("drops the stamp entirely when one row cannot say when it was priced", () => {
    // A minimum over the rows that happen to carry a timestamp is not a minimum over the
    // card, and a precise-looking time that quietly excluded the unknown row would be
    // worse than the generic warning.
    const { reel } = build([
      row({ fixture_id: "a", priced_at: "2026-11-13T11:45:00+00:00" }),
      row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00", priced_at: null }),
    ]);
    expect(reel.pricedAt).toBeNull();
    expect(reel.pricedNote).toBe("Prices move — check before backing");
  });

  it("still warns when it does not know when the prices were read", () => {
    const { reel } = build([row({ fixture_id: "a" }),
                            row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })]);
    expect(reel.pricedNote).toBe("Prices move — check before backing");
  });

  it("names the period from the rows, not from today", () => {
    const { reel } = build([row({ fixture_id: "a" }),
                            row({ fixture_id: "b", date: "2026-11-16T15:00:00+00:00" })]);
    expect(reel.period).toBe("14 Nov – 16 Nov");
  });
});

describe("one row, as a frame shows it", () => {
  it("carries the bet, the price, the book and the model side by side", () => {
    const { reel } = build([row({ fixture_id: "a" }),
                            row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })]);
    const r = reel.rows[0];
    expect(r.fixture).toBe("Tondela v Alverca");
    expect(r.bet).toBe("Tondela Over 4.5 corners");
    expect(r.plus).toBe(5);
    expect(r.price).toBe(2.1);
    expect(r.book).toBe("Bet365");
    expect(r.fair).toBe(1.8);
    expect(r.prob).toBe(55.6);
    expect(r.ev).toBe(16.7);
    expect(r.league).toBe("Segunda Liga");
    expect(r.time).toBe("8:15pm");
    expect(r.day).toBe("Saturday 14th November");
  });

  it("keeps the price as a NUMBER, not as prose", () => {
    // The renderer draws a bar from the edge and a box from the price. A renderer that had
    // to parse either back out of a label would be one bad regex from drawing a correct
    // number in the wrong place.
    const r = tipRow(row(), rung());
    expect(typeof r.price).toBe("number");
    expect(typeof r.ev).toBe("number");
    expect(typeof r.line).toBe("number");
  });
});

describe("how much is on screen", () => {
  const reel = build([row({ fixture_id: "a" }),
                      row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" }),
                      row({ fixture_id: "c", date: "2026-11-16T15:00:00+00:00" })],
                     { join: "t.me/x", record: { landed: 61, settled: 107 } }).reel;

  it("starts on the first row and ends on all of them", () => {
    expect(tipsAt(reel, 0).shown).toBe(1);
    expect(tipsAt(reel, 1).shown).toBe(3);
  });

  it("gives the end card its own beat at the end", () => {
    expect(tipsAt(reel, 0.5).end).toBe(0);
    expect(tipsAt(reel, 0.9).end).toBeGreaterThan(0);
  });

  it("pins the LAST frame at full, which is the one that is held", () => {
    // (1 - 0.76) / 0.24 is a hair under 1 in binary floating point, and the frame it lands
    // on is the held final frame of the video and the still that gets posted.
    expect(tipsAt(reel, 1).end).toBe(1);
    expect(END_SHARE).toBe(0.24);
  });

  it("gives the rows the whole clip when there is no end card", () => {
    const bare = build([row({ fixture_id: "a" }),
                        row({ fixture_id: "b", date: "2026-11-15T15:00:00+00:00" })]).reel;
    expect(tipsAt(bare, 0.99).shown).toBe(2);
    expect(tipsAt(bare, 0.99).end).toBe(0);
  });

  it("answers for no reel rather than throwing", () => {
    expect(tipsAt(null, 0.5)).toEqual({ shown: 0, end: 0, growth: 1 });
  });

  it("runs the newest row's bar out and leaves the rest alone", () => {
    const mid = tipsAt(reel, 0.13);
    expect(mid.shown).toBe(1);
    expect(mid.growth).toBeGreaterThan(0);
    expect(mid.growth).toBeLessThanOrEqual(1);
  });
});

describe("the caption", () => {
  const { reel } = build([row({ fixture_id: "a" }),
                          row({ fixture_id: "b", home_name: "Burton Albion",
                                away_name: "Notts County", league_id: "eng-l2",
                                league_name: "League Two",
                                date: "2026-11-15T15:00:00+00:00",
                                best: rung({ line: 5.5, book_odds: 1.95,
                                             fair_odds: 1.76, prob: 56.8, ev: 10.8,
                                             book: "Bet365" }) })],
                         { pricedAt: "2026-11-13T11:20:00+00:00", join: "t.me/corner" });

  const post = tipsPost({ reel, site: "thecornermodel.com" });

  it("writes each pick in the channel's own six lines", () => {
    expect(post).toContain("📅 Saturday 14th November");
    expect(post).toContain("🏟️ Tondela v Alverca");
    expect(post).toContain("🚩 Tondela Over 4.5 corners");
    expect(post).toContain("📈 [2.10] via Bet365");
    expect(post).toContain("📊 Model price: 1.80 (56%) | EV: +16.7%");
  });

  it("puts the league and the kick-off on one line, as the channel does", () => {
    expect(post).toContain("Segunda Liga @ 8:15pm");
  });

  it("CARRIES NO STAKE, because this is not a tip", () => {
    // The owner is explicit: "no stake as it's not a tip. Just posting the best EV+ ahead
    // of the weekend." A unit size on it would make it one.
    expect(post).not.toContain("💸");
    expect(post).not.toMatch(/\d+u\b/);
  });

  it("repeats the filter and the price warning in the text", () => {
    // The clip can be watched with the sound off and screenshotted out of context; the
    // caption is the copy that travels.
    expect(post).toContain("5+ and 6+ team corner lines");
    expect(post).toContain("Oldest price here read 11:20am GMT — check before backing");
  });

  it("ends on the link and the site", () => {
    expect(post).toContain("t.me/corner");
    expect(post.trim().endsWith("thecornermodel.com")).toBe(true);
  });

  it("never leaves a run of blank lines behind a dropped line", () => {
    expect(post).not.toMatch(/\n\n\n/);
  });

  it("is nothing at all for no reel", () => {
    expect(tipsPost({ reel: null })).toBe("");
    expect(tipsPost({})).toBe("");
  });
});

describe("the constants the rest of the app reads", () => {
  it("defaults to the band the ledger measured", () => {
    // 5+/6+: +48.47u over 90. 4+ and below: -12.90u over 29. 7+: 12 bets, not a sample.
    expect(BAND).toEqual([5, 6]);
  });

  it("defaults to the bot's own edge floor", () => {
    expect(MIN_TIP_EV).toBe(5.0);
  });
});
