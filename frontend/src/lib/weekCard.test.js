import { boardLabel, cardNote, dayStrip, lineLabel, priceOf, recordOf, recordText,
         slotsOf, warningsOf } from "./weekCard";

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

  it("says plainly when the run is at a different line from the bet", () => {
    // THE BUG THIS PREVENTS: a 5+ record printed under a 6+ price reads as a 6+ record.
    const text = recordText(side({
      pick: pick({ line: 6 }), run_matches_pick: false,
      run: { line: 5, line_label: "5+", hits: 9, settled: 10, floor: 4 },
    }));
    expect(text).toBe("5+ in 9 of 10, lowest 4 — not this line");
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
    const days = dayStrip(new Date("2026-11-23T10:00:00Z"), 7);
    expect(days).toHaveLength(7);
    expect(days[0].short).toBe("Today");
    expect(days[1].short).toBe("Tomorrow");
    expect(days[2].short).toBe("Wed");
  });

  it("uses UK days, so a late kick-off is filed where the reader expects it", () => {
    // 23:30 UTC in June is 00:30 the next day in London. The strip must agree with the
    // backend, which buckets by London date.
    const days = dayStrip(new Date("2026-06-10T23:30:00Z"), 2);
    expect(days[0].value).toBe("2026-06-11");
  });

  it("labels each day in full for the heading", () => {
    expect(dayStrip(new Date("2026-11-23T10:00:00Z"), 1)[0].label)
      .toBe("Mon 23 Nov");
  });
});
