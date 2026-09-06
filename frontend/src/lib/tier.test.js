/**
 * The risk in this file is not a wrong label, it is an implied claim. A tier badge sits
 * on a board that ranks teams across countries, so what is pinned is that it degrades to
 * NOTHING when the level is unknown — a "T?" or a dash would read as a real category —
 * and that the filters agree with the labels they are named after.
 */
import { tierLabel, tierName, tierTitle, TIER_FILTERS, tierFilter } from "./tier";

describe("labels", () => {
  test("name the level, from the top flight down", () => {
    expect(tierLabel(1)).toBe("T1");
    expect(tierName(1)).toBe("Top flight");
    expect(tierName(5)).toBe("5th tier");
  });

  test("say nothing at all when the tier is unknown", () => {
    for (const bad of [undefined, null, 0, 9, "x", {}]) {
      expect(tierLabel(bad)).toBe("");
      expect(tierTitle(bad)).toBe("");
    }
  });

  test("a numeric string is the same tier, so badge and filter agree on it", () => {
    expect(tierLabel("2")).toBe("T2");
    expect(tierFilter("1-2")({ tier: "2" })).toBe(true);
  });

  test("the tooltip refuses the cross-border reading outright", () => {
    expect(tierTitle(2, "England")).toContain("England");
    expect(tierTitle(2, "England")).toContain("not a strength rating");
  });
});

describe("filters", () => {
  const rows = [{ tier: 1 }, { tier: 2 }, { tier: 3 }, { tier: 5 }, {}];

  test("'any' keeps everything, including rows with no tier", () => {
    expect(rows.filter(tierFilter("any"))).toHaveLength(5);
  });

  test("narrow by level as named", () => {
    expect(rows.filter(tierFilter("1")).map((r) => r.tier)).toEqual([1]);
    expect(rows.filter(tierFilter("1-2")).map((r) => r.tier)).toEqual([1, 2]);
    expect(rows.filter(tierFilter("3+")).map((r) => r.tier)).toEqual([3, 5]);
  });

  test("a row with no tier is excluded by every narrowing filter, not guessed into one", () => {
    for (const key of ["1", "1-2", "3+"]) {
      expect(TIER_FILTERS.find((t) => t.v === key).test({})).toBe(false);
    }
  });

  test("an unknown key falls back to keeping everything", () => {
    expect(tierFilter("nonsense")({ tier: 4 })).toBe(true);
  });
});
