// The three-month review, as one card — what it may claim, and how it must label it.
//
// THIS CARD CARRIES TWO KINDS OF NUMBER AND THEY MUST NOT MERGE.
//
//   STATED     the channel's monthly units (lib/channelResults.js). The account's own
//              record of the picks it sent out. The site cannot check these: its ledger
//              holds the model's automated selections, not the picks actually posted.
//   VERIFIED   the site's graded record (/api/results). Every streak published before
//              kick-off, settled off a snapshot frozen BEFORE the game, so the list being
//              graded is the list that was claimed. A hit rate with its denominator —
//              never units, because those rows carry a line and no price.
//
// An advert that blended them would be the strongest number on the card borrowing the
// credibility of the other, which is the exact move this file exists to prevent. They are
// drawn in separate blocks and each is labelled with where it came from.
//
// THREE RULES INHERITED FROM recordCard.js, for the same reasons:
//
//   1. A rate without its denominator is unfalsifiable. "66%" is a claim nobody can check;
//      "31 of 47" is one anybody can. The denominator is never optional.
//   2. A month still running cannot sit in a total that reads as final. resultsSummary.js
//      already makes that call and is used rather than re-decided here.
//   3. No profit figure on the verified half. Not because it would be unflattering —
//      because it would have to be invented.
import { summarise } from "./resultsSummary.js";
import { recentPeriods, SOURCE_NOTE } from "./channelResults.js";

export { SOURCE_NOTE };

/** Three months is the review; more than four blocks stops being readable on a phone. */
export const MAX_PERIODS = 4;
export const DEFAULT_PERIODS = 3;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** "+20.73u" / "-4.50u" — a unit figure always wears its sign. */
export const unitsText = (units) => {
  const n = num(units);
  if (n === null) return "";
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(2)}u`;
};

/**
 * The verified block: the site's own graded record over the whole period.
 *
 * NULL WHEN NOTHING HAS SETTLED, rather than "0 of 0". A card claiming a record that does
 * not exist yet is worse than a card without that block — and an empty denominator is how
 * one gets published by accident.
 */
export const verifiedBlock = (summary = null) => {
  if (!summary) return null;
  const settled = num(summary.settled) || 0;
  const landed = num(summary.landed) || 0;
  if (!settled) return null;
  return {
    landed,
    settled,
    big: `${landed} of ${settled}`,
    rate: Math.round((landed / settled) * 100),
    pending: num(summary.pending) || 0,
    voided: num(summary.voided) || 0,
    since: summary.since || null,
    // Carried so the card can say what the hit rate covers. Not a units figure: see rule 3.
    weeks: num(summary.weeks) || 0,
  };
};

/**
 * The card, or null when there is nothing to publish.
 *
 * `periods` is the stated monthly record; `record` is whatever /api/results returned.
 * Either may be missing — a card with only the stated months is the one this account has
 * been able to make all along, and the verified block is an addition to it, not a
 * replacement.
 */
export const reviewFrom = ({ periods = null, record = null,
                             count = DEFAULT_PERIODS } = {}) => {
  const rows = (periods || recentPeriods(Math.min(count, MAX_PERIODS)))
    .filter((r) => r && num(r.units) !== null)
    .slice(0, MAX_PERIODS);
  if (!rows.length) return null;

  const blocks = rows.map((r) => ({
    period: r.period,
    units: num(r.units),
    unitsText: unitsText(r.units),
    up: num(r.units) > 0,
    // A month still running says so on its own row, not only in the total. The row is what
    // gets screenshotted out of context.
    partial: Boolean(r.partial),
    note: r.partial ? "month to date" : "",
  }));

  // The total is resultsSummary's, so the card and the join page cannot disagree about
  // what "since June" adds up to — including the rule about a running month.
  const totals = summarise(rows);
  return {
    blocks,
    n: blocks.length,
    total: totals.total,
    totalText: unitsText(totals.total),
    settledTotal: totals.settled,
    partial: totals.partial,
    running: totals.running,
    verified: verifiedBlock(record?.summary || null),
    source: SOURCE_NOTE,
  };
};

/**
 * The post that goes with the picture.
 *
 * THE IMAGE IS NOT THE POST. A graphic is a claim a reader has to take on trust; these
 * lines are the part that survives a failed render, and the part a sceptic can quote back.
 */
export const reviewPost = ({ review = null, site = "", heading = "The record so far" } = {}) => {
  if (!review) return "";
  const lines = [heading, ""];
  review.blocks.forEach((b) => {
    lines.push(`${b.period}: ${b.unitsText}${b.partial ? " (month to date)" : ""}`);
  });
  lines.push("");
  lines.push(review.partial
    ? `${review.totalText} in total, with ${review.running.join(" and ")} still running`
    : `${review.totalText} in total`);
  if (review.verified) {
    lines.push("");
    lines.push(`Model record, graded on site: ${review.verified.big} published streaks `
               + `landed (${review.verified.rate}%)`);
  }
  lines.push("");
  lines.push(review.source);
  if (site) {
    lines.push("");
    lines.push(site);
  }
  return lines.join("\n");
};
