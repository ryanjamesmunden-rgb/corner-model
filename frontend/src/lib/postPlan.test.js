/**
 * The posting week.
 *
 * THE POINT OF THIS FILE IS THAT THE SHAPE DOES NOT MOVE. A poster whose pattern drifts is
 * one nobody learns to expect, and the value of posting daily is that people know when to
 * look. So the whole week is asserted, day by day, rather than discovered on a Thursday —
 * a rotation that skips a day, doubles a board or looks three days ahead on a Saturday
 * morning still produces a post every day, and the post still looks fine.
 */
import { boardForDay, freezesSnapshot, gradesWeekend, extraForDay, isQuietDay,
         MONDAY, THURSDAY, FRIDAY } from "./postPlan";

const WEEK = [1, 2, 3, 4, 5, 6, 7];

test("the week is exactly this, and this is the test that keeps it there", () => {
  expect(WEEK.map((d) => boardForDay(d).board)).toEqual([
    "results",   // Mon — how last week's frozen streaks landed
    "game",      // Tue — the midweek fixture with the strongest angle
    "streaks",   // Wed — what is trending, plus the weekend card to the channel
    null,        // Thu — nothing, deliberately
    "game",      // Fri — the best game of the weekend
    "game",      // Sat — what is on today
    "game",      // Sun — what is on today
  ]);
});

test("Monday reports the weekend, because no other day can", () => {
  expect(boardForDay(MONDAY).board).toBe("results");
  expect(gradesWeekend(MONDAY)).toBe(true);
  expect(gradesWeekend(FRIDAY)).toBe(false);
});

test("Thursday says nothing, and says so in the plan rather than by accident", () => {
  // Every scheduling instinct says fill the slot, and filling it is how an account starts
  // posting things nobody needed to read. A silent day has to be a decision the code
  // states, not something that happens because a board came back empty.
  expect(WEEK.filter(isQuietDay)).toEqual([THURSDAY]);
  expect(boardForDay(THURSDAY).board).toBeNull();
  expect(boardForDay(THURSDAY).days).toBe(0);
});

test("only Monday falls back to another board", () => {
  // Monday's board can be empty through nobody's fault. Any other day being empty means
  // there is nothing worth posting, and reaching for a different board to fill the slot is
  // how a daily poster starts posting filler.
  expect(boardForDay(MONDAY).fallback).toBe("streaks");
  for (const d of [2, 3, 4, 5, 6, 7]) expect(boardForDay(d).fallback).toBeNull();
});

test("each day looks as far ahead as its own question needs", () => {
  expect(boardForDay(2).days).toBe(2);   // midweek card, not the weekend
  expect(boardForDay(3).days).toBe(3);
  expect(boardForDay(5).days).toBe(3);   // the weekend, from Friday
  expect(boardForDay(6).days).toBe(1);   // "what is on today"
  expect(boardForDay(7).days).toBe(1);
});

test("the channel gets the weekend before anything public names those games", () => {
  // This is the product. Wednesday is roughly when the weekend's prices appear; the public
  // post about the same games is Friday. Two clear days of edge, and a schedule that ever
  // posts publicly first hands that back.
  const card = WEEK.filter((d) => extraForDay(d));
  expect(card).toEqual([3]);
  const publicWeekendPost = FRIDAY;
  expect(card[0]).toBeLessThan(publicWeekendPost);
});

test("the snapshot is the last moment before kick-off, not the day the card goes out", () => {
  // A snapshot records what was being claimed while it was still a prediction, so it wants
  // to be as late as possible and still before the first whistle. Freezing on Wednesday
  // would pin a board that then has two more days to change.
  expect(WEEK.filter(freezesSnapshot)).toEqual([FRIDAY]);
  expect(extraForDay(FRIDAY)).toBeNull();
  expect(freezesSnapshot(3)).toBe(false);
});

test("a weekday it does not recognise still posts something rather than nothing", () => {
  // `date +%u` should never hand this a 0 or an 8, but a poster that throws on an
  // unexpected day is a poster that goes silent for a reason nobody looks for. An
  // unrecognised day must not land on the quiet-day path either.
  for (const d of [0, 99, undefined, null, "x"]) {
    expect(boardForDay(d).board).toBe("streaks");
    expect(isQuietDay(d)).toBe(false);
  }
});
