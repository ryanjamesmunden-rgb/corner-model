/**
 * What a week's highlight reel may claim.
 *
 * A week is a CHOSEN period — "another 10/10 week" is the clip somebody posts in a good
 * week and not in a bad one — so most of what is pinned here is that the clip cannot
 * quietly become a better week than the one that happened: losers stay, voids stay, the
 * trim takes the oldest rather than the worst, and the overall record rides along.
 */
import { reelFrom, reelAt, reelPost, reelRow, valueText, MAX_REEL_ROWS } from "./resultsReel.js";

const DAY = 86400000;
const NOW = Date.parse("2026-10-04T12:00:00Z");

const row = (over = {}) => ({
  name: "Celtic", line_label: "6+", result: "win", value: 9,
  kickoff: new Date(NOW - DAY).toISOString(), price: 1.8, stake: 1, ...over,
});

const results = (rows, over = {}) => ({
  posted: { claimed: { rows, landed: 31, settled: 47, voided: 0, pending: 0, ...over } },
});

describe("a row", () => {
  test("says what actually happened, which is the point of a result card", () => {
    expect(valueText({ value: 9 })).toBe("9 corners");
    expect(valueText({ value: 1 })).toBe("1 corner");
    expect(valueText({})).toBe("");
  });

  test("marks a void as its own outcome", () => {
    const r = reelRow(row({ result: "void" }));
    expect(r.voided).toBe(true);
    expect(r.won).toBe(false);
    expect(r.lost).toBe(false);
  });
});

describe("the reel", () => {
  test("nothing settled means no reel", () => {
    expect(reelFrom(results([]))).toBeNull();
    expect(reelFrom(results([row({ result: "pending" }), row({ result: "pending" })])))
      .toBeNull();
  });

  test("one result is a card, not a clip", () => {
    expect(reelFrom(results([row()]), { now: NOW })).toBeNull();
  });

  test("it counts what went past", () => {
    const reel = reelFrom(results([row(), row({ result: "loss", value: 3 }), row()]),
                          { now: NOW });
    expect(reel.big).toBe("2 from 3");
    expect(reel.clean).toBe(false);
  });

  test("losers stay in the clip", () => {
    // THE WHOLE POINT. Ten stills is ten chances to drop the one that lost; one reel off
    // one list is not.
    const reel = reelFrom(results([row(), row({ result: "loss" }), row()]), { now: NOW });
    expect(reel.rows.filter((r) => r.lost)).toHaveLength(1);
  });

  test("a void is kept and counted apart", () => {
    const reel = reelFrom(results([row(), row(), row({ result: "void" })]), { now: NOW });
    expect(reel.voided).toBe(1);
    // It happened to the money, so it is on screen — but it is not a win or a loss.
    expect(reel.big).toBe("2 from 2");
    expect(reel.n).toBe(3);
  });

  test("the rows replay in kick-off order, not best-first", () => {
    const reel = reelFrom(results([
      row({ name: "Late", kickoff: new Date(NOW - DAY).toISOString() }),
      row({ name: "Early", kickoff: new Date(NOW - 5 * DAY).toISOString() }),
    ]), { now: NOW });
    expect(reel.rows.map((r) => r.name)).toEqual(["Early", "Late"]);
  });

  test("only the window counts", () => {
    const reel = reelFrom(results([
      row(), row(), row({ name: "LastMonth", kickoff: new Date(NOW - 30 * DAY).toISOString() }),
    ]), { now: NOW, days: 7 });
    expect(reel.n).toBe(2);
    expect(reel.rows.some((r) => r.name === "LastMonth")).toBe(false);
  });

  test("a trim drops the OLDEST and says so, never the losers", () => {
    const rows = Array.from({ length: MAX_REEL_ROWS + 3 }, (_, i) => row({
      name: `T${i}`, result: i === 0 ? "win" : i === 1 ? "loss" : "win",
      kickoff: new Date(NOW - (MAX_REEL_ROWS + 3 - i) * 3600000).toISOString(),
    }));
    const reel = reelFrom(results(rows), { now: NOW });
    expect(reel.n).toBe(MAX_REEL_ROWS);
    expect(reel.more).toBe(3);
    // The headline still counts every settled row in the window, trimmed or not.
    expect(reel.settled).toBe(MAX_REEL_ROWS + 3);
  });

  test("the overall record rides along, because a week is a chosen period", () => {
    const reel = reelFrom(results([row(), row()]), { now: NOW });
    expect(reel.context).toBe("31 of 47 overall");
  });

  test("units only when every settled row carries a price", () => {
    const priced = reelFrom(results([row(), row({ result: "loss" })]), { now: NOW });
    expect(priced.units).toBe(-0.2);          // 0.8 - 1
    const mixed = reelFrom(results([row(), row({ price: null })]), { now: NOW });
    expect(mixed.units).toBeNull();
    expect(mixed.unitsNote).toContain("without a price");
  });
});

describe("the timeline", () => {
  const reel = { n: 4 };

  test("it opens with a row on screen rather than on an empty frame", () => {
    expect(reelAt(reel, 0).shown).toBe(1);
  });

  test("rows arrive one at a time", () => {
    expect(reelAt(reel, 0.3).shown).toBeGreaterThan(1);
    expect(reelAt(reel, 0.3).shown).toBeLessThan(4);
    expect(reelAt(reel, 0.3).tally).toBe(0);
  });

  test("without an end card the tally owns the tail", () => {
    // A clip with nothing to advertise ends on the record, which is a complete post.
    expect(reelAt(reel, 1).tally).toBe(1);
    expect(reelAt(reel, 1).next).toBe(0);
  });

  test("with one, the end card takes its beat from the rows and the tally stays up", () => {
    // A number that fades out as the advert arrives reads as a number being taken away.
    const selling = { n: 4, join: "thecornermodel.com/join" };
    expect(reelAt(selling, 1).next).toBe(1);
    expect(reelAt(selling, 1).tally).toBe(1);
    expect(reelAt(selling, 0.5).next).toBe(0);
  });

  test("the tally gets its own beat at the end", () => {
    // A number that arrives on the final frame is a number nobody reads.
    expect(reelAt(reel, 0.8).shown).toBe(4);
    expect(reelAt(reel, 0.8).tally).toBeGreaterThan(0);
    expect(reelAt(reel, 1).tally).toBe(1);
  });

  test("no reel, no timeline", () => {
    expect(reelAt(null, 0.5)).toEqual({ shown: 0, tally: 0, next: 0, growth: 1 });
  });

  test("the newest row's bar grows, and the ones behind it have stopped", () => {
    // The whole point of the bar is watching it pass the line: one that arrived full would
    // show the result without ever showing the margin.
    expect(reelAt(reel, 0).growth).toBeLessThan(1);
    expect(reelAt(reel, 0.74).growth).toBe(1);
    // And it settles before the next row lands, rather than being interrupted halfway.
    expect(reelAt(reel, 0.16).growth).toBe(1);
  });
});

describe("the caption", () => {
  test("carries every row with what it landed on", () => {
    const reel = reelFrom(results([row(), row({ name: "Viking", result: "loss", value: 3 })]),
                          { now: NOW });
    const out = reelPost({ reel, site: "thecornermodel.com" });
    expect(out).toContain("1 from 2");
    expect(out).toContain("Celtic 6+ — 9 corners ✅");
    expect(out).toContain("Viking 6+ — 3 corners ❌");
    expect(out).toContain("31 of 47 overall");
    expect(out).toContain("Graded from a snapshot frozen before kick-off");
    expect(out).toContain("thecornermodel.com");
  });

  test("no reel, no caption", () => {
    expect(reelPost({ reel: null })).toBe("");
  });
});
