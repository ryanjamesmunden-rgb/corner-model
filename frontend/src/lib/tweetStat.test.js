// The daily public post.
//
// WHAT THESE GUARD. This is the only thing here that goes to people who have never heard
// of the site, under its name, with no price and no qualification attached. The failures
// that matter are not rendering ones:
//
//   - A PREDICTION. "have won" is a fact about matches already played; "will win" or "are
//     due" is a tip. A streak is the weakest reading of a team on its own — five clears
//     can be five coin flips — so the post states the run and stops.
//   - A NAMED TEAM. The names are the paid half and the reason to click. A post that
//     answers its own hook has given the product away and is a worse post.
//   - A NUMBER THAT DOES NOT TIE UP with the channel post. Somebody clicking through
//     should find the list the headline promised.
//   - A LOOSENED BAR ON A QUIET DAY, which is how a daily statistic stops meaning
//     anything.
//   - Over 280 by X's WEIGHTED count, where a flag costs 2 and JavaScript says 14.
import {
  counted, statsFrom, tweetStat, STAT_MIN_LINE, STAT_MIN_RUN, STAT_MIN_TEAMS,
} from "./tweetStat.js";
import { xWeight, X_MAX_WEIGHT } from "./xLimit.js";

const row = (name, leagueId, line, run) => ({
  name, league_id: leagueId, line, direction: "over",
  streak: { length: run },
  projection: { fair_odds: 1.4 },
  next_fixture: { fixture_id: 1, opponent: "Someone", is_home: true,
                  date: "2026-09-26T14:00:00Z" },
});

const board = (n, leagueId = "eng-l2", line = 4, run = 6) =>
  Array.from({ length: n }, (_, i) => row(`Team ${i}`, leagueId, line, run));

const SITE = "https://thecornermodel.com";


describe("what it counts", () => {
  test("the same bar the channel post uses", () => {
    // A tweet counting rows the finder excludes sends people to a shorter list than the
    // number that brought them, and the first thing they learn is that it does not tie up.
    expect(STAT_MIN_LINE).toBe(4);
    expect(STAT_MIN_RUN).toBe(5);
  });

  test("a 3+ line is not counted", () => {
    expect(counted([row("Plymouth", "eng-ch", 3, 18)])).toEqual([]);
  });

  test("a short run is not counted", () => {
    expect(counted([row("X", "eng-pl", 4, STAT_MIN_RUN - 1)])).toEqual([]);
  });

  test("an under is not counted", () => {
    const under = { ...row("X", "eng-pl", 9, 8), direction: "under" };
    expect(counted([under])).toEqual([]);
  });

  test("a row with no kick-off is not counted", () => {
    const noDate = { ...row("X", "eng-pl", 4, 8), next_fixture: { fixture_id: 1 } };
    expect(counted([noDate])).toEqual([]);
  });
});


describe("the facts", () => {
  test("teams, countries and the total are what they say", () => {
    const rows = [row("A", "eng-l2", 4, 6), row("B", "ned-ed", 5, 7),
                  row("C", "bra-sb", 4, 12)];
    const s = statsFrom(rows);
    expect(s.teams).toBe(3);
    expect(s.countries).toBe(3);
    expect(s.clears).toBe(25);          // 6 + 7 + 12, "between them"
    expect(s.longest).toBe(12);
    expect(s.second).toBe(7);
  });

  test("two divisions of one country count once", () => {
    // "9 countries" is a claim a reader can check at a glance; counting leagues would
    // inflate it with England four times over.
    const s = statsFrom([row("A", "eng-pl", 4, 6), row("B", "eng-l2", 4, 6),
                         row("C", "eng-ch", 4, 6)]);
    expect(s.countries).toBe(1);
  });

  test("a cup is its own competition rather than a guessed country", () => {
    // countryCodeFor returns "" for a cup — there is no honest short code for "twenty
    // countries" — so it must not collapse every cup into one bucket with the unknowns.
    const s = statsFrom([row("A", "ucl", 5, 6), row("B", "uel", 5, 6)]);
    expect(s.countries).toBe(2);
  });

  test("an empty board has no facts rather than zeroes", () => {
    expect(statsFrom([])).toBeNull();
  });
});


describe("what the post may say", () => {
  const post = () => tweetStat({ rows: board(23), days: 3, site: SITE }).text;

  test("it describes matches already played", () => {
    expect(post()).toContain("have won");
  });

  test("it never predicts", () => {
    // The line between a statistic and a tip, on an account with no price attached.
    const text = post().toLowerCase();
    for (const word of ["will win", "are due", "expect", "tip", "best bet",
                        "value", "banker", "nap", "guarantee"]) {
      expect(text).not.toContain(word);
    }
  });

  test("it names nobody", () => {
    const rows = board(20).map((r, i) => ({ ...r, name: `Distinctive${i}` }));
    const { text } = tweetStat({ rows, days: 3, site: SITE });
    expect(text).not.toContain("Distinctive");
  });

  test("it sends the reader to the list", () => {
    expect(post()).toContain("thecornermodel.com/streaks");
  });

  test("the headline count is the number of qualifying teams", () => {
    const { text, stats } = tweetStat({ rows: board(23), days: 3, site: SITE });
    expect(stats.teams).toBe(23);
    expect(text.startsWith("23 teams")).toBe(true);
  });

  test("one team reads as one team", () => {
    const { text } = tweetStat({ rows: board(7), days: 3, site: SITE, minTeams: 1 });
    expect(text).toContain("7 teams");
    const single = tweetStat({ rows: board(1), days: 3, site: SITE, minTeams: 1 });
    expect(single.text).toContain("1 team ");
  });

  test("a one-day window reads as today", () => {
    expect(tweetStat({ rows: board(20), days: 1, site: SITE }).text).toContain("today");
  });
});


describe("a quiet board", () => {
  test("produces no post rather than a small number", () => {
    // Dropping the bar to keep the number up is how a daily statistic stops meaning
    // anything. Saying nothing lets the caller report a quiet day.
    expect(tweetStat({ rows: board(STAT_MIN_TEAMS - 1), site: SITE }).text).toBe("");
  });

  test("an empty board produces no post", () => {
    expect(tweetStat({ rows: [], site: SITE }).text).toBe("");
  });

  test("the bar is never loosened to reach the threshold", () => {
    // Twenty teams on 3+ and four on 4+ is a quiet day for this post, and must read as one.
    const rows = [...board(20, "eng-ch", 3, 18), ...board(4)];
    expect(tweetStat({ rows, site: SITE }).text).toBe("");
  });
});


describe("what X will accept", () => {
  test("an ordinary board fits once the link is counted", () => {
    const { text } = tweetStat({ rows: board(23), days: 3, site: SITE });
    expect(xWeight(text)).toBeLessThanOrEqual(X_MAX_WEIGHT);
  });

  test("a board of many countries still fits", () => {
    const many = ["eng-pl", "ned-ed", "bra-sb", "usa-ml", "ita-sa", "ger-bl", "fra-l1",
                  "esp-ll", "por-pl", "jpn-j1", "arg-lp", "sco-pl"]
      .flatMap((lid) => board(3, lid, 5, 14));
    const { text, stats } = tweetStat({ rows: many, days: 3, site: SITE });
    expect(stats.countries).toBe(12);
    expect(xWeight(text)).toBeLessThanOrEqual(X_MAX_WEIGHT);
    // Sentences are dropped from the END, so the count survives whatever else does not.
    expect(text.startsWith(`${stats.teams} teams`)).toBe(true);
  });

  test("the link survives whatever is trimmed", () => {
    // A post that loses its link is a statistic with nowhere to go.
    const many = board(40, "bra-sb", 6, 22);
    expect(tweetStat({ rows: many, days: 3, site: SITE }).text)
      .toContain("/streaks");
  });
});
