/**
 * The posting week.
 *
 * This is the part of a daily poster that is easiest to get quietly wrong and hardest to
 * notice: a rotation that skips a day, doubles a board, or looks three days ahead on a
 * Saturday morning will still produce a post every day, and the post will look fine. So
 * the week is asserted here rather than discovered on a Thursday.
 */
import { boardForDay, freezesSnapshot, gradesWeekend, extraForDay } from "./postPlan";

const WEEK = [1, 2, 3, 4, 5, 6, 7];

test("every day of the week has something to post", () => {
  for (const d of WEEK) {
    const { board, days } = boardForDay(d);
    expect(["results", "streaks", "game"]).toContain(board);
    expect(days).toBeGreaterThan(0);
  }
});

test("Monday reports the weekend, because no other day can", () => {
  expect(boardForDay(1).board).toBe("results");
  expect(gradesWeekend(1)).toBe(true);
  expect(gradesWeekend(5)).toBe(false);
});

test("only Monday falls back to another board", () => {
  // An empty board on any other day means there is nothing worth posting. Reaching for a
  // different board to fill the slot is how a daily poster starts posting filler.
  expect(boardForDay(1).fallback).toBe("streaks");
  for (const d of [2, 3, 4, 5, 6, 7]) expect(boardForDay(d).fallback).toBeNull();
});

test("the weekend carries games, the midweek carries streaks", () => {
  // A single game across three lines, not a board of them: see gameShare. The list format
  // fits six rows in a post by cramping each one, which reads as a price list rather than
  // a reason to look.
  expect(boardForDay(5).board).toBe("game");
  expect(boardForDay(6).board).toBe("game");
  expect(boardForDay(7).board).toBe("game");
  expect(boardForDay(2).board).toBe("streaks");
  expect(boardForDay(4).board).toBe("streaks");
});

test("Saturday and Sunday look one day ahead, not three", () => {
  // "What is on today" is the Saturday-morning question. A three-day window answers it
  // with a list mostly made of games that have not been priced yet.
  expect(boardForDay(6).days).toBe(1);
  expect(boardForDay(7).days).toBe(1);
  expect(boardForDay(3).days).toBe(3);
});

test("Friday, and only Friday, freezes the weekend", () => {
  // Two snapshots in a week would give Monday two things to grade and no way to say which
  // one it graded; none would leave the weekend ungradeable for good.
  expect(WEEK.filter(freezesSnapshot)).toEqual([5]);
});

test("a weekday it does not recognise still posts something rather than nothing", () => {
  // `date +%u` should never hand this a 0 or an 8, but a poster that throws on an
  // unexpected day is a poster that goes silent for a reason nobody looks for.
  expect(boardForDay(0).board).toBe("streaks");
  expect(boardForDay(99).board).toBe("streaks");
  expect(boardForDay(undefined).board).toBe("streaks");
});

// THE WEEKEND CARD IS THE PRODUCT. The public post goes out on the day of the game, by
// which time the market has found it. What a member is paying for is seeing Sunday's card
// on Friday, so the day this fires is not a detail.
test("only Friday sends the weekend card early", () => {
  expect(extraForDay(5)).toBe("weekend");
  for (const d of [1, 2, 3, 4, 6, 7]) expect(extraForDay(d)).toBeNull();
});

test("the card and the snapshot ride the same day", () => {
  // Both are Friday jobs about the same weekend. If they ever drift apart, one of them is
  // describing a different set of games from the one that got frozen.
  for (const d of [1, 2, 3, 4, 5, 6, 7]) {
    expect(Boolean(extraForDay(d))).toBe(freezesSnapshot(d));
  }
});
