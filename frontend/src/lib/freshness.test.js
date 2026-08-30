/**
 * The header badge spent five days showing "LIVE · 5d ago" in green, with a pulsing dot,
 * while the provider account was suspended and nothing had synced. On a betting site that
 * is the worst possible failure mode: the numbers were wrong AND the site said they were
 * fine. These pin the badge's ability to say no.
 */
import {
  dataHealth, healthTitle, freshnessLabel, FRESH_HOURS, MISSED_HOURS,
} from "./freshness";

const H = 3600000;

describe("dataHealth", () => {
  test("a just-synced site is live", () => {
    expect(dataHealth(0).key).toBe("live");
    expect(dataHealth(2).key).toBe("live");
  });

  test("a run a few minutes late is not an alarm", () => {
    // The sync is 12-hourly and GitHub cron is best-effort; 12h05m must stay green or
    // the badge cries wolf twice a day and stops being read.
    expect(dataHealth(12.1).key).toBe("live");
  });

  test("a missed refresh goes amber, not green", () => {
    expect(dataHealth(FRESH_HOURS).key).toBe("late");
    expect(dataHealth(20).key).toBe("late");
  });

  test("over a full missed cycle goes red", () => {
    expect(dataHealth(MISSED_HOURS).key).toBe("stale");
    expect(dataHealth(120).key).toBe("stale");
  });

  test("the five-day outage this was written for is red, and never says LIVE", () => {
    const five = dataHealth(115.4);
    expect(five.key).toBe("stale");
    expect(five.label).toBe("STALE");
  });

  test("only the healthy state pulses", () => {
    expect(dataHealth(1).pulse).toBe(true);
    expect(dataHealth(20).pulse).toBe(false);
    expect(dataHealth(200).pulse).toBe(false);
  });

  test("green is reserved for live — the stale states carry no emerald", () => {
    for (const age of [FRESH_HOURS, 20, MISSED_HOURS, 500]) {
      const h = dataHealth(age);
      expect(`${h.cls} ${h.dot} ${h.text}`).not.toMatch(/emerald/);
    }
  });

  test("nothing ever synced renders no badge rather than a false one", () => {
    expect(dataHealth(null)).toBeNull();
    expect(dataHealth(undefined)).toBeNull();
    expect(dataHealth(NaN)).toBeNull();
  });

  test("the thresholds still agree with the server", () => {
    // server.py SCREEN_STALE_HOURS = 13, report_sync.py STALE_AFTER_HOURS = 26.
    // If either moves, this fails and the badge gets moved with it.
    expect(FRESH_HOURS).toBe(13);
    expect(MISSED_HOURS).toBe(26);
  });
});

describe("healthTitle", () => {
  const at = Date.now();

  test("the stale tooltips say what it means for the numbers, not just that time passed", () => {
    expect(healthTitle("late", at)).toMatch(/do not include/i);
    expect(healthTitle("stale", at)).toMatch(/out of date/i);
  });

  test("the live tooltip explains the cadence", () => {
    expect(healthTitle("live", at)).toMatch(/every 12h/);
  });

  test("every state names when the data actually came from", () => {
    for (const key of ["live", "late", "stale"]) {
      expect(healthTitle(key, at)).toContain(new Date(at).toLocaleString());
    }
  });
});

describe("freshnessLabel", () => {
  const now = Date.now();

  test("reads in the largest sensible unit", () => {
    expect(freshnessLabel(now - 12 * 60000, now)).toBe("12m ago");
    expect(freshnessLabel(now - 6 * H, now)).toBe("6h ago");
    expect(freshnessLabel(now - 5 * 24 * H, now)).toBe("5d ago");
  });

  test("a clock skew that puts the sync in the future does not show negative time", () => {
    expect(freshnessLabel(now + 5 * 60000, now)).toBe("0m ago");
  });

  test("no sync means no label", () => {
    expect(freshnessLabel(null, now)).toBeNull();
  });
});
