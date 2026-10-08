/**
 * The pure arithmetic behind the story cards.
 *
 * Most of storyImage.js is drawing, which is checked by rendering a card and reading it
 * back (tools/render_story.mjs). What CAN be pinned here is the maths the drawing rests
 * on, and a number that is wrong on a published graphic is wrong everywhere it was shared.
 */
import { recentRate } from "./storyImage.js";


describe("the wide card's recency pills", () => {
  // The headline fraction says how often across the whole window; it cannot say whether
  // the run is still going. A 9/10 built on a streak that ended four games ago is a
  // different proposition from one that is live.
  const vals = [1, 1, 1, 9, 9, 9, 9, 9, 9, 9];   // oldest first: cold start, hot finish

  test("it counts the LAST n, not the first", () => {
    expect(recentRate(vals, 5, 5)).toEqual({ n: 5, hits: 5, pct: 100 });
    expect(recentRate(vals, 5, 10)).toEqual({ n: 10, hits: 7, pct: 70 });
  });

  test("a window the pool cannot fill is null, not a short answer", () => {
    // "L20" over twelve games would be a label making a claim the data cannot.
    expect(recentRate(vals, 5, 20)).toBeNull();
    expect(recentRate([], 5, 5)).toBeNull();
  });

  test("the line is the threshold, inclusive", () => {
    expect(recentRate([4, 4, 4, 4, 4], 4, 5).hits).toBe(5);
    expect(recentRate([3, 3, 3, 3, 3], 4, 5).hits).toBe(0);
  });

  test("nonsense in, null out", () => {
    expect(recentRate(null, 4, 5)).toBeNull();
    expect(recentRate([1, 2, 3], 4, 0)).toBeNull();
  });
});
