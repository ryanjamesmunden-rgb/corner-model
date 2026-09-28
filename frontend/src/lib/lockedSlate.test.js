// The locked list, sent before kick-off.
//
// WHAT THIS IS FOR. The Results page says "18 of 18". That number only means anything if the
// list was written down first, and until now nothing ever SENT the list — so there was no
// message anywhere proving it.
//
// WHAT THESE GUARD:
//
//   - IT MATCHES WHAT WILL BE GRADED. The post is built from the snapshot's own entries and
//     only from the ones marked `qualified`. A post listing the near-misses too would claim
//     credit for rows nobody was shown; a post that recomputed the bar would drift from the
//     record it is supposed to prove.
//   - IT CARRIES THE LINE. This goes to the paid channel, and a locked list with the lines
//     removed is the record without the product.
//   - THE ROUTE IS NAMED. A twelve-game run standing alone and a six-game run leaning on a
//     leaky opponent are different claims, and the record used to show them identically.
//   - IT FITS TELEGRAM, and says so when it had to drop rows — a list that silently ends
//     early cannot be checked against the Results page.
import {
  STRONG_RUN, TELEGRAM_MAX, callOf, cardLabel, evidence, frozenLabel, lockedEntries,
  lockedRow, lockedSlate, versus,
} from "./lockedSlate.js";

const SITE = "https://thecornermodel.com";
const KICK = "2026-10-03T14:00:00Z";

const entry = (over = {}) => ({
  team_id: "eng-l2-1", name: "Plymouth", league_id: "eng-l2",
  line: 4, direction: "over", subject: "team",
  streak_len: 12, games: 20, hits: 12, window: 12, settled: 12, voids: 0,
  fixture_id: "eng-l2-999", kickoff: KICK, opponent: "Wycombe", is_home: true,
  prob: 78.4, qualified: true, card: "weekend", route: "long_run",
  support: { run: 12, prob: 78.4, weak_opponent: true, opp_conceded: 6.4 },
  ...over,
});

const slate = (over = {}) => lockedSlate({
  tag: "2026-09-28", card: "weekend", site: SITE, entries: [entry()], ...over });


describe("only what will actually be graded", () => {
  test("an unqualified entry is not named", () => {
    // The freeze keeps 25 rows so the record can ask what the near-misses did. The CARD is
    // the ones that cleared a route inside the window.
    const rows = [entry(), entry({ name: "Barrow", qualified: false })];
    expect(lockedEntries(rows).map((e) => e.name)).toEqual(["Plymouth"]);
  });

  test("`qualified` is read, never recomputed", () => {
    // It was decided against data that has since moved. A bar re-applied here is a bar
    // applied to a different board — the survivorship problem the snapshot exists to stop.
    const weak = entry({ qualified: true, streak_len: 2, route: null, prob: 10 });
    expect(lockedEntries([weak])).toHaveLength(1);
  });

  test("an entry with nothing to grade against is dropped", () => {
    expect(lockedEntries([entry({ fixture_id: null })])).toEqual([]);
    expect(lockedEntries([entry({ name: "" })])).toEqual([]);
  });

  test("an empty freeze produces no post rather than a cheerful one", () => {
    expect(slate({ entries: [] })).toBe("");
    expect(slate({ entries: [entry({ qualified: false })] })).toBe("");
  });
});


describe("what each row says", () => {
  test("the call is the line that was made", () => {
    expect(callOf(entry())).toBe("4+ corners");
    expect(callOf(entry({ direction: "under", line: 9 }))).toBe("under 9 corners");
    expect(callOf(entry({ subject: "match", line: 10 }))).toBe("10+ in the match");
  });

  test("the fixture reads from this team's side of it", () => {
    expect(versus(entry())).toBe("v Wycombe");
    expect(versus(entry({ is_home: false }))).toBe("at Wycombe");
    expect(versus(entry({ opponent: "" }))).toBe("");
  });

  test("a long run is published on the run alone", () => {
    const out = evidence(entry({ streak_len: 12, route: "long_run" }));
    expect(out).toContain("12 in a row");
    expect(out).toContain("the run alone");
    expect(out).not.toContain("opponent ships");
  });

  test("a shorter run names the opponent that backs it", () => {
    const out = evidence(entry({ streak_len: 6, route: "corroborated" }));
    expect(out).toContain("6 in a row");
    expect(out).toContain("opponent ships 6.4/g");
    expect(out).not.toContain("the run alone");
  });

  test("a corroborated row with no opponent average still says why", () => {
    const out = evidence(entry({ streak_len: 6, route: "corroborated",
                                support: { run: 6, prob: 64 } }));
    expect(out).toContain("leaky opponent");
  });

  test("the sample is printed beside the run", () => {
    // Five of five from a side with five games on file is its whole record, not form.
    expect(evidence(entry({ games: 20 }))).toContain("20 games on file");
  });

  test("the kick-off is UK time", () => {
    // 14:00Z in October is 3pm in London. Every other post here is UK time and this is
    // read alongside them.
    expect(lockedRow(entry())).toContain("Sat 3:00pm");
  });
});


describe("what the post claims", () => {
  test("it states the day it was frozen", () => {
    // The claim being made. A reader can compare it with the kick-offs.
    expect(frozenLabel("2026-09-28")).toBe("Mon 28 Sep");
    expect(slate()).toContain("Frozen Mon 28 Sep, before a ball was kicked");
  });

  test("the frozen date names the day the tag names, in any offset", () => {
    // Built at noon UTC on purpose: no European offset can move the calendar day from
    // there, so the label cannot end up a day either side of the tag.
    expect(frozenLabel("2026-01-01")).toBe("Thu 1 Jan");
    expect(frozenLabel("2026-06-30")).toBe("Tue 30 Jun");
    // Three letters on every ICU build. Some spell September "Sept", which would make the
    // same tag produce two different posts depending on which machine composed it.
    expect(frozenLabel("2026-09-28")).toBe("Mon 28 Sep");
    expect(frozenLabel("2026-09-28").split(" ")[2]).toHaveLength(3);
    expect(frozenLabel("")).toBe("");
    expect(frozenLabel("nonsense")).toBe("");
  });

  test("it names the card", () => {
    expect(slate()).toContain("Weekend card");
    expect(slate({ card: "midweek" })).toContain("Midweek card");
    expect(cardLabel("nonsense")).toBe("");
  });

  test("the card is recovered from the rows when the caller has none", () => {
    // FOUND ON THE FIRST REAL RUN. The snapshot DOCUMENT carries no `card` — only its
    // entries do — so a caller reading the freeze response has nothing to pass, and the
    // heading came out as a bare "🔒 LOCKED IN".
    const out = lockedSlate({ tag: "2026-09-28", site: SITE,
                              entries: [entry({ card: "midweek" })] });
    expect(out).toContain("Midweek card");
  });

  test("an explicit card beats the rows", () => {
    // The workflow passes one, and it knows which card it is publishing.
    const out = lockedSlate({ tag: "2026-09-28", card: "weekend", site: SITE,
                              entries: [entry({ card: "midweek" })] });
    expect(out).toContain("Weekend card");
  });

  test("a row with no card at all still produces a heading", () => {
    const out = lockedSlate({ tag: "2026-09-28", site: SITE,
                              entries: [entry({ card: undefined })] });
    expect(out.startsWith("🔒 LOCKED IN")).toBe(true);
  });

  test("it counts the calls it is making", () => {
    const three = slate({ entries: [entry(), entry({ name: "B" }), entry({ name: "C" })] });
    expect(three).toContain("3 calls");
    expect(slate()).toContain("1 call,");
  });

  test("it carries the line, because this is the paid channel", () => {
    // Everything public withholds these now. Being told the line before the game rather
    // than after is what a member is paying for.
    expect(slate()).toContain("4+ corners");
    expect(slate()).toContain("model 78%");
  });

  test("it says nothing can be added afterwards", () => {
    expect(slate()).toContain("Nothing is added or removed after this message");
  });

  test("it sends the reader to the record", () => {
    expect(slate()).toContain("thecornermodel.com/results");
  });

  test("it does not promise a result", () => {
    const text = slate().toLowerCase();
    for (const word of ["will land", "guaranteed", "banker", "can't lose", "sure thing"]) {
      expect(text).not.toContain(word);
    }
    // "graded whatever happens to them" is the opposite claim, and it is the honest one.
    expect(slate()).toContain("whatever happens");
  });
});


describe("what Telegram will take", () => {
  test("a full card fits", () => {
    const many = Array.from({ length: 8 }, (_, i) => entry({ name: `Team ${i}` }));
    const out = slate({ entries: many });
    expect(out.length).toBeLessThanOrEqual(TELEGRAM_MAX);
    expect(out).not.toContain("more on the site");
  });

  test("an oversized freeze is trimmed and SAYS it was trimmed", () => {
    // A list that silently ends early cannot be checked against the Results page, which is
    // the only thing this post is for.
    const many = Array.from({ length: 25 }, (_, i) =>
      entry({ name: `A very long club name indeed number ${i}` }));
    const out = lockedSlate({ tag: "2026-09-28", card: "weekend", site: SITE,
                              entries: many, max: 900 });
    expect(out.length).toBeLessThanOrEqual(900);
    expect(out).toMatch(/\+ \d+ more on the site, all of them graded\./);
  });

  test("rows are dropped from the END so the order matches the record", () => {
    const many = [entry({ name: "First" }), entry({ name: "Second" }),
                  entry({ name: "Third" })];
    const out = lockedSlate({ tag: "2026-09-28", card: "weekend", entries: many, max: 420 });
    expect(out).toContain("First");
    expect(out).not.toContain("Third");
  });

  test("a single row too long for the limit produces nothing rather than a fragment", () => {
    expect(lockedSlate({ tag: "2026-09-28", entries: [entry()], max: 50 })).toBe("");
  });

  test("STRONG_RUN matches the backend's own bar", () => {
    // angle_of_day.STRONG_RUN. If they drift, this post explains a route the record did
    // not take.
    expect(STRONG_RUN).toBe(10);
  });
});
