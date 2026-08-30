// What of the ledger is fit to publish on a sales page.
//
// The join page advertises a paid subscription against this record, so the failure mode
// is not a wrong pixel — it is a headline ROI computed from nine bets that reads like a
// track record. Every number shown has to carry the sample it came from, and a sample
// too small to mean anything has to be withheld rather than rounded into confidence.
//
// Kept out of the page so the thresholds are testable without a DOM, and so the rule
// about when a number may be shown lives in one place rather than in JSX conditionals.

// Below this many settled picks, no headline percentage is shown at all. This is not a
// significance test — it is a floor beneath which a percentage is actively misleading.
// 20 is already generous; it is chosen so an empty or barely-started ledger cannot
// produce a number, not to certify that 20 is enough to judge anything on.
export const MIN_SAMPLE = 20;

/**
 * Ledger summary -> what the page may state.
 *
 * ROI and profit come only from picks with a RECORDED PRICE (see _record in server.py:
 * a win at an unknown price has no return). So they describe a subset of the settled
 * picks, and the page has to say which subset — otherwise a ledger where only the
 * memorable bets got a price typed in would advertise itself as the whole record.
 */
export function publishableRecord(summary) {
  if (!summary) return null;
  const settled = summary.settled || 0;
  const staked = summary.staked || 0;
  const unpriced = summary.unpriced || 0;
  return {
    settled,
    staked,
    unpriced,
    pending: summary.pending || 0,
    voided: summary.void || 0,
    winRate: summary.win_rate,
    profit: summary.profit,
    roi: summary.roi,
    // A strike rate needs settled picks; a return needs PRICED ones. They gate separately
    // because a ledger can be rich in one and empty in the other, and usually is.
    showWinRate: settled >= MIN_SAMPLE,
    showReturn: staked >= MIN_SAMPLE,
    // Share of settled picks that carry a price. Under 100% the money figures describe
    // part of the record, and the page must print this next to them.
    coverage: settled ? Math.round((staked / settled) * 100) : 0,
    // Nothing here is worth showing yet — the page says so instead of drawing empty tiles.
    empty: settled < MIN_SAMPLE && staked < MIN_SAMPLE,
  };
}

/** "+12.4" / "-3.0" — a sign is not optional on a P&L figure. */
export function signed(n, dp = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(dp)}`;
}
