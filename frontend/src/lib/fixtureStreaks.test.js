// The runs shown on a fixture page.
//
// WHY IT EXISTS AT ALL: /streaks advertises a run, and clicking the fixture used to lose
// it. The payload was there the whole time and went to a share button, so the one thing
// that made the reader click was the one thing the destination did not say.
//
// WHAT THESE GUARD:
//   - The fire meaning something different here from everywhere else. Three marks wearing
//     one emoji is worse than no emoji.
//   - "9 in a row" and "9 of 9" being conflated. They are different numbers and diverge
//     exactly when it matters — a void mid-window, or a run shorter than its window.
//   - A direction relabelled. An under printed as "5+" costs money in the opposite
//     direction to the reader's intent.
import {
  FIRE_RUN, fixtureStreaks, markFor, streakDetail, streakHeadline, streakRow, RECENT_SHOWN,
} from "./fixtureStreaks.js";

const leg = (corners, result = "won") => ({ corners, result, opponent: "Someone", home: true });

const streak = (name, { line = 5, run = 6, hits = 6, settled = 6, voids = 0,
                        avg = 7.2, min = 5, label, legs } = {}) => ({
  name, team_id: `eng-pl-${name}`, league_id: "eng-pl",
  streak: { line, line_label: label ?? `${line}+ corners`, length: run, hits, settled,
            voids, avg, min_won: min,
            recent: legs ?? Array.from({ length: 8 }, (_, i) => leg(7 + (i % 3))) },
});


describe("the mark", () => {
  test("it is the threshold the rest of the site uses", () => {
    // Not a new number. FIRE_RUN drives the share text and the angle menu too.
    expect(FIRE_RUN).toBe(8);
  });

  test("fire at the threshold, flag below it", () => {
    expect(markFor(FIRE_RUN)).toBe("🔥");
    expect(markFor(FIRE_RUN + 4)).toBe("🔥");
    expect(markFor(FIRE_RUN - 1)).toBe("🚩");
  });

  test("junk is a flag, not a crash or a fire", () => {
    expect(markFor(undefined)).toBe("🚩");
    expect(markFor(null)).toBe("🚩");
  });
});


describe("the run and the record are different numbers", () => {
  test("both are carried", () => {
    const r = streakRow(streak("Arsenal", { run: 9, hits: 9, settled: 9 }));
    expect(r.run).toBe(9);
    expect(r.hits).toBe(9);
    expect(r.settled).toBe(9);
  });

  test("a run shorter than its window does not borrow the window's record", () => {
    // 4 in a row inside a window that went 8 of 10. Printing "4 of 4" would overstate the
    // run's own evidence; printing "8 of 10" would overstate the run. Both are shown.
    const r = streakRow(streak("Chelsea", { run: 4, hits: 8, settled: 10 }));
    expect(r.run).toBe(4);
    expect(streakDetail(r)).toContain("8 of 10 settled");
  });

  test("a void is surfaced rather than folded away", () => {
    const r = streakRow(streak("Spurs", { voids: 1 }));
    expect(streakDetail(r)).toContain("1 void");
  });

  test("missing numbers are omitted, not printed as blanks", () => {
    const bare = { name: "X", streak: { line_label: "4+ corners", length: 5 } };
    const d = streakDetail(streakRow(bare));
    expect(d).not.toContain("undefined");
    expect(d).not.toContain("null");
  });
});


describe("what reaches the panel", () => {
  test("the label comes straight from the API", () => {
    // An under relabelled as an over loses in the opposite direction to the intent.
    const under = streak("Sunderland", { label: "under 9" });
    expect(streakRow(under).label).toBe("under 9");
  });

  test("a row with no label is dropped rather than guessed at", () => {
    const noLabel = { name: "X", team_id: "t", streak: { length: 9 } };
    expect(fixtureStreaks([noLabel])).toEqual([]);
  });

  test("a run of one is not a run", () => {
    expect(fixtureStreaks([streak("X", { run: 1 })])).toEqual([]);
  });

  test("longest first", () => {
    const rows = fixtureStreaks([streak("A", { run: 4 }), streak("B", { run: 11 }),
                                 streak("C", { run: 7 })]);
    expect(rows.map((r) => r.team)).toEqual(["B", "C", "A"]);
  });

  test("recent legs are capped and newest first", () => {
    const legs = [leg(9), leg(8), leg(7), leg(6), leg(5), leg(4), leg(3), leg(2)];
    const r = streakRow(streak("A", { legs }));
    expect(r.recent).toHaveLength(RECENT_SHOWN);
    expect(r.recent[0].corners).toBe(9);
  });

  test("an empty payload is an empty panel, not a crash", () => {
    expect(fixtureStreaks([])).toEqual([]);
    expect(fixtureStreaks()).toEqual([]);
  });
});


describe("the header", () => {
  test("it counts the runs and says how many are hot", () => {
    const rows = fixtureStreaks([streak("A", { run: 11 }), streak("B", { run: 4 })]);
    expect(streakHeadline(rows)).toBe("2 streaks running into this game · 1 on 8+");
  });

  test("no hot run means no claim about one", () => {
    const rows = fixtureStreaks([streak("A", { run: 4 })]);
    expect(streakHeadline(rows)).toBe("1 streak running into this game");
  });

  test("nothing running says nothing", () => {
    expect(streakHeadline([])).toBe("");
  });
});
