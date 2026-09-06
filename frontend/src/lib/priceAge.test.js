/**
 * The value board's whole claim is "this line is worth backing", computed against a
 * price a human typed in at some point. So what is pinned here is that an OLD price is
 * never allowed to look like a fresh one, and that a missing timestamp is reported as
 * missing rather than silently treated as new — the row that says "just now" about a
 * price from Tuesday is the one that costs someone money.
 */
import { priceAge, priceFreshness } from "./priceAge";

const NOW = Date.parse("2026-09-06T12:00:00Z");
const ago = (ms) => new Date(NOW - ms).toISOString();
const MIN = 60e3, HOUR = 60 * MIN, DAY = 24 * HOUR;

describe("age in words", () => {
  test("is coarse on purpose", () => {
    expect(priceAge(ago(MIN), NOW).label).toBe("just now");
    expect(priceAge(ago(20 * MIN), NOW).label).toBe("20m ago");
    expect(priceAge(ago(3 * HOUR), NOW).label).toBe("3h ago");
    expect(priceAge(ago(26 * HOUR), NOW).label).toBe("yesterday");
    expect(priceAge(ago(72 * HOUR), NOW).label).toBe("3d ago");
  });

  test("has no answer rather than a wrong one", () => {
    expect(priceAge(null)).toBe(null);
    expect(priceAge(undefined)).toBe(null);
    expect(priceAge("nonsense")).toBe(null);
  });

  test("never reports a future timestamp as negative age", () => {
    expect(priceAge(new Date(NOW + HOUR).toISOString(), NOW).label).toBe("just now");
  });
});

describe("freshness", () => {
  test("escalates with age", () => {
    expect(priceFreshness(ago(30 * MIN), NOW).key).toBe("fresh");
    expect(priceFreshness(ago(4 * HOUR), NOW).key).toBe("ageing");
    expect(priceFreshness(ago(30 * HOUR), NOW).key).toBe("stale");
  });

  test("a missing timestamp is 'unknown', never 'fresh'", () => {
    const f = priceFreshness(null, NOW);
    expect(f.key).toBe("unknown");
    expect(f.key).not.toBe("fresh");
    expect(f.note).toBeTruthy();          // says why, and what to do about it
  });

  test("only a fresh price is allowed to say nothing", () => {
    expect(priceFreshness(ago(30 * MIN), NOW).note).toBe("");
    for (const old of [4 * HOUR, 30 * HOUR]) {
      expect(priceFreshness(ago(old), NOW).note).toBeTruthy();
    }
  });
});
