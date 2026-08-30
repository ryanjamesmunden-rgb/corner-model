/**
 * The join page sells a £20/month subscription against these numbers, so the thing to
 * defend against is not a rendering bug — it is a confident-looking headline drawn from
 * a handful of bets, or a return quietly computed over whichever picks happened to have
 * a price typed in. Both would be advertising claims the ledger cannot support.
 */
import { publishableRecord, signed, MIN_SAMPLE } from "./record";

const summary = (over = {}) => ({
  picks: 0, settled: 0, void: 0, won: 0, lost: 0, pending: 0,
  win_rate: 0, staked: 0, profit: 0, roi: 0, unpriced: 0, unpriced_wins: 0, ...over,
});

describe("publishableRecord", () => {
  test("an empty ledger publishes nothing", () => {
    const r = publishableRecord(summary());
    expect(r.empty).toBe(true);
    expect(r.showWinRate).toBe(false);
    expect(r.showReturn).toBe(false);
  });

  test("a handful of bets is not a track record", () => {
    const r = publishableRecord(summary({ settled: 9, staked: 9, win_rate: 100, roi: 44.0 }));
    // 9 from 9 at +44% ROI is exactly the shape of number that sells a subscription and
    // means nothing. It must not reach the page.
    expect(r.showWinRate).toBe(false);
    expect(r.showReturn).toBe(false);
    expect(r.empty).toBe(true);
  });

  test("the threshold is inclusive, so a record at the floor publishes", () => {
    const r = publishableRecord(summary({ settled: MIN_SAMPLE, staked: MIN_SAMPLE }));
    expect(r.showWinRate).toBe(true);
    expect(r.showReturn).toBe(true);
    expect(r.empty).toBe(false);
  });

  test("a strike rate can publish while a return cannot", () => {
    // The common real state: plenty settled, few with a price typed in. server.py computes
    // ROI only over priced picks, so showing it here would advertise a subset as the whole.
    const r = publishableRecord(summary({ settled: 80, staked: 4, win_rate: 61.2, unpriced: 76 }));
    expect(r.showWinRate).toBe(true);
    expect(r.showReturn).toBe(false);
  });

  test("partial price coverage is reported, not hidden", () => {
    const r = publishableRecord(summary({ settled: 100, staked: 40, unpriced: 60 }));
    expect(r.coverage).toBe(40);
    expect(r.unpriced).toBe(60);
  });

  test("full coverage reads as 100 so the caveat can be suppressed", () => {
    expect(publishableRecord(summary({ settled: 50, staked: 50 })).coverage).toBe(100);
  });

  test("coverage of an empty ledger does not divide by zero", () => {
    expect(publishableRecord(summary()).coverage).toBe(0);
  });

  test("a losing record publishes exactly as readily as a winning one", () => {
    // Nothing may gate on the sign — a page that only shows its record when ahead is
    // worse than one with no record at all.
    const win = publishableRecord(summary({ settled: 60, staked: 60, roi: 8.2, profit: 4.9 }));
    const lose = publishableRecord(summary({ settled: 60, staked: 60, roi: -8.2, profit: -4.9 }));
    expect(lose.showReturn).toBe(win.showReturn);
    expect(lose.showWinRate).toBe(win.showWinRate);
    expect(lose.roi).toBe(-8.2);
  });

  test("missing fields degrade to zero rather than NaN on the page", () => {
    const r = publishableRecord({});
    expect(r.settled).toBe(0);
    expect(r.staked).toBe(0);
    expect(r.empty).toBe(true);
  });

  test("no summary at all is null, so the page can say the record is unavailable", () => {
    expect(publishableRecord(null)).toBeNull();
    expect(publishableRecord(undefined)).toBeNull();
  });
});

describe("signed", () => {
  test("a positive P&L carries its plus sign", () => {
    expect(signed(12.4)).toBe("+12.4");
    expect(signed(4.85, 2)).toBe("+4.85");
  });

  test("a negative one is not disguised", () => {
    expect(signed(-3)).toBe("-3.0");
  });

  test("zero is neither", () => {
    expect(signed(0)).toBe("0.0");
  });

  test("an absent figure renders as a dash, never as 0", () => {
    // "0.0%" would read as break-even; there is a difference between flat and unknown.
    expect(signed(null)).toBe("—");
    expect(signed(undefined)).toBe("—");
    expect(signed(NaN)).toBe("—");
  });
});
