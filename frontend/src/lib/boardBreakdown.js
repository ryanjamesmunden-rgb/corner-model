/**
 * The record, split by which board made the claim, as rows a panel can render.
 *
 * WHY A SEPARATE MODULE. This file holds the decisions that are easy to get quietly
 * wrong — when a rate may be shown at all, which way a residual reads, whether a
 * denominator is worth printing — and none of them are about React. The repo tests
 * logic in src/lib and has no component renderer, so anything worth pinning has to
 * live here rather than inside the JSX.
 *
 * THE RESIDUAL IS THE RESULT. A board landing 73% against its own stated 82% is losing;
 * one landing 61% against a stated 59% is winning. The hit rate alone describes which
 * games happened to get picked, not whether the board was right about them.
 *
 * A RATE REFUSES TO EXIST WITHOUT SETTLED GAMES — the same rule as recordCard and the
 * backend's _tally. Nothing settled and everything missed are different facts, and 0%
 * for the first is a lie about the second.
 */

/** A board with no frozen claims at all is not a board with a bad record. */
export const hasRecord = (b) => Number(b?.claims) > 0;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * One board -> one row, or null when there is nothing frozen to describe.
 *
 * `rate` is null unless something has settled. `residual` is null unless the board
 * stored a probability on settled rows — it cannot be inferred from the hit rate.
 */
export const boardLine = (b) => {
  if (!hasRecord(b)) return null;
  const settled = num(b.settled) || 0;
  const resid = num(b.residual);
  const lo = num(b.lo);
  const hi = num(b.hi);
  const frozen = num(b.frozen_rows);
  const claims = num(b.claims);
  return {
    key: b.key,
    label: b.label || b.key,
    blurb: b.blurb || "",
    settled,
    landed: num(b.landed) || 0,
    missed: num(b.missed) || 0,
    voided: num(b.voided) || 0,
    pending: num(b.pending) || 0,
    claims,
    // Shown only once something has been played. See the note at the top.
    rate: settled > 0 ? num(b.hit_rate) : null,
    // Printed together or not at all: half an interval is not an interval.
    interval: settled > 0 && lo !== null && hi !== null ? { lo, hi } : null,
    meanProb: num(b.mean_prob),
    residual: resid,
    // "beat" / "short" / "level", so nothing depends on colour alone — the site's tones
    // are close enough under colour blindness that none may carry a meaning by itself.
    verdict: resid === null ? null : resid > 0 ? "beat" : resid < 0 ? "short" : "level",
    // THE REPEATS LINE, only when there were repeats. These boards freeze every morning
    // over a seven-day horizon, so the gap is usually large, and it is the difference
    // between an honest denominator and one several times too big.
    repeats: frozen !== null && claims !== null && frozen > claims
      ? { frozen, claims, snapshots: num(b.snapshots) || 0 }
      : null,
  };
};

/** The day's boards as rows, dropping any with nothing frozen. */
export const boardLines = (boards = []) =>
  (Array.isArray(boards) ? boards : []).map(boardLine).filter(Boolean);
