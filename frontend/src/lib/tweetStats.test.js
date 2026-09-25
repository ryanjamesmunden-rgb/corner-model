// Several statistics a day.
//
// WHAT THESE GUARD. Same account, same audience, same rules as tweetStat — and now several
// posts a day instead of one, so every failure it guarded against gets more chances:
//
//   - A PREDICTION. Every sentence must describe matches already played.
//   - A NAMED TEAM. The names are the paid half and the reason to click.
//   - A LOOSENED BAR ON A QUIET DAY. Each candidate states a threshold and counts what
//     clears it; a candidate that cannot clear its own bar is dropped, never widened.
//   - TWO POSTS THAT ARE THE SAME POST. A board where every run is long would otherwise
//     produce "20 teams on 4+" and "20 of them on 10+" — padding, and it looks like it.
//   - OVER 280 by X's weighted count, with the link counted.
import {
  BUILDERS, DEEP_RUN, EXAMPLES, HIGH_LINE, MIN_SUBJECTS, MISMATCH_BAR, breadthStat, dedupe,
  deepRunStat, examplesLine, highLineStat, mismatchStat, pickExamples, todayStat,
  tweetStats, ukDay, STAT_MIN_LINE, STAT_MIN_RUN,
} from "./tweetStats.js";
import { xWeight, X_MAX_WEIGHT } from "./xLimit.js";

const SITE = "https://thecornermodel.com";
const NOW = new Date("2026-09-26T09:00:00Z");
const TODAY = "2026-09-26T14:00:00Z";
const TOMORROW = "2026-09-27T14:00:00Z";

let nextId = 1;
const row = (name, leagueId, line, run, date = TOMORROW, opp = null, home = true) => ({
  name, league_id: leagueId, line, direction: "over",
  streak: { length: run },
  projection: { fair_odds: 1.4 },
  // A DISTINCT FIXTURE PER ROW. Sharing one id made every row the same tie, and the
  // examples would collapse to one — which is a property worth testing, not a fixture bug
  // to leave lying around. See the dedupe test below for the shared-tie case.
  next_fixture: { fixture_id: (nextId += 1), opponent: opp || `Rival ${name}`,
                  is_home: home, date },
});

const board = (n, leagueId = "eng-l2", line = 4, run = 6, date = TOMORROW) =>
  Array.from({ length: n }, (_, i) => row(`Team ${i}`, leagueId, line, run, date));

const mm = (name, leagueId, teamFor, oppConceded) => ({
  name, league_id: leagueId, team_for: teamFor, opp_conceded: oppConceded,
  lambda: 11.2, line: 10, prob: 62.0,
  next_fixture: { fixture_id: (nextId += 1), opponent: `Rival ${name}`,
                  is_home: true, date: TOMORROW },
});

const mmBoard = (n, teamFor = 6.4, oppConceded = 6.8) =>
  Array.from({ length: n }, (_, i) => mm(`Side ${i}`, "ned-ed", teamFor, oppConceded));

const allText = (cands) => cands.map((c) => c.text).join("\n");


describe("the rules every candidate obeys", () => {
  const every = tweetStats({
    rows: [...board(14), ...board(6, "bra-sb", 5, 12, TODAY)],
    mismatches: mmBoard(8), days: 3, site: SITE, now: NOW,
  });

  test("there is more than one of them", () => {
    expect(every.length).toBeGreaterThan(1);
  });

  test("none of them predicts", () => {
    const text = allText(every).toLowerCase();
    for (const word of ["will win", "are due", "expect", "tip", "best bet",
                        "value", "banker", "nap", "guarantee", "likely to"]) {
      expect(text).not.toContain(word);
    }
  });

  test("all of them describe matches already played", () => {
    for (const c of every) {
      expect(c.text).toMatch(/have won|average|has shipped|concede/);
    }
  });

  test("each names exactly two games, not the list", () => {
    // A DELIBERATE REVERSAL. These posts named nobody, on the reasoning that the names are
    // the reason to click and a post answering its own hook has given the product away.
    // Two of twenty does the opposite: an aggregate nobody can check reads like a claim,
    // and the same aggregate with two games attached reads like a fact. The eighteen others
    // still need the link.
    //
    // WHAT THIS GUARDS IS THE CEILING. "Two examples" becoming "here is the board" is the
    // failure, and it would happen one row at a time.
    const named = tweetStats({
      rows: board(20).map((r, i) => ({ ...r, name: `Distinctive${i}`,
        next_fixture: { ...r.next_fixture, fixture_id: i, opponent: `Rival${i}` } })),
      days: 3, site: SITE, now: NOW,
    });
    for (const c of named) {
      const hits = (c.text.match(/Distinctive/g) || []).length;
      expect(hits).toBeLessThanOrEqual(EXAMPLES);
      expect(hits).toBeGreaterThan(0);
    }
  });

  test("naming a game does not turn it into a recommendation", () => {
    // The line that must not move. "Plymouth v Wycombe (18 in a row)" is a record of
    // eighteen matches already played; it becomes a tip the moment it carries a price, a
    // probability or an instruction.
    const text = allText(every).toLowerCase();
    for (const word of ["back ", "bet on", "watch", "worth a", "@", "odds", "price",
                        "fair ", "%"]) {
      expect(text).not.toContain(word);
    }
  });

  test("all of them send the reader to the list", () => {
    for (const c of every) expect(c.text).toContain("thecornermodel.com/streaks");
  });

  test("all of them fit once the link is counted", () => {
    for (const c of every) {
      expect(xWeight(c.text)).toBeLessThanOrEqual(X_MAX_WEIGHT);
    }
  });

  test("each carries a key so the sender can label them", () => {
    const keys = every.map((c) => c.key);
    expect(new Set(keys).size).toBe(keys.length);
    for (const k of keys) expect(BUILDERS.map(([n]) => n)).toContain(k);
  });
});


describe("the breadth post is still the lead", () => {
  test("it comes first and reads as before", () => {
    const [first] = tweetStats({ rows: board(23), days: 3, site: SITE, now: NOW });
    expect(first.key).toBe("breadth");
    expect(first.text.startsWith("23 teams")).toBe(true);
  });

  test("a board below the minimum yields no breadth post", () => {
    expect(breadthStat({ rows: board(3), days: 3, site: SITE })).toBeNull();
  });
});


describe("the deep-run post is a different claim, not a re-cut", () => {
  test("it counts only the long runs", () => {
    const rows = [...board(15, "eng-l2", 4, 6), ...board(6, "ned-ed", 4, DEEP_RUN + 2)];
    const c = deepRunStat({ rows, days: 3, site: SITE });
    expect(c.stats.teams).toBe(6);
    expect(c.stats.of).toBe(21);
    expect(c.text).toContain(`${DEEP_RUN} games or more`);
  });

  test("too few long runs is no post rather than a shorter bar", () => {
    const rows = [...board(20), ...board(MIN_SUBJECTS - 1, "ned-ed", 4, DEEP_RUN)];
    expect(deepRunStat({ rows, days: 3, site: SITE })).toBeNull();
  });
});


describe("the high-line post carries its denominator", () => {
  test("six of twenty reads as six of twenty", () => {
    const rows = [...board(14, "eng-l2", 4, 6), ...board(6, "ned-ed", HIGH_LINE, 7)];
    const c = highLineStat({ rows, days: 3, site: SITE });
    expect(c.stats.teams).toBe(6);
    expect(c.text).toContain(`${HIGH_LINE}+ corners`);
    expect(c.text).toContain("6 of the 20");
  });

  test("it never counts a line below its own bar", () => {
    const c = highLineStat({ rows: board(30, "eng-ch", STAT_MIN_LINE, 9), site: SITE });
    expect(c).toBeNull();
  });
});


describe("today is today in UK time", () => {
  test("it counts only games kicking off on the UK calendar day", () => {
    const rows = [...board(6, "eng-l2", 4, 6, TODAY), ...board(9, "ned-ed", 4, 7, TOMORROW)];
    const c = todayStat({ rows, days: 3, site: SITE, now: NOW });
    expect(c.stats.teams).toBe(6);
    expect(c.text).toContain("playing today");
  });

  test("a late kick-off belongs to the UK day, not the UTC one", () => {
    // 23:30Z on the 26th is half past midnight on the 27th in London — so it is NOT today.
    expect(ukDay("2026-09-26T23:30:00Z")).toBe("2026-09-27");
    const rows = board(10, "eng-l2", 4, 6, "2026-09-26T23:30:00Z");
    expect(todayStat({ rows, days: 3, site: SITE, now: NOW })).toBeNull();
  });

  test("a one-day window has no separate today post", () => {
    // It would be the breadth post word for word.
    expect(todayStat({ rows: board(20, "eng-l2", 4, 6, TODAY),
                       days: 1, site: SITE, now: NOW })).toBeNull();
  });
});


describe("the mismatch post states two recorded averages and stops", () => {
  test("both sides have to clear the bar", () => {
    const rows = [...mmBoard(6, 6.5, 6.9), ...mmBoard(9, 6.5, 3.0)];
    const c = mismatchStat({ mismatches: rows, days: 3, site: SITE });
    expect(c.stats.teams).toBe(6);
    expect(c.text).toContain(`${MISMATCH_BAR}+ corners a game`);
  });

  test("it reports the leakiest opponent as a number, not a name", () => {
    const c = mismatchStat({ mismatches: [...mmBoard(5), mm("X", "ned-ed", 6.2, 9.4)],
                             days: 3, site: SITE });
    expect(c.stats.mostLeaked).toBe(9.4);
    expect(c.text).toContain("9.4");
    expect(c.text).not.toContain("X ");
  });

  test("no mismatch board is no mismatch post", () => {
    expect(mismatchStat({ mismatches: [], days: 3, site: SITE })).toBeNull();
  });
});


describe("a quiet board", () => {
  test("produces nothing at all rather than a small number", () => {
    expect(tweetStats({ rows: board(2), mismatches: [], days: 3, site: SITE, now: NOW }))
      .toEqual([]);
  });

  test("a bar is never loosened to reach a candidate", () => {
    // Twenty teams on 3+ is a quiet day for this account and must read as one.
    const rows = board(20, "eng-ch", 3, 18);
    expect(tweetStats({ rows, days: 3, site: SITE, now: NOW })).toEqual([]);
  });

  test("one weak board does not suppress a strong one", () => {
    // The whole point of several candidates: a quiet streak board still leaves the
    // mismatch post standing.
    const out = tweetStats({ rows: board(2), mismatches: mmBoard(9),
                             days: 3, site: SITE, now: NOW });
    expect(out.map((c) => c.key)).toEqual(["mismatch"]);
  });
});


describe("two posts that are the same post", () => {
  test("a repeated headline count is dropped", () => {
    // Every run long means "20 teams on 4+" and "20 of them on 10+" are one sentence twice.
    const rows = board(20, "eng-l2", 4, DEEP_RUN + 3);
    const keys = tweetStats({ rows, days: 3, site: SITE, now: NOW }).map((c) => c.key);
    expect(keys).toContain("breadth");
    expect(keys).not.toContain("deep");
  });

  test("dedupe keeps the first of an equal pair", () => {
    const a = { key: "a", text: "x", stats: { teams: 9 } };
    const b = { key: "b", text: "y", stats: { teams: 9 } };
    const c = { key: "c", text: "z", stats: { teams: 4 } };
    expect(dedupe([a, b, c]).map((x) => x.key)).toEqual(["a", "c"]);
  });
});


// NAMING TWO OF THEM.
//
// Asked for: the aggregate alone reads like a claim, and the same aggregate with two games
// attached reads like a fact. The failures worth guarding are the ones that turn a sample
// into the list, print a game twice, or get the fixture the wrong way round.
describe("the two example games", () => {
  test("a home run reads with our side first, an away run second", () => {
    // The fixture as it really is, not always our team first — a reader checking it against
    // a fixture list has to find the same match.
    const home = row("Plymouth", "eng-l2", 4, 18, TOMORROW, "Wycombe", true);
    const away = row("Salford", "eng-l2", 4, 17, TOMORROW, "Barrow", false);
    expect(examplesLine([home, away])).toBe(
      "Two of them: Plymouth v Wycombe (18 in a row), Barrow v Salford (17).");
  });

  test("the longest runs are the ones named", () => {
    const rows = [...board(10, "eng-l2", 4, 6),
                  row("Long", "ned-ed", 4, 19, TOMORROW, "Opp", true),
                  row("Longer", "ned-ed", 4, 21, TOMORROW, "Opp2", true)];
    expect(pickExamples(rows).map((e) => e.run)).toEqual([21, 19]);
  });

  test("one game is named once, however many of its sides are on a run", () => {
    // Both teams in a tie can be running. The same fixture printed twice is one example
    // and a mistake the reader will spot before we do.
    const a = { ...row("A", "eng-l2", 4, 9, TOMORROW, "B", true) };
    const b = { ...row("B", "eng-l2", 4, 8, TOMORROW, "A", false),
                next_fixture: { ...a.next_fixture, opponent: "A", is_home: false } };
    expect(pickExamples([a, b])).toHaveLength(1);
  });

  test("a row with no opponent still names the team rather than 'undefined'", () => {
    const bare = { name: "Solo", league_id: "eng-l2", line: 4, direction: "over",
                   streak: { length: 12 }, next_fixture: { date: TOMORROW } };
    expect(examplesLine([bare])).toBe("One of them: Solo (12 in a row).");
  });

  test("'in a row' is spelled out once, then the bracket is just the number", () => {
    // By the second the reader knows what the bracket means, and saying it again costs
    // characters the post does not have.
    const line = examplesLine([row("A", "eng-l2", 4, 9, TOMORROW, "X", true),
                               row("B", "eng-l2", 4, 8, TOMORROW, "Y", true)]);
    expect(line.match(/in a row/g)).toHaveLength(1);
    expect(line).toContain("(8)");
  });

  test("an empty board names nothing rather than an empty sentence", () => {
    expect(examplesLine([])).toBe("");
  });

  test("the mismatch post names games without a run in brackets", () => {
    // Those rows carry averages, not runs. "(0 in a row)" would be a different quantity
    // wearing the same notation.
    const c = mismatchStat({ mismatches: mmBoard(9), days: 3, site: SITE });
    expect(c.text).toMatch(/Two of them: [^(]+ v [^(]+, /);
    expect(c.text).not.toContain("in a row");
  });

  test("the examples come before the context, so a long day does not drop them", () => {
    // fitToPost drops from the tail. These were asked for; the spread and the total are
    // context and give way first.
    // Two leagues, so the "They span N countries" sentence actually exists to sit after.
    const rows = [...board(12, "eng-l2"), ...board(8, "ned-ed")];
    const c = breadthStat({ rows, days: 3, site: SITE });
    expect(c.text).toContain("They span");
    expect(c.text.indexOf("Two of them")).toBeLessThan(c.text.indexOf("They span"));
  });

  test("the named pair is not also quoted as 'the longest run is'", () => {
    // The examples ARE the longest two, so both would print the same numbers twice.
    const rows = [...board(10, "eng-l2", 4, 6),
                  row("L", "ned-ed", 4, 20, TOMORROW, "O", true),
                  row("M", "ned-ed", 4, 19, TOMORROW, "P", true)];
    const c = breadthStat({ rows, days: 3, site: SITE });
    expect(c.text).toContain("(20 in a row)");
    expect(c.text).not.toContain("The longest run is");
  });

  test("they are carried on the stats too, not only in the prose", () => {
    // So a caller can render them differently without re-deriving which two we chose.
    const c = breadthStat({ rows: board(20), days: 3, site: SITE });
    expect(c.stats.examples).toHaveLength(EXAMPLES);
    expect(c.stats.examples[0]).toHaveProperty("label");
    expect(c.stats.examples[0]).toHaveProperty("run");
  });
});


describe("how many are offered", () => {
  test("the limit is respected", () => {
    const rows = [...board(14), ...board(6, "bra-sb", 5, 12, TODAY)];
    const out = tweetStats({ rows, mismatches: mmBoard(8), days: 3, site: SITE,
                             now: NOW, limit: 2 });
    expect(out).toHaveLength(2);
  });

  test("a full board offers several distinct angles", () => {
    const rows = [...board(14, "eng-l2", 4, 6),
                  ...board(6, "bra-sb", 5, 12, TODAY),
                  ...board(5, "ned-ed", 4, DEEP_RUN + 1)];
    const out = tweetStats({ rows, mismatches: mmBoard(8), days: 3, site: SITE, now: NOW });
    expect(out.length).toBeGreaterThanOrEqual(3);
    expect(new Set(out.map((c) => c.text)).size).toBe(out.length);
  });
});
