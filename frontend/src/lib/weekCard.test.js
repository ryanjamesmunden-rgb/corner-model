import { boardLabel, cardNote, dayStrip, lineLabel, PICK_RESULT, priceOf, priceValue,
         priceTone, recordOf, recordText, resultText, slotsOf, valueShort, valueText,
         warningsOf } from "./weekCard";

const pick = (over = {}) => ({ line: 6, label: "6+", book_odds: 1.73, fair_odds: 1.58,
                               prob: 63.2, ev: 9.4, credibility: "credible", ...over });

const side = (over = {}) => ({
  name: "Bradford", team_id: "t1", venue: "home", pick: pick(),
  run: { line: 6, line_label: "6+", hits: 9, settled: 10, floor: 4, length: 6 },
  run_matches_pick: true, boards: ["streaks"], warnings: [], game_state: null, ...over,
});

describe("the price — the red half", () => {
  it("is the bookmaker's number when there is one", () => {
    expect(priceOf(pick())).toMatchObject({ odds: 1.73, ev: 9.4, quoted: true });
  });

  it("falls back to the model's price and says it is not a real one", () => {
    // A fair price and a price you can take cannot look alike on a card people bet from.
    const p = priceOf(pick({ book_odds: null, ev: null }));
    expect(p).toMatchObject({ odds: 1.58, quoted: false });
    expect(p.ev).toBeNull();
  });

  it("is nothing at all rather than zero when there is no line", () => {
    expect(priceOf(null)).toBeNull();
    expect(priceOf({ book_odds: null, fair_odds: null })).toBeNull();
  });

  it("does not treat a zero edge as missing", () => {
    expect(priceOf(pick({ ev: 0 })).ev).toBe(0);
  });

  it("reads the line off either shape", () => {
    expect(lineLabel({ line_label: "5+" })).toBe("5+");
    expect(lineLabel({ line: 7 })).toBe("7+");
    expect(lineLabel(null)).toBe("");
  });
});

describe("the record — the green half", () => {
  it("is the run with its denominator and its floor", () => {
    expect(recordText(side())).toBe("9 of 10, lowest 4");
  });

  it("names the line first when the run is at a different one from the bet", () => {
    // THE BUG THIS PREVENTS: a 5+ record printed under a 6+ price reads as a 6+ record.
    // The caller draws this one muted; green is reserved for a record of THIS bet.
    const other = side({
      pick: pick({ line: 6 }), run_matches_pick: false,
      run: { line: 5, line_label: "5+", hits: 9, settled: 10, floor: 4 },
    });
    expect(recordText(other)).toBe("5+ · 9 of 10, lowest 4");
    expect(recordOf(other).atPick).toBe(false);
  });

  it("marks a matching run as such, so the caller can colour it", () => {
    expect(recordOf(side()).atPick).toBe(true);
  });

  it("is empty for a side with no run rather than inventing one", () => {
    expect(recordText(side({ run: null }))).toBe("");
    expect(recordOf(side({ run: { hits: null, settled: 10 } }))).toBeNull();
  });

  it("drops the floor rather than printing a blank one", () => {
    expect(recordText(side({ run: { line: 6, hits: 8, settled: 10, floor: null },
                             run_matches_pick: true }))).toBe("8 of 10");
  });

  it("keeps a floor of zero, which is the most important floor there is", () => {
    // A side that once won no corners at all is exactly what the floor exists to show.
    expect(recordText(side({ run: { line: 6, hits: 8, settled: 10, floor: 0 },
                             run_matches_pick: true }))).toBe("8 of 10, lowest 0");
  });
});

describe("the card as a whole", () => {
  const card = (over = {}) => ({
    fixture_id: "fx1", status: "ok", run_count: 1,
    home: side(), away: side({ name: "Barnsley", team_id: "t2", run: null }), ...over,
  });

  it("says a game has no price yet rather than looking complete", () => {
    expect(cardNote(card({ status: "no_price" }))).toBe("No price yet — research game");
  });

  it("counts the sides with a run without scoring them", () => {
    expect(cardNote(card({ run_count: 2 }))).toBe("Both sides on a run");
    expect(cardNote(card({ run_count: 1 }))).toBe("One side on a run");
    expect(cardNote(card({ run_count: 0 }))).toContain("no run");
  });

  it("gives the two sides in home-then-away order", () => {
    expect(slotsOf(card()).map((s) => s.venue)).toEqual(["H", "A"]);
  });

  it("says a shared warning once, not once per side", () => {
    // Both sides raise "the opponent's record is thin" about each other.
    const thin = "opponent's venue record is 8 games";
    const out = warningsOf(card({
      home: side({ warnings: [thin, "Bradford promoted: price less reliable"] }),
      away: side({ warnings: [thin] }),
    }));
    expect(out).toEqual([thin, "Bradford promoted: price less reliable"]);
  });

  it("survives a card with nothing on it", () => {
    expect(warningsOf({})).toEqual([]);
    expect(cardNote(null)).toBe("");
  });

  it("names the boards the way the site does, not the way the API does", () => {
    expect(boardLabel("quick_scan")).toBe("Quick Scan");
    expect(boardLabel("perfect_games")).toBe("Perfect Games");
    expect(boardLabel("something_new")).toBe("something_new");
  });
});

describe("the day strip", () => {
  it("starts at today and runs forward", () => {
    const days = dayStrip(new Date("2026-11-23T10:00:00Z"), 7, 0);
    expect(days).toHaveLength(7);
    expect(days[0].short).toBe("Today");
    expect(days[1].short).toBe("Tomorrow");
    expect(days[2].short).toBe("Wed");
  });

  it("uses UK days, so a late kick-off is filed where the reader expects it", () => {
    // 23:30 UTC in June is 00:30 the next day in London. The strip must agree with the
    // backend, which buckets by London date.
    const days = dayStrip(new Date("2026-06-10T23:30:00Z"), 2, 0);
    expect(days[0].value).toBe("2026-06-11");
  });

  it("labels each day in full for the heading", () => {
    expect(dayStrip(new Date("2026-11-23T10:00:00Z"), 1, 0)[0].label)
      .toBe("Mon 23 Nov");
  });
});

// --- a day that has been played ------------------------------------------------------
//
// The card was a forecast that vanished at kick-off. The day you most want to look at one
// is the day after: the same games, the same lines, the same prices, with the corner count
// beside each.

describe("a played card", () => {
  const done = (over = {}) => ({
    fixture_id: "p1", status: "played", settled: 3, landed: 2,
    result: { home_goals: 2, away_goals: 1, home_corners: 7, away_corners: 4,
              total_corners: 11, corners_known: true, finished_as: "FT" },
    home: side({ pick: pick({ result: "won", actual: 7 }) }),
    away: side({ name: "Barnsley", pick: pick({ result: "lost", actual: 4 }) }),
    ...over,
  });

  it("leads with the corners, then the goals", () => {
    expect(resultText(done())).toBe("7-4 corners · 2-1");
  });

  it("says the corner count never arrived rather than printing nil-nil", () => {
    // 0-0 corners is a real result; "nobody fetched it" is not.
    const r = { ...done().result, corners_known: false, home_corners: null,
                away_corners: null };
    expect(resultText(done({ result: r }))).toBe("played — corner count not in yet");
  });

  it("prints the goals only when both are known", () => {
    const r = { ...done().result, home_goals: null, away_goals: null };
    expect(resultText(done({ result: r }))).toBe("7-4 corners");
  });

  it("is null for a game still to come", () => {
    expect(resultText({ home: side() })).toBeNull();
    expect(resultText(null)).toBeNull();
  });

  it("leads its note with the score, not with what it once suggested", () => {
    expect(cardNote(done())).toBe("2 of 3 landed");
    expect(cardNote(done({ settled: 0, landed: 0 }))).toBe("played");
  });

  it("still reads as a forecast before kick-off", () => {
    expect(cardNote({ run_count: 2 })).toBe("Both sides on a run");
  });

  it("gives each outcome a word, not just a colour", () => {
    // The site's tones are close enough under colour blindness that none may carry a
    // meaning on its own.
    expect(PICK_RESULT.won.word).toBe("landed");
    expect(PICK_RESULT.lost.word).toBe("missed");
    expect(PICK_RESULT.void.word).toBe("push");
  });
});

// --- the case for taking a price -----------------------------------------------------
//
// The thing the page exists to find: a line that has come in every time it was priced,
// being offered at more than it came in at. Two facts and a subtraction — nothing here
// forecasts anything, and every number in it can be checked against the games.

describe("a price longer than the line has landed at", () => {
  const h = (...games) => ({ games, found: games.length,
                             landed: games.filter((g) => g.result === "won").length,
                             last: games[0] });
  const won = (odds) => ({ result: "won", book_odds: odds, value: 7 });

  it("makes the case when every priced game landed and the price has grown", () => {
    expect(valueText(pick({ book_odds: 1.73, history: h(won(1.62), won(1.7)) })))
      .toBe("Landed all 2 · best was 1.70, now 1.73");
  });

  it("says nothing when the price is no longer than before", () => {
    // Same record, worse price. That is not an argument for anything.
    expect(valueText(pick({ book_odds: 1.65, history: h(won(1.62), won(1.7)) })))
      .toBeNull();
    expect(valueText(pick({ book_odds: 1.7, history: h(won(1.62), won(1.7)) })))
      .toBeNull();
  });

  it("ends at one miss, because the claim is that it lands every time", () => {
    expect(valueText(pick({ book_odds: 2.5,
                            history: h(won(1.62), { result: "lost", book_odds: 1.7 }) })))
      .toBeNull();
  });

  it("refuses to argue from a single game", () => {
    // One instance is an anecdote; it still shows as the ordinary history sentence.
    expect(valueText(pick({ book_odds: 1.9, history: h(won(1.62)) }))).toBeNull();
  });

  it("leaves a push out of the count rather than letting it pad the record", () => {
    // A push is neither a hit nor a miss, and counting it would make "all 3" of two.
    const v = priceValue(pick({ book_odds: 1.9,
      history: h(won(1.62), { result: "void", book_odds: 1.8 }, won(1.7)) }));
    expect(v).toMatchObject({ games: 2, best: 1.7 });
  });

  it("will not compare against a game whose price was never stored", () => {
    // "Longer than before" needs a before. A missing price is not a small one.
    expect(valueText(pick({ book_odds: 1.9,
      history: h(won(1.62), { result: "won", book_odds: null }) }))).toBeNull();
  });

  it("says nothing at all for a line with no history and no price", () => {
    expect(valueText(pick({ history: undefined }))).toBeNull();
    expect(valueText(null)).toBeNull();
    expect(priceValue({ book_odds: null, history: h(won(1.62), won(1.7)) })).toBeNull();
  });

  it("fits a column in the table layout without losing either fact", () => {
    expect(valueShort(pick({ book_odds: 1.73, history: h(won(1.62), won(1.7)) })))
      .toBe("All 2 landed, best 1.70");
    expect(valueShort(pick({ book_odds: 1.6, history: h(won(1.62), won(1.7)) })))
      .toBeNull();
  });
});

describe("the day strip reaching backwards", () => {
  it("offers yesterday as well as tomorrow", () => {
    const days = dayStrip(new Date("2026-11-25T10:00:00Z"), 7, 3);
    expect(days).toHaveLength(10);
    const today = days.findIndex((d) => d.short === "Today");
    expect(days[today - 1].short).toBe("Yesterday");
    expect(days[today + 1].short).toBe("Tomorrow");
  });

  it("marks which days are behind, so the page can say they are results", () => {
    const days = dayStrip(new Date("2026-11-25T10:00:00Z"), 7, 3);
    expect(days.filter((d) => d.past)).toHaveLength(3);
    expect(days.find((d) => d.short === "Today").past).toBe(false);
  });

  it("still starts at today when nothing is asked for behind", () => {
    expect(dayStrip(new Date("2026-11-25T10:00:00Z"), 7, 0)[0].short).toBe("Today");
  });
});

// --- the price as a traffic light -----------------------------------------------------
//
// A real card led with "VfB Stuttgart 8+ at 13.00" over a 4+ record, because +34% on a
// 10% shot beat +13% on a 59% one. The backend no longer picks that rung; the colour is
// the second line of defence, for every case where the only price on a side is one its
// record cannot reach.

describe("what colour the price is drawn in", () => {
  const sided = (over = {}) => ({
    name: "Bradford", pick: pick({ line: 4, book_odds: 1.94 }),
    run: { line: 4, line_label: "4+", hits: 4, settled: 5, floor: 3 },
    opp_conceded: 5.4, ...over,
  });

  it("is green when the run covers the line and it keeps landing", () => {
    expect(priceTone(sided()).tone).toBe("backed");
    expect(priceTone(sided()).why).toBe("4 of the last 5 at 4+");
  });

  it("is green for a bet UNDER the run's line, because a record reaches down", () => {
    // A side that got 5+ four times in five also got 4+ four times in five.
    expect(priceTone(sided({ run: { line: 5, hits: 4, settled: 5 } })).tone)
      .toBe("backed");
  });

  it("warns when the bet sits above the run — the Stuttgart case", () => {
    const t = priceTone(sided({ pick: pick({ line: 8, book_odds: 13 }),
                                opp_conceded: 5.4 }));
    expect(t.tone).toBe("warning");
    expect(t.why).toContain("The run is at 4+");
  });

  it("warns when the opponent does not give up that many", () => {
    // Inter concede 3.1 at home. No amount of the other side's form answers that.
    const t = priceTone(sided({ opp_conceded: 3.1, pick: pick({ line: 4 }) }));
    expect(t.tone).toBe("warning");
    expect(t.why).toContain("concedes 3.1");
  });

  it("says so once when both legs fail, not twice", () => {
    const t = priceTone(sided({ pick: pick({ line: 8, book_odds: 13 }),
                                opp_conceded: 3.1 }));
    expect(t.tone).toBe("warning");
    expect(t.why).toContain("neither reaches");
  });

  it("leaves a side with no run plain rather than red", () => {
    // Most sides on a card have no run. No evidence is not evidence against, and red on
    // every row is where this started.
    expect(priceTone(sided({ run: null })).tone).toBe("plain");
  });

  it("still warns a side with no run when the opponent is the problem", () => {
    expect(priceTone(sided({ run: null, opp_conceded: 3.1 })).tone).toBe("warning");
  });

  it("is plain for a thin run rather than green", () => {
    // 3 of 5 is a record. It is not "it keeps landing".
    expect(priceTone(sided({ run: { line: 4, hits: 3, settled: 5 } })).tone).toBe("plain");
  });

  it("judges nothing without a quoted price", () => {
    // A model fair price is an opinion; colouring it would dress one up as the other.
    expect(priceTone(sided({ pick: pick({ line: 8, book_odds: null }) })).tone)
      .toBe("plain");
    expect(priceTone(null).tone).toBe("plain");
    expect(priceTone({}).tone).toBe("plain");
  });

  it("does not warn on an opponent nobody measured", () => {
    expect(priceTone(sided({ opp_conceded: null })).tone).toBe("backed");
  });
});
