// The streak finder post, against the worked example it was specified by.
//
// WHAT THESE GUARD. The format was given as a sample post rather than described, so the
// first job is that it still reproduces that sample. After that, the failures worth a test
// are the ones that produce a post which reads perfectly and costs money:
//
//   - An UNDER row in a column of "N+" rows. At a glance it reads as an over, and it is
//     the one mistake here that loses in the opposite direction to the reader's intent.
//   - A 12-hour clock. A third of this board is Brazilian and MLS, kicking off after
//     midnight UK time; "3:30am" beside "15:00" is a conversion the reader gets wrong.
//   - A book price where the header promises a model one, or the reverse — the column is
//     labelled "Model price" and a quoted price in it is an offer nobody made.
//   - A post over Telegram's 4,096 limit: HTTP 400 and nothing else.
import {
  addDays, buildFinder, dropOn, eligible, finderOrder, finderRow, finderTime,
  finderWindow, liveDrop, londonDay, streakFinder,
  FINDER_HEAD, FINDER_KEY, FINDER_MIN_LINE, FINDER_MIN_RUN,
} from "./streakFinder.js";
import { TELEGRAM_MAX } from "./shareText.js";

const row = (name, leagueId, line, run, fair, date, extra = {}) => ({
  name, league_id: leagueId, line, direction: "over",
  streak: { length: run },
  projection: { fair_odds: fair, prob: fair ? 100 / fair : null },
  next_fixture: { fixture_id: 1, opponent: "Someone", is_home: true, date },
  ...extra,
});

// Straight from the sample post.
const SAMPLE = [
  row("Grimsby", "eng-l2", 7, 6, 3.79, "2026-09-26T14:00:00Z"),
  row("Den Bosch", "ned-ed", 5, 7, 2.47, "2026-09-27T12:30:00Z"),
  row("Hercules", "ned-ed", 5, 7, 1.21, "2026-09-26T14:30:00Z"),
  row("Stockport", "eng-l1", 5, 6, 1.25, "2026-09-26T14:00:00Z"),
  row("Novorizontino", "bra-sb", 4, 12, 1.17, "2026-09-25T22:30:00Z"),
  row("Philadelphia", "usa-ml", 4, 11, 1.14, "2026-09-26T23:30:00Z"),
  row("Goias", "bra-sb", 4, 5, 1.35, "2026-09-26T21:30:00Z"),
];

const SITE = "https://www.thecornermodel.com";


describe("it reproduces the post it was specified by", () => {
  test("the two header lines, verbatim", () => {
    const { text } = streakFinder({ rows: SAMPLE, site: SITE });
    expect(text.startsWith(`${FINDER_HEAD}\n${FINDER_KEY}\n\n`)).toBe(true);
  });

  test("a row reads line, team, run, price, date", () => {
    const [grimsby] = finderOrder(SAMPLE);
    // The sample's own first row: "7+ Grimsby 6/6 3.79 📅 Sat 15:00"
    expect(finderRow(grimsby)).toContain("7+ Grimsby 6/6 3.79 📅 Sat 15:00");
  });

  test("the run states its own sample size", () => {
    // "6/6" carries what "100%" does not. A lone percentage on a run of three reads
    // identically to one on a run of thirty.
    expect(finderRow(row("X", "eng-pl", 4, 12, 1.2, "2026-09-26T14:00:00Z")))
      .toContain("12/12");
  });

  test("it ends on the streaks page, once", () => {
    const { text } = streakFinder({ rows: SAMPLE, site: SITE });
    expect(text.endsWith(`${SITE}/streaks`)).toBe(true);
    expect(text.match(/thecornermodel/g).length).toBe(1);
  });

  test("no site means no dangling link", () => {
    expect(buildFinder({ rows: SAMPLE }).text).not.toContain("/streaks");
  });
});


describe("the order", () => {
  test("boldest line first, longest run within it", () => {
    const names = finderOrder(SAMPLE).map((r) => r.name);
    expect(names).toEqual([
      "Grimsby",                                  // 7+
      "Den Bosch", "Hercules", "Stockport",       // 5+, runs 7, 7, 6
      "Novorizontino", "Philadelphia", "Goias",   // 4+, runs 12, 11, 5
    ]);
  });

  test("a longer run does not outrank a bolder line", () => {
    // 12/12 at 4+ is more evidence, and 7+ is still the bigger claim. The header says
    // "highest stats", not "best bets", precisely because neither has been measured.
    expect(finderOrder(SAMPLE)[0].name).toBe("Grimsby");
  });

  test("a tie keeps the order the backend sent, and is not re-ranked by price", () => {
    // The worked example proves this: Den Bosch at 2.47 is printed above Hercules at 1.21
    // on the same line and the same run. Sorting ties by price here would make the post
    // disagree with the /streaks screen it links to.
    const names = finderOrder(SAMPLE).map((r) => r.name);
    expect(names.indexOf("Den Bosch")).toBeLessThan(names.indexOf("Hercules"));
    const swapped = finderOrder([...SAMPLE].reverse()).map((r) => r.name);
    expect(swapped.indexOf("Hercules")).toBeLessThan(swapped.indexOf("Den Bosch"));
  });

  test("the same rows in the same order give the same post every time", () => {
    const once = finderOrder(SAMPLE).map((r) => r.name);
    expect(finderOrder(SAMPLE).map((r) => r.name)).toEqual(once);
  });
});


describe("what may not appear", () => {
  test("an under is excluded, not relabelled", () => {
    // "under 9" in a column of "N+" rows reads as an over at a glance, and that mistake
    // loses in the opposite direction to the one the reader intended.
    const under = row("Sunderland", "eng-pl", 9, 8, 1.4, "2026-09-26T14:00:00Z",
                      { direction: "under", line_label: "under 9" });
    expect(eligible(under)).toBe(false);
    expect(buildFinder({ rows: [under] }).n).toBe(0);
  });

  test("3+ is too easy to be news", () => {
    // A side fails to win three corners in about one match in five, so a long run at 3+
    // mostly says the team turned up — and it tops the run column while saying the least.
    // The first real board had Plymouth 18/18 and Salford 17/17 at 1.16 and 1.44.
    const easy = row("Plymouth", "eng-ch", 3, 18, 1.16, "2026-09-26T14:00:00Z");
    expect(eligible(easy)).toBe(false);
    expect(buildFinder({ rows: [easy] }).n).toBe(0);
  });

  test("the floor is 4+, and 4+ itself is kept", () => {
    expect(FINDER_MIN_LINE).toBe(4);
    expect(eligible(row("X", "eng-pl", 4, 9, 1.2, "2026-09-26T14:00:00Z"))).toBe(true);
  });

  test("a longer run at 3+ cannot displace a shorter one at 4+", () => {
    // The floor is absolute, not a tiebreak — an 18-game run is exactly the row that
    // would win on any ordering that let it in at all.
    const { text, n } = buildFinder({ rows: [
      row("Plymouth", "eng-ch", 3, 18, 1.16, "2026-09-26T14:00:00Z"),
      row("Walsall", "eng-l2", 4, 4, 1.36, "2026-09-26T14:00:00Z"),
    ]});
    expect(n).toBe(1);
    expect(text).toContain("Walsall");
    expect(text).not.toContain("Plymouth");
  });

  test("a run of two is not a streak", () => {
    expect(eligible(row("X", "eng-pl", 4, FINDER_MIN_RUN - 1, 1.2, "2026-09-26T14:00:00Z")))
      .toBe(false);
  });

  test("a row with no kick-off is dropped", () => {
    // The date is half this post's usefulness; a blank there is a team nobody can act on.
    expect(eligible(row("X", "eng-pl", 4, 9, 1.2, null))).toBe(false);
  });

  test("a row with no model price still earns its place", () => {
    // The run is the claim and the price is the extra. Dropping the row loses both.
    const r = row("X", "eng-pl", 4, 9, null, "2026-09-26T14:00:00Z");
    expect(eligible(r)).toBe(true);
    expect(finderRow(r)).toContain("4+ X 9/9 📅");
  });
});


describe("the clock", () => {
  test("twenty-four hour, with the day", () => {
    expect(finderTime("2026-09-26T14:00:00Z")).toBe("Sat 15:00");
  });

  test("an overnight kick-off is unambiguous", () => {
    // A third of this board is Brazilian and MLS. "Sun 03:30" beside "Sat 15:00" needs no
    // conversion; "3:30am" does, and that is the row people get wrong.
    expect(finderTime("2026-09-27T02:30:00Z")).toBe("Sun 03:30");
  });

  test("midnight is 00, never 24", () => {
    expect(finderTime("2026-09-26T23:00:00Z")).toBe("Sun 00:00");
  });

  test("junk is empty rather than 'Invalid Date'", () => {
    expect(finderTime("not a date")).toBe("");
    expect(finderTime(null)).toBe("");
  });
});


describe("what Telegram will deliver", () => {
  test("a long board is rebuilt smaller, not cut mid-row", () => {
    const many = Array.from({ length: 60 }, (_, i) =>
      row(`Borussia Monchengladbach Reserves Number ${i}`, "ger-bl2",
          4 + (i % 4), 3 + (i % 10), 1.5, "2026-09-26T14:00:00Z"));
    const { text } = streakFinder({ rows: many, site: SITE, max: 60 });
    expect(text.length).toBeLessThanOrEqual(TELEGRAM_MAX);
    expect(text.endsWith(`${SITE}/streaks`)).toBe(true);
  });

  test("an ordinary board of twenty is comfortably inside", () => {
    const twenty = Array.from({ length: 20 }, (_, i) =>
      row(`Team ${i}`, "eng-pl", 4 + (i % 3), 5 + i, 1.4, "2026-09-26T14:00:00Z"));
    expect(streakFinder({ rows: twenty, site: SITE }).text.length)
      .toBeLessThan(TELEGRAM_MAX / 2);
  });

  test("a quiet board is no post at all", () => {
    expect(streakFinder({ rows: [], site: SITE })).toEqual({ text: "", n: 0 });
  });
});


describe("when it goes out and what it covers", () => {
  // Week of Mon 2026-09-21. Monday's drop takes the weekend; Thursday's takes the midweek.
  const MON = "2026-09-21";
  const THU = "2026-09-24";

  test("Monday publishes the weekend, Thursday the midweek", () => {
    expect(dropOn(MON)).toBe("weekend");
    expect(dropOn(THU)).toBe("midweek");
  });

  test("no other day publishes", () => {
    for (const d of ["2026-09-22", "2026-09-23", "2026-09-25", "2026-09-26", "2026-09-27"]) {
      expect(dropOn(d)).toBeNull();
    }
  });

  test("Monday's window is Friday to Monday", () => {
    expect(finderWindow("weekend", MON))
      .toEqual({ first: "2026-09-25", last: "2026-09-28", label: "Weekend" });
  });

  test("Thursday's window is Tuesday to Thursday", () => {
    expect(finderWindow("midweek", THU))
      .toEqual({ first: "2026-09-29", last: "2026-10-01", label: "Midweek" });
  });

  test("every day of the week belongs to exactly one drop", () => {
    // A day covered twice is a fixture claimed twice; a day covered by neither is a night
    // this site never had a view on. This is the whole reason the windows are what they are.
    const w = finderWindow("weekend", MON);
    const m = finderWindow("midweek", THU);
    const days = [];
    for (let d = w.first; d <= w.last; d = addDays(d, 1)) days.push(d);
    for (let d = m.first; d <= m.last; d = addDays(d, 1)) days.push(d);
    expect(days.length).toBe(7);
    expect(new Set(days).size).toBe(7);
    // Contiguous: Fri 25th through Thu 1st, no gap.
    expect(days.sort()).toEqual([
      "2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28",
      "2026-09-29", "2026-09-30", "2026-10-01",
    ]);
  });

  test("a row outside the window does not reach the post", () => {
    const w = finderWindow("weekend", MON);
    const inside = row("Grimsby", "eng-l2", 7, 6, 3.79, "2026-09-26T14:00:00Z");
    const outside = row("Elsewhere", "eng-l2", 7, 9, 3.79, "2026-09-30T14:00:00Z");
    const { text, n } = buildFinder({ rows: [outside, inside], ...w });
    expect(n).toBe(1);
    expect(text).toContain("Grimsby");
    expect(text).not.toContain("Elsewhere");
  });

  test("the window is applied before the cap, not after", () => {
    // Trimming to twenty first and windowing second posts three rows on a full weekend.
    const w = finderWindow("weekend", MON);
    const far = Array.from({ length: 30 }, (_, i) =>
      row(`Far ${i}`, "eng-pl", 9, 20, 5.0, "2026-09-30T14:00:00Z"));
    const near = Array.from({ length: 5 }, (_, i) =>
      row(`Near ${i}`, "eng-pl", 4, 6, 1.3, "2026-09-26T14:00:00Z"));
    expect(buildFinder({ rows: [...far, ...near], max: 20, ...w }).n).toBe(5);
  });

  test("no window means no filtering, for an ad-hoc post", () => {
    expect(buildFinder({ rows: SAMPLE }).n).toBe(SAMPLE.length);
  });

  test("on a publishing day, that day's drop is the live one", () => {
    expect(liveDrop(MON)).toEqual({ drop: "weekend", publishedOn: MON });
    expect(liveDrop(THU)).toEqual({ drop: "midweek", publishedOn: THU });
  });

  test("between drops it walks BACK to the last one, never forward", () => {
    // On a Tuesday the live list is Monday's weekend. Looking forward would hand the
    // reader Thursday's midweek for games that have not been selected yet — and it is
    // what makes an off-schedule send carry the window the channel is already expecting.
    expect(liveDrop("2026-09-22")).toEqual({ drop: "weekend", publishedOn: MON });
    expect(liveDrop("2026-09-23")).toEqual({ drop: "weekend", publishedOn: MON });
    expect(liveDrop("2026-09-25")).toEqual({ drop: "midweek", publishedOn: THU });
    expect(liveDrop("2026-09-27")).toEqual({ drop: "midweek", publishedOn: THU });
  });

  test("every day of the week has a live drop", () => {
    for (let i = 0; i < 7; i += 1) {
      expect(liveDrop(addDays(MON, i))).not.toBeNull();
    }
  });

  test("a kick-off is placed by its London day, not its UTC one", () => {
    // A 23:30 UTC Friday kick-off in Brazil is Saturday 00:30 in London, and the window is
    // stated in London days — the same clock the post prints.
    expect(londonDay("2026-09-25T23:30:00Z")).toBe("2026-09-26");
  });
});
