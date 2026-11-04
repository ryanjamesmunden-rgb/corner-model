// The published results table on the join page.
//
// THIS IS THE PART OF THE SITE A SCEPTICAL BUYER CHECKS FIRST, and the only thing that
// makes it worth anything is that it cannot quietly overstate. The specific way a results
// table overstates is not by inventing a number — it is by presenting a RUNNING month
// beside CLOSED ones and letting the total read as settled. September at +16 with two
// weeks left is a true number arranged into a false impression, in exactly the way the day
// card was: the honest fix is not to hide it, it is to label it and to make the total say
// what it contains.
//
// So a partial month is marked at the source and the summary refuses to present a total as
// final while one is in it. The alternative — a `partial` flag the renderer may or may not
// remember to honour — is how the label goes missing in a later edit that only touched
// layout.

/**
 * Total the published months, and say honestly what the total covers.
 *
 * Returns `partial: true` when any row is still running, along with the names of the months
 * that are. `settled` is the total of the closed months alone, so a caller that wants to
 * show a figure nobody can argue with has one without recomputing it.
 */
export const summarise = (rows = []) => {
  const list = (rows || []).filter((r) => r && Number.isFinite(Number(r.units)));
  const total = list.reduce((a, r) => a + Number(r.units), 0);
  const running = list.filter((r) => r.partial);
  const settled = list.filter((r) => !r.partial)
    .reduce((a, r) => a + Number(r.units), 0);
  return {
    total: Math.round(total * 100) / 100,
    settled: Math.round(settled * 100) / 100,
    partial: running.length > 0,
    // Named rather than counted, because "1 month still running" makes a reader hunt for
    // which one while the answer is right there in the table.
    running: running.map((r) => r.period),
  };
};

/** "Since June" / "Since June, September still running" — the total's own caveat. */
export const totalLabel = (rows = [], since = "Since June") => {
  const { partial, running } = summarise(rows);
  return partial ? `${since} · ${running.join(", ")} still running` : since;
};

/** The suffix beside a single row. Empty for a closed month. */
export const periodNote = (row = {}) => (row.partial ? "month to date" : "");

/**
 * A unit figure wearing its own sign: "+48.70" / "−12.54" / "0.00".
 *
 * WHY THIS IS NOT LEFT TO THE MARKUP. The join page's total row printed a literal "+"
 * and a literal green, while the rows above it branched on the sign properly. With the
 * running total positive that read correctly and looked finished — but a losing month
 * big enough to turn the total over would have rendered "+−12.54" in green, on the one
 * table this file's header calls the first thing a sceptical buyer checks. A sign that
 * is only right while the number happens to be positive is not a sign.
 *
 * The minus is U+2212, not a hyphen, matching reviewCard.unitsText so the same figure
 * reads the same whether it is on the page or on a card.
 */
export const signedUnits = (units, dp = 2) => {
  // "" must not become 0.00: Number("") is 0 and finite, so a blank figure would print
  // as a real result. A missing number is blank, never zero.
  if (units === null || units === undefined || units === "") return "";
  const n = Number(units);
  if (!Number.isFinite(n)) return "";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${Math.abs(n).toFixed(dp)}`;
};

/** Which way a figure should read: "up", "down", or "flat" for exactly zero. */
export const unitsTone = (units) => {
  const n = Number(units);
  if (!Number.isFinite(n) || n === 0) return "flat";
  return n > 0 ? "up" : "down";
};
