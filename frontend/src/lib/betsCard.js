// Today's bets, as one card — what it may claim, and what it must admit.
//
// WHY THIS IS NOT JUST A LAYOUT FILE. This is the one card on the site that posts a PROFIT
// figure, and a profit figure is the single most over-claimed object in this industry. So
// the deciding happens here, in a tested function, rather than in the drawing code where
// nobody would look at it again — the same reasoning recordCard.js sets out, and the same
// reason that file refuses to post units at all.
//
// WHAT MAKES IT POSTABLE HERE AND NOT THERE. recordCard draws posted ANGLES, which are
// stored with a line and no price, so any unit figure on one would mean inventing odds
// after the fact. These rows cannot exist without a price: the backend selects them on EV,
// EV cannot be computed without a book price, and only a manually entered price counts
// (server.py `_value_shortlist`). Every row therefore carries the price the bet was
// published at, and the units follow from it rather than from a guess.
//
// THREE RULES, each because breaking it is the normal thing to do:
//
//   1. EVERY ROW STAYS ON THE CARD, including the losers. Dropping a lost bet from the
//      afternoon re-draw would make the evening card a selection of the morning's winners
//      — a lie told with true numbers. `cardFrom` takes what the day froze, in full.
//   2. THE RUNNING TOTAL COUNTS SETTLED BETS ONLY, and says how many are still open.
//      "+1.63u" above two pending rows is not a day's result, it is a half-time score, and
//      a reader who cannot see the denominator cannot tell the difference.
//   3. A PRICE IS A BOOK PRICE OR THE ROW DOES NOT EXIST. There is no "fair" fallback on
//      this card. dailySlip.js draws the model's break-even number where no real price was
//      typed, because a morning slate is about fixtures; this card is about bets, and a bet
//      at a price nobody can get is not one.
import { slipTime, slipZoneLabel, SLIP_TZ } from "./dailySlip.js";

export { SLIP_TZ };

/** Settlement's own statuses, so the card and the ledger cannot disagree about a result. */
export const WON = "won";
export const LOST = "lost";
export const VOID = "void";
export const HALF_WON = "half_won";
export const HALF_LOST = "half_lost";
export const PENDING = "pending";

const WIN_LIKE = [WON, HALF_WON];
const LOSS_LIKE = [LOST, HALF_LOST];
export const SETTLED = [...WIN_LIKE, ...LOSS_LIKE, VOID];

/** Fewer than this is not a card. One bet is a message, not a board. */
export const MIN_CARD_ROWS = 1;
/** What the drawing can hold while staying readable on a phone. */
export const MAX_CARD_ROWS = 6;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const one = (v) => {
  const n = num(v);
  return n === null ? null : Math.round(n * 10) / 10;
};

/** "WON" / "LOST" / "VOID" / "PENDING" — what the pill says. */
export const statusLabel = (status) => {
  if (WIN_LIKE.includes(status)) return status === HALF_WON ? "HALF WON" : "WON";
  if (LOSS_LIKE.includes(status)) return status === HALF_LOST ? "HALF LOST" : "LOST";
  if (status === VOID) return "VOID";
  return "PENDING";
};

/** Which of the three colours a row is drawn in. Never a fourth: a void is not a loss. */
export const statusTone = (status) =>
  (WIN_LIKE.includes(status) ? "win"
    : LOSS_LIKE.includes(status) ? "loss"
      : status === VOID ? "void" : "pending");

/**
 * The result, in corners, as the bet was actually judged.
 *
 * A TEAM BET IS JUDGED ON ONE SIDE'S CORNERS AND A TOTAL ON BOTH, and printing the wrong
 * one beside a settled bet is how a card ends up showing "WON 7" against a line of 9. The
 * subject decides which number is shown, and the number shown is the one the grader used.
 */
export const resultText = (p = {}) => {
  const own = num(p.result_corners);
  const opp = num(p.result_opp_corners);
  if (own === null) return "";
  if (p.subject === "match") {
    const total = num(p.result_total_corners) ?? (opp === null ? null : own + opp);
    return total === null ? "" : `${total} corners`;
  }
  return opp === null ? `${own} corners` : `${own}-${opp} corners`;
};

/** "+0.95u" / "-1u" / "0u" — the units this bet returned, at a flat 1u stake. */
export const profitText = (profit) => {
  const n = num(profit);
  if (n === null) return "";
  const rounded = Math.round(n * 100) / 100;
  if (rounded === 0) return "0u";
  return `${rounded > 0 ? "+" : ""}${rounded}u`;
};

/**
 * What the bet is, in words, with whose corners it is about.
 *
 * "6+" IS TWO DIFFERENT BETS — a team's own corners and the match total are roughly a
 * factor of two apart — so the subject is always printed, for the same reason
 * fixtureStreaks.js prints it. A card showing the bare number would hand the reader the
 * wrong bet half the time.
 *
 * AND IT NAMES THE TEAM RATHER THAN THE SIDE. The backend stores the market's own label,
 * "Home Team Over 5.5", which is what a ladder on a fixture page should say — the page
 * already knows which fixture it is. On a card the row carries two club names, and "Home
 * Team" asks the reader to work out which of them is meant, in a column narrow enough
 * that the words were being truncated to "Home Team Over…" anyway. The stored label stays
 * as the fallback for anything this cannot build.
 */
export const betLabel = (p = {}) => {
  const line = num(p.line);
  if (line === null) return p.label || "";
  return p.subject === "match"
    ? `Over ${line} match corners`
    : `${p.team || p.label || "Team"} ${line}+ corners`;
};

/** One frozen pick, reduced to what the card prints. */
export const cardRow = (p = {}) => {
  const status = p.status || PENDING;
  return {
    home: p.home || "",
    away: p.away || "",
    leagueId: p.league_id || "",
    league: p.league_name || "",
    time: slipTime(p.kickoff),
    market: betLabel(p),
    // The price the bet was PUBLISHED at. See rule 3 at the top of this file.
    price: num(p.odds),
    fair: num(p.model_odds),
    ev: one(p.ev),
    status,
    tone: statusTone(status),
    statusLabel: statusLabel(status),
    result: resultText(p),
    profit: num(p.profit),
    profitText: profitText(p.profit),
    settled: SETTLED.includes(status),
    key: `${p.fixture_id}-${p.market_key}`,
  };
};

/**
 * The day's card, or null when there is nothing to post.
 *
 * NULL RATHER THAN AN EMPTY CARD. A card headed "TODAY'S BETS" with no rows under it is
 * not a quiet day, it reads as a broken job — and the days this returns null are ordinary:
 * no price has been typed in, or nothing typed in clears the floor. The caller posts
 * nothing, which is the honest output for a day with no bets on it.
 */
export const cardFrom = ({ rows = [], day = null, summary = null, max = MAX_CARD_ROWS } = {}) => {
  const priced = (rows || []).filter((p) => num(p?.odds));
  if (priced.length < MIN_CARD_ROWS) return null;
  // CHOSEN ON EDGE, SHOWN IN KICK-OFF ORDER, and the two steps are separate on purpose.
  //
  // Sorting by kick-off and then cutting to the cap would keep the EARLIEST six and throw
  // away whatever the day's best bet happened to be if it kicked off late — a selection
  // rule nobody intended, hidden inside a display decision. So the cut is still made on
  // the edge, and only what survives it is put into the order the day plays out in.
  //
  // The order changed because leading on the biggest edge reads wrong on a card that is
  // checked against the day as it happens: a reader looking for the next game had to hunt
  // for it, and the evening re-draw listed results in an order the results did not arrive
  // in.
  const kept = [...priced]
    .sort((a, b) => (num(b.ev) ?? 0) - (num(a.ev) ?? 0))
    .slice(0, Math.max(1, max))
    .sort((a, b) => String(a.kickoff || "").localeCompare(String(b.kickoff || ""))
                    || (num(b.ev) ?? 0) - (num(a.ev) ?? 0))
    .map(cardRow);
  const settled = kept.filter((r) => r.settled);
  const graded = settled.filter((r) => r.status !== VOID);
  // Units are summed over SETTLED rows only. A pending bet has no result to add, and
  // counting it as zero would make an open day look like a flat one.
  const units = settled.reduce((t, r) => t + (r.profit ?? 0), 0);
  return {
    day: day || null,
    zone: slipZoneLabel(kept[0]?.kickoff || day),
    rows: kept,
    n: kept.length,
    hidden: Math.max(0, priced.length - kept.length),
    won: graded.filter((r) => r.tone === "win").length,
    lost: graded.filter((r) => r.tone === "loss").length,
    voided: settled.length - graded.length,
    pending: kept.length - settled.length,
    settled: settled.length,
    units: Math.round(units * 100) / 100,
    unitsText: profitText(units),
    // Nothing settled yet means there is no result to state — the footer says so rather
    // than printing "0u", which reads as a day that went nowhere.
    hasResult: settled.length > 0,
    // Carried through so a caller can state the floor the day was selected at. A card
    // claiming "positive EV" that was built at a 5% bar is making a different claim.
    minEv: one(summary?.min_ev ?? null),
  };
};

/**
 * The post that goes with the picture.
 *
 * THE IMAGE IS NOT THE POST. A graphic is a claim a reader has to take on trust; the lines
 * below are the part that can be checked, and they are what survives when an image fails to
 * render or a client collapses it.
 */
export const cardPost = ({ card = null, site = "", heading = "Today's bets" } = {}) => {
  if (!card) return "";
  const lines = [heading, ""];
  card.rows.forEach((r) => {
    const tail = r.settled ? `${r.statusLabel}${r.result ? ` ${r.result}` : ""} ${r.profitText}`.trim()
      : `${r.time || ""}`.trim();
    lines.push(`${r.home} v ${r.away} — ${r.market} @ ${r.price}${tail ? `  ·  ${tail}` : ""}`);
  });
  lines.push("");
  lines.push(card.hasResult
    ? `${card.won} won · ${card.lost} lost${card.voided ? ` · ${card.voided} void` : ""}`
      + `${card.pending ? ` · ${card.pending} pending` : ""} · ${card.unitsText}`
    : `${card.n} bet${card.n === 1 ? "" : "s"} · all pending`);
  if (site) {
    lines.push("");
    lines.push(site);
  }
  return lines.join("\n");
};
