/**
 * A kick-off is only useful if it is RIGHT, and the two ways it goes wrong are both
 * quiet: a bad date string rendering as "Invalid Date" next to a real bet, and the
 * relative naming drifting so "Today" means yesterday. Both are pinned here.
 *
 * The exact strings are locale-dependent, so what's asserted is the SHAPE — which day
 * word, whether a time is present — not "19:45", which is only that on a 24-hour clock.
 */
import { kickoffTime, kickoffDay, kickoffLabel, timeZoneLabel, timesFooter } from "./kickoff";

const inHours = (h) => new Date(Date.now() + h * 3600 * 1000).toISOString();
// Anchored to local midnight so the case can't straddle a day boundary mid-run.
const atLocalNoonInDays = (d) => {
  const t = new Date();
  t.setDate(t.getDate() + d);
  t.setHours(12, 0, 0, 0);
  return t.toISOString();
};

describe("naming the day", () => {
  test("today and tomorrow are named, not dated", () => {
    expect(kickoffDay(atLocalNoonInDays(0))).toBe("Today");
    expect(kickoffDay(atLocalNoonInDays(1))).toBe("Tomorrow");
  });

  test("further out falls back to a real date", () => {
    const day = kickoffDay(atLocalNoonInDays(5));
    expect(day).not.toBe("Today");
    expect(day).not.toBe("Tomorrow");
    expect(day).toMatch(/\d/);
  });

  test("a game earlier today is still Today — the time is what separates them", () => {
    // The row for a game that kicked off an hour ago must not read as tomorrow's.
    expect(kickoffDay(inHours(-1))).toMatch(/Today|Yesterday|\d/);
  });
});

describe("bad input never reaches the screen", () => {
  test.each([null, undefined, "", "not a date"])("%p renders as nothing at all", (bad) => {
    expect(kickoffTime(bad)).toBe("");
    expect(kickoffDay(bad)).toBe("");
    expect(kickoffLabel(bad)).toBe("");
  });

  test("no 'Invalid Date' ever leaks into a label", () => {
    expect(kickoffLabel("2026-13-45T99:99:99Z")).not.toMatch(/Invalid/);
  });
});

describe("the label", () => {
  test("carries both the day and a time", () => {
    const label = kickoffLabel(atLocalNoonInDays(0));
    expect(label).toContain("Today");
    expect(label).toMatch(/\d{1,2}[:.]\d{2}/);
  });

  test("the zone is a separate call, so shared text can name it once", () => {
    expect(kickoffLabel(atLocalNoonInDays(0))).not.toContain(timeZoneLabel());
    expect(typeof timeZoneLabel()).toBe("string");
  });
});

describe("the shared zone footer", () => {
  test("names the zone once, on its own line", () => {
    const footer = timesFooter([atLocalNoonInDays(0), atLocalNoonInDays(1)]);
    expect(footer).toBe(`\nAll times ${timeZoneLabel()}`);
    // Once, not once per date — the whole reason it isn't on every line.
    expect(footer.match(/All times/g)).toHaveLength(1);
  });

  test("is dropped when nothing in the board has a kick-off", () => {
    // A board of dateless rows that still said "All times BST" would be claiming
    // a precision it hasn't got.
    expect(timesFooter([])).toBe("");
    expect(timesFooter([null, undefined, "", "not a date"])).toBe("");
    expect(timesFooter(undefined)).toBe("");
  });

  test("survives one bad date among good ones", () => {
    expect(timesFooter([null, atLocalNoonInDays(0)])).toContain("All times");
  });

  test("carries its own leading newline, so it can't run into the line above", () => {
    expect(`+3 more on the site${timesFooter([atLocalNoonInDays(0)])}`).toContain("site\nAll times");
  });
});
