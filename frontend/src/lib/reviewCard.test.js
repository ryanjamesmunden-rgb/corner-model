/**
 * What a three-month advert may claim.
 *
 * The card carries two kinds of number — the channel's stated units and the site's graded
 * record — and most of what is pinned here is that they stay apart, that a running month
 * cannot hide inside a final-looking total, and that a record which does not exist yet is
 * not drawn at all.
 */
import { reviewFrom, reviewPost, verifiedBlock, unitsText } from "./reviewCard.js";

const CLOSED = [
  { period: "September", units: 16.0 },
  { period: "August", units: 20.73 },
  { period: "June - July", units: 17.14 },
];

const RUNNING = [{ period: "October", units: 4.2, partial: true }, ...CLOSED];

const record = (over = {}) => ({
  summary: { landed: 31, settled: 47, pending: 3, voided: 2, weeks: 14,
             since: "2026-06-29", ...over },
});

describe("unit figures", () => {
  test("always wear their sign", () => {
    expect(unitsText(20.73)).toBe("+20.73u");
    expect(unitsText(-4.5)).toBe("−4.50u");
    expect(unitsText(0)).toBe("0.00u");
  });

  test("and a missing one is blank rather than zero", () => {
    expect(unitsText(null)).toBe("");
    expect(unitsText("")).toBe("");
  });
});

describe("the verified block", () => {
  test("is a fraction, not a bare percentage", () => {
    // "66%" is a claim nobody can check; "31 of 47" is one anybody can.
    const v = verifiedBlock(record().summary);
    expect(v.big).toBe("31 of 47");
    expect(v.rate).toBe(66);
  });

  test("does not exist when nothing has settled", () => {
    // A card reading "0 of 0" is a claim about a record that has not been made yet.
    expect(verifiedBlock({ landed: 0, settled: 0, pending: 9 })).toBeNull();
    expect(verifiedBlock(null)).toBeNull();
  });
});

describe("the card", () => {
  test("nothing stated means no card", () => {
    expect(reviewFrom({ periods: [] })).toBeNull();
    expect(reviewFrom({ periods: [{ period: "August" }] })).toBeNull();
  });

  test("the months keep the order they were handed in", () => {
    const r = reviewFrom({ periods: CLOSED });
    expect(r.blocks.map((b) => b.period)).toEqual(["September", "August", "June - July"]);
    expect(r.blocks[1].unitsText).toBe("+20.73u");
  });

  test("the total is the sum of the months", () => {
    expect(reviewFrom({ periods: CLOSED }).total).toBe(53.87);
  });

  test("a running month is labelled on its own row AND in the total", () => {
    // The row is what gets screenshotted out of context, so the caveat cannot live only
    // in the footer.
    const r = reviewFrom({ periods: RUNNING, count: 4 });
    expect(r.blocks[0].partial).toBe(true);
    expect(r.blocks[0].note).toBe("month to date");
    expect(r.partial).toBe(true);
    expect(r.running).toEqual(["October"]);
    // And the closed-months total is available so a caller can show one nobody can argue
    // with rather than recomputing it.
    expect(r.settledTotal).toBe(53.87);
  });

  test("the stated months and the graded record stay in separate blocks", () => {
    const r = reviewFrom({ periods: CLOSED, record: record() });
    expect(r.total).toBe(53.87);
    expect(r.verified.big).toBe("31 of 47");
    // No units anywhere on the verified half: those rows carry a line and no price.
    expect(r.verified.units).toBeUndefined();
  });

  test("and the card still draws without a graded record", () => {
    const r = reviewFrom({ periods: CLOSED, record: null });
    expect(r.verified).toBeNull();
    expect(r.blocks).toHaveLength(3);
  });

  test("it carries the line saying where the stated figures came from", () => {
    expect(reviewFrom({ periods: CLOSED }).source).toMatch(/recorded in the channel/i);
  });
});

describe("the post", () => {
  test("lists every month, the total and the graded record", () => {
    const out = reviewPost({ review: reviewFrom({ periods: CLOSED, record: record() }),
                             site: "thecornermodel.com" });
    expect(out).toContain("September: +16.00u");
    expect(out).toContain("August: +20.73u");
    expect(out).toContain("+53.87u in total");
    expect(out).toContain("31 of 47");
    expect(out).toContain("recorded in the channel");
    expect(out).toContain("thecornermodel.com");
  });

  test("a running month is said out loud in the total line", () => {
    const out = reviewPost({ review: reviewFrom({ periods: RUNNING, count: 4 }) });
    expect(out).toContain("October: +4.20u (month to date)");
    expect(out).toContain("with October still running");
  });

  test("no card, no post", () => {
    expect(reviewPost({ review: null })).toBe("");
  });
});
