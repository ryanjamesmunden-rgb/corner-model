// The one post that goes to the channel.
//
// WHAT THESE GUARD. Not "does it render" — the failures worth testing for are the ones
// that produce a card which looks completely normal and misleads the person reading it:
//
//   - The same team under three headings, so twelve rows are really four and the reader
//     cannot tell which one to act on.
//   - A seeded price in the Value section. seed_team_odds writes `fair_odds * uniform(0.90,
//     1.15)`, so an EV against one is the model finding value in its own noise. On screen
//     it is indistinguishable from a real edge.
//   - An empty Value section that does not say WHICH kind of empty. "Nothing priced" is a
//     job to do; "nothing beats its price" is a reason not to bet. A blank reads as neither
//     and the reader supplies the flattering one.
//   - A card over Telegram's 4,096 limit. That is an HTTP 400 and nothing else — the exact
//     failure the weekend card hit twice, reporting success both times.
//   - A post that looks like a card and contains no angle.
import { buildCard, dailyCard, pricedFixtures, CARD_MIN_RUN } from "./dailyCard.js";
import { TELEGRAM_MAX } from "./shareText.js";

const fx = (id, opponent = "Chelsea", isHome = true) => ({
  fixture_id: id, opponent, is_home: isHome, date: "2026-09-22T19:00:00Z",
});

const chaseRow = (name, id, line = 4) => ({
  name, league_id: "eng-pl", league_name: "Premier League", line,
  next_fixture: fx(id), consistency: 4, consistency_of: 5,
  team_for: 6.2, opp_conceded: 5.8, lambda: 5.4, prob: 72.5,
  fair_odds: 1.38, book_odds: 1.45, ev: 5.1,
});

const mismatchRow = (name, id, line = 5) => ({
  name, league_id: "esp-ll", line, team_for: 7.1, opp_conceded: 6.4,
  prob: 68.0, fair_odds: 1.47, next_fixture: fx(id, "Getafe"),
});

const streakRow = (name, id, run = 6) => ({
  name, league_id: "ita-sa", line_label: "4+ corners",
  streak: { length: run }, next_fixture: fx(id, "Lazio"),
  projection: { prob: 70.0, fair_odds: 1.43 },
});

const valueRow = (id, ev = 8.4, source = "manual") => ({
  fixture_id: id, league_id: "ger-bl", home: "Mainz", away: "Koln",
  date: "2026-09-22T18:30:00Z", odds_source: source,
  best: { label: "Mainz 5+ corners", book_odds: 2.1, fair_odds: 1.9, ev },
});

// The card is built FOR a day, and slateFrom filters the chase board to that day's
// kickoffs. Pinning it keeps these tests from passing in the morning and failing at night.
const DAY = "2026-09-22";

const base = {
  day: DAY,
  chase: [chaseRow("Arsenal", 101), chaseRow("Napoli", 102)],
  mismatches: [mismatchRow("Barcelona", 201)],
  streaks: [streakRow("Inter", 301)],
  value: [valueRow(401)],
  site: "https://thecornermodel.com",
};


describe("what the card contains", () => {
  test("all four sections, chase first", () => {
    const { text } = dailyCard(base);
    const at = (s) => text.indexOf(s);
    expect(at("🎯 THE CHASE BOARD")).toBeGreaterThan(-1);
    // The chase board is what the channel actually gets posted, so it leads. Streaks are
    // the weakest claim alone and must not be mistaken for the headline.
    expect(at("🎯 THE CHASE BOARD")).toBeLessThan(at("⚔️ TOP MISMATCHES"));
    expect(at("⚔️ TOP MISMATCHES")).toBeLessThan(at("🔥 RUNNING STREAKS"));
    expect(at("🔥 RUNNING STREAKS")).toBeLessThan(at("💰 PRICED UP"));
  });

  test("a chase row names the team whose corners they are", () => {
    // "5+ corners" beside a fixture reads as the MATCH total, which is roughly twice the
    // number and a completely different bet.
    expect(dailyCard(base).text).toContain("Arsenal 4+ corners");
  });

  test("a chase row carries its argument, not just its number", () => {
    const { text } = dailyCard(base);
    expect(text).toContain("6.2 for home");
    expect(text).toContain("opp concede 5.8");
    expect(text).toContain("cleared 4 of 5");
  });

  test("counts report what actually went out per section", () => {
    // A quiet day and a broken board look identical without this.
    expect(dailyCard(base).counts)
      .toEqual({ chase: 2, mismatch: 1, streak: 1, value: 1 });
  });
});


describe("a team appears once", () => {
  test("a team on the chase board is not repeated under mismatches or streaks", () => {
    const { text, counts } = dailyCard({
      ...base,
      chase: [chaseRow("Arsenal", 101)],
      mismatches: [mismatchRow("Arsenal", 101)],
      streaks: [streakRow("Arsenal", 101)],
    });
    expect(counts).toMatchObject({ chase: 1, mismatch: 0, streak: 0 });
    // Asserted by SECTION, not by counting the name: a chase row prints the team twice
    // on purpose — once in "Arsenal v Chelsea" and once in "Arsenal 4+ corners", because
    // the market has to say whose corners it is. Counting occurrences would fail on a
    // correct card and pass on a broken one whose repeat happened to render differently.
    const after = text.slice(text.indexOf("⚔️ TOP MISMATCHES"));
    expect(after).not.toContain("Arsenal");
  });

  test("the corroboration becomes a marker instead of a second row", () => {
    const { text } = dailyCard({
      ...base,
      chase: [],
      mismatches: [mismatchRow("Inter", 301)],
      streaks: [streakRow("Inter", 301)],
    });
    // Mismatch keeps the row (it is the stronger claim); the run is not silently lost.
    expect(text).toContain("⚔️ TOP MISMATCHES");
    expect(text).not.toContain("🔥 RUNNING STREAKS");
  });

  test("the same team in a DIFFERENT fixture is a different row", () => {
    const { counts } = dailyCard({
      ...base,
      chase: [chaseRow("Arsenal", 101)],
      mismatches: [mismatchRow("Arsenal", 999)],
      streaks: [],
    });
    expect(counts).toMatchObject({ chase: 1, mismatch: 1 });
  });
});


describe("the value section", () => {
  test("a seeded price never reaches the card", () => {
    // seed_team_odds writes fair_odds * uniform(0.90, 1.15). An EV against that is the
    // model finding value in its own jitter, and it looks exactly like a real edge.
    const { text, counts } = dailyCard({ ...base, value: [valueRow(401, 12.0, "seed")] });
    expect(counts.value).toBe(0);
    expect(text).not.toContain("Mainz");
  });

  test("a priced market with no edge is not an edge", () => {
    const { counts } = dailyCard({ ...base, value: [valueRow(401, -3.0)] });
    expect(counts.value).toBe(0);
  });

  test("nothing priced says so, and says it is a job to do", () => {
    const { text } = dailyCard({ ...base, value: [] });
    expect(text).toContain("No prices entered yet");
  });

  test("priced but beaten by nothing says the opposite thing", () => {
    // Opposite facts. A blank section reads as neither.
    const { text } = dailyCard({ ...base, value: [valueRow(401, -2.0)] });
    expect(text).toContain("nothing beats its price");
    expect(text).not.toContain("No prices entered yet");
  });

  test("best edge leads", () => {
    const { text } = dailyCard({
      ...base,
      value: [valueRow(401, 3.0), { ...valueRow(402, 11.0), home: "Bayern" }],
    });
    expect(text.indexOf("Bayern")).toBeLessThan(text.indexOf("Mainz"));
  });

  test("a priced game is marked on the row above rather than de-duplicated away", () => {
    // "keeps clearing the line" and "this price is long" are different claims about the
    // same game, and the second is the one worth money.
    const { text } = dailyCard({
      ...base,
      chase: [chaseRow("Arsenal", 401)],
      value: [valueRow(401)],
    });
    expect(text).toContain("💰");
    expect(text).toContain("💰 PRICED UP");
  });

  test("prices always carry two decimals", () => {
    // "@ 1.4" beside "fair 1.35" reads as a rounder number than the one under it, and on
    // a card about prices it invites the question of whether it means 1.40 or 1.45.
    const { text } = dailyCard({
      ...base,
      chase: [{ ...chaseRow("Arsenal", 101), book_odds: 1.4, ev: 4.0 }],
      value: [{ ...valueRow(401), best: { label: "Mainz 5+ corners", book_odds: 2.1, fair_odds: 1.9, ev: 8.4 } }],
    });
    expect(text).toContain("@ 1.40");
    expect(text).not.toMatch(/@ \d+\.\d(?!\d)/);
    expect(text).toContain("@ 2.10");
    expect(text).toContain("fair 1.90");
  });

  test("pricedFixtures counts only manual prices with a real edge", () => {
    expect([...pricedFixtures([
      valueRow(1, 5.0, "manual"), valueRow(2, 5.0, "seed"), valueRow(3, -1.0, "manual"),
    ])]).toEqual([1]);
  });
});


describe("streaks", () => {
  test("two games is not a streak", () => {
    expect(dailyCard({ ...base, streaks: [streakRow("Inter", 301, CARD_MIN_RUN - 1)] })
      .counts.streak).toBe(0);
  });

  test("the longest run leads", () => {
    const { text } = dailyCard({
      ...base,
      streaks: [streakRow("Inter", 301, 4), streakRow("Roma", 302, 9)],
    });
    expect(text.indexOf("Roma")).toBeLessThan(text.indexOf("Inter"));
  });
});


describe("what Telegram will actually deliver", () => {
  const longName = (i) => `Borussia Monchengladbach Reserves Number ${i}`;

  test("a board of long names is rebuilt smaller, not cut", () => {
    const big = {
      ...base,
      chase: Array.from({ length: 10 }, (_, i) => chaseRow(longName(i), 100 + i)),
      mismatches: Array.from({ length: 10 }, (_, i) => mismatchRow(longName(i), 200 + i)),
      streaks: Array.from({ length: 10 }, (_, i) => streakRow(longName(i), 300 + i)),
      value: Array.from({ length: 10 }, (_, i) => valueRow(400 + i, 5 + i)),
    };
    const { text } = dailyCard(big);
    expect(text.length).toBeLessThanOrEqual(TELEGRAM_MAX);
    // Rebuilt, not trimmed: no row ends mid-link.
    expect(text.endsWith("/fixture/")).toBe(false);
    expect(text).not.toMatch(/\/fixture\/\s*$/);
  });

  test("an ordinary card is nowhere near the limit", () => {
    expect(dailyCard(base).text.length).toBeLessThan(TELEGRAM_MAX / 2);
  });
});


describe("an honest nothing", () => {
  test("no angles at all produces no post", () => {
    // A post that looks like a card and carries no angle trains the reader to skim.
    expect(dailyCard({ day: DAY, chase: [], mismatches: [], streaks: [], value: [] }).text).toBe("");
  });

  test("a value-only day is still not a card", () => {
    expect(dailyCard({ day: DAY, chase: [], mismatches: [], streaks: [], value: [valueRow(401)] })
      .text).toBe("");
  });

  test("no site means no broken links rather than a bare arrow", () => {
    const { text } = buildCard({ ...base, site: "" });
    expect(text).not.toContain("↳");
  });
});
