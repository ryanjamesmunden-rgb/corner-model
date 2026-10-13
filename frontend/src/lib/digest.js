// One message a day: the teams on a corner run, banded by what that line has paid.
//
// WHAT THIS REPLACES, AND WHY. The bot sent eight messages on a Monday — a slate, two
// bets cards, an X draft, a numbered menu of five different boards, the day's best game, a
// statistic to post, and a locked-in list. Several were built for an audience of one and
// all of them went to the same chat, so the useful ones arrived inside a stream of things
// nobody needed to read. The complaint that produced this file was "so many messages that
// are not value, just a streak or fair price with no context", and both halves of that are
// fair: a streak with no opponent is a fact about last month, and a fair price with no
// book price beside it is not an edge.
//
// SO: ONE MESSAGE, ONE BOARD. Streaks only. No chase board, no mismatches, no value list,
// no numbered menu to choose from. The other boards are not deleted — they are still on
// the site and still one dispatch away — they just stop arriving unasked.
//
// AND THE ORDER IS THE BETTING RECORD, NOT THE BOARD'S. The streak endpoint sorts by how
// high the line is, so left alone the first thing a digest offers is the longest run on the
// highest line, and the highest lines are the part of the sheet that has never paid. The
// bands in lineBands.js re-sort it by what each line has actually returned, and the band
// headings carry the record WITH its denominator so a thin band cannot read as a strong
// one. A row below the money band is shown rather than hidden — hiding it would make the
// digest a recommendation engine, and the whole complaint was about being handed
// conclusions with no context — but it is shown under a heading that says what the band
// has cost.
//
// EVERY ROW CARRIES THE FIXTURE AND BOTH SIDES' RATES, which is the context that was
// missing. "Reading 6+, 7 in a row" is the claim; "7.8 at home against a defence giving up
// 6.2 away" is the reason, and it is also the pair of numbers the model's lambda is built
// from, so a reader who disagrees with the price can see which input they disagree with.
//
// SUBJECT: TEAM CORNER OVERS, nothing else, and that is a deliberate limit rather than an
// oversight. It is the exact market the band records in lineBands.js measure — 131 settled
// team-corner singles — so the caption above a row is a record of that row's own market.
// Conceded runs ("they ship 5+ every week") produce a bet in the same market and would fit
// the same bands, and they are the obvious next addition; they are not here because
// /api/share/rows builds one board per call and each call walks every team in the
// database, which is already the endpoint's documented timeout risk.

// EXPLICIT .js, because tools/digest.mjs imports this module in BARE NODE, where an
// extensionless specifier does not resolve. It works under webpack and under jest, so the
// failure only ever appears in the scheduled job — which is the one place nobody is
// watching. Same reason shareText.js spells its own imports out.
import { flagBullet } from "./countryFlag.js";
import { LINE_BANDS, bandRecord, BANDS_SOURCE } from "./lineBands.js";

/**
 * How long a run has to be to reach the digest.
 *
 * FIVE, matching SHARE_MIN_RUN. A run of two is two coin flips and there are hundreds of
 * them; the message is only worth opening if what is in it was hard to find.
 */
export const DIGEST_MIN_RUN = 5;

/**
 * How many rows each band gets.
 *
 * THE MONEY BAND GETS MOST OF THEM and the unproven band gets two, because the caps are
 * the only place the digest expresses a preference without hiding anything. Twelve rows
 * is already a long message; a digest that lists forty is the thing it replaced.
 */
export const DIGEST_CAPS = { money: 6, below: 3, long: 2 };

/**
 * A number, or null — and `null` is NOT a number.
 *
 * `Number.isFinite(Number(v))` ALONE IS NOT THIS TEST, which is what this was and what
 * the tests caught. `Number(null)` is 0 and so is `Number("")`, so a row whose average
 * the backend could not compute came through as a real zero: it ranked as though it
 * cleared its line by minus five, and — far worse — ratesOf printed "Reading 0.0 at home"
 * against a defence it had invented a rate for. A missing number has to stay missing all
 * the way to the renderer, which drops the line rather than writing a nought into it.
 */
const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** The run alive right now — the team's own, not the filter's minimum. */
export const runOf = (row) => num(row?.streak?.length) ?? 0;

/**
 * How much room the run has: the window average, less the line it has to clear.
 *
 * THE TIE-BREAK, AFTER RUN LENGTH. Two teams on six-game runs at 5+ are not the same bet
 * if one averages 8.2 and the other 5.4 — the second is clearing by a single corner a
 * week and is one quiet evening from the run ending. Same measure the browse page ranks
 * its own runs by, so the two cannot put the same pair of teams in opposite orders.
 */
export const marginOf = (row) => {
  const avg = num(row?.avg);
  const line = num(row?.line);
  return avg === null || line === null ? null : Math.round((avg - line) * 100) / 100;
};

/**
 * A measured edge, in EV points — or 0 where there is nothing to measure.
 *
 * THE ONE THING IN THIS MESSAGE THAT IS NOT AN ASSUMPTION. Every other row is the model's
 * own price against no price at all; a row where `/prices` holds a real quote and the
 * model beats it is an edge somebody could have taken. `db.odds` is manual-only, so a
 * stored price also means this is a game that has already been looked at by hand.
 *
 * ONLY A POSITIVE EV COUNTS. A stored price the model does NOT beat is evidence against
 * the row, so it must not jump the queue — it returns 0 and ranks on its run like the
 * rest, which is the honest treatment of a bet whose price has been checked and found
 * wanting.
 */
export const edgeOf = (row) => {
  const ev = num(row?.projection?.ev);
  const book = num(row?.projection?.book_odds);
  return book !== null && ev !== null && ev > 0 ? ev : 0;
};

/**
 * The rows, split into bands and ranked inside each one.
 *
 * RANKED BY MEASURED EDGE, THEN RUN, THEN MARGIN — and never by line. Line height is what
 * the band already encodes, so ranking by it inside a band would just re-apply the board's
 * own order. The edge comes first because it is the only key backed by a real price rather
 * than by the model's opinion of one, and a priced +EV row buried fifth behind four
 * unpriced ones is the message putting its weakest evidence at the top.
 *
 * `skipped` counts what the run floor and the caps removed, separately, because they mean
 * different things: a floor that removed thirty rows is a quiet week, and caps that
 * removed thirty is a week worth opening the site for. A digest that silently truncated
 * would read the same on both.
 */
export function digestBands(rows = [], { minRun = DIGEST_MIN_RUN,
                                          caps = DIGEST_CAPS } = {}) {
  const usable = (rows || []).filter((r) => r && num(r.line) !== null
                                         && runOf(r) >= minRun
                                         // A RUN WITH NO UPCOMING FIXTURE IS NOT A BET.
                                         // It renders as a team, a line and a number with
                                         // nothing under it — no opponent, no kick-off, no
                                         // link — which is the bare claim this whole file
                                         // exists to stop printing. The endpoint filters
                                         // these out when asked for a day window, so this
                                         // is a guard rather than the common path; it was
                                         // caught by running the tool, not by reading it.
                                         && r.next_fixture);
  const short = (rows || []).length - usable.length;

  const bands = LINE_BANDS.map((band) => {
    const mine = usable.filter((r) => {
      const n = num(r.line);
      return n >= band.min && n <= band.max;
    }).sort((a, b) => (edgeOf(b) - edgeOf(a))
                   || (runOf(b) - runOf(a))
                   || ((marginOf(b) ?? -99) - (marginOf(a) ?? -99)));
    const cap = caps[band.id] ?? mine.length;
    return { band, rows: mine.slice(0, cap), total: mine.length,
             held: Math.max(0, mine.length - cap) };
  });

  return {
    bands,
    shown: bands.reduce((a, b) => a + b.rows.length, 0),
    qualified: usable.length,
    skippedShort: short,
    held: bands.reduce((a, b) => a + b.held, 0),
  };
}

/** "Reading 6+ — 7 in a row". The claim, and nothing that is not the claim. */
export const claimOf = (row) => {
  const line = row?.line_label || (num(row?.line) !== null ? `${row.line}+` : "");
  const run = runOf(row);
  const tail = run >= 2 ? ` — ${run} in a row` : "";
  return `${row?.name || ""}${line ? ` ${line}` : ""}${tail}`.trim();
};

/**
 * "v Hull (H) · Mon 15:00" — who, where, when.
 *
 * THE VENUE LETTER IS ABOUT THE NEXT GAME, NOT THE RUN. The board is asked for `overall`
 * runs, so "7 in a row" spans both venues and writing "7 in a row at home" would be
 * false. Where the next one is played still belongs here: it is what decides whether the
 * two rates on the line below are the ones that matter.
 */
export const fixtureOf = (row, dayTime) => {
  const nf = row?.next_fixture;
  if (!nf) return "";
  const where = nf.is_home === true ? " (H)" : nf.is_home === false ? " (A)" : "";
  const when = dayTime ? dayTime(nf.date) : "";
  return [`v ${nf.opponent || "?"}${where}`, when].filter(Boolean).join(" · ");
};

/**
 * "Reading 7.8 at home, Hull concede 6.2 away" — the two numbers the price is built from.
 *
 * BOTH SIDES, ALWAYS, OR NEITHER. These are the lambda's own inputs, averaged; printing
 * one of them would invite a reader to check it against a price that was built from both
 * and find a disagreement that is not there. Absent either, the line is dropped rather
 * than half-written.
 */
export const ratesOf = (row) => {
  const p = row?.projection;
  const nf = row?.next_fixture;
  const forR = num(p?.team_for);
  const agR = num(p?.opp_conceded);
  if (forR === null || agR === null) return "";
  const here = nf?.is_home === true ? "at home" : nf?.is_home === false ? "away" : "";
  const there = nf?.is_home === true ? "away" : nf?.is_home === false ? "at home" : "";
  const mine = `${row.name} ${forR.toFixed(1)}${here ? ` ${here}` : ""}`;
  const theirs = `${nf?.opponent || "they"} concede ${agR.toFixed(1)}`
               + `${there ? ` ${there}` : ""}`;
  return `${mine}, ${theirs}`;
};

/**
 * "fair 1.47" — or, where a real price has been typed in, that price and its edge.
 *
 * THE FAIR PRICE ALONE WAS HALF THE ORIGINAL COMPLAINT, and the complaint was right: a
 * model's own number with nothing to compare it against is not an edge, it is an opinion
 * wearing a decimal point. It stays because it is what a reader checks a book against —
 * but when `/prices` actually holds a price for this market, that is the line that matters
 * and it leads. `odds` in the database is manual-only, so this is the uncommon case.
 *
 * AND THE CAVEAT IS NOT REPEATED PER ROW. The first draft wrote "fair 1.52 — no book
 * price stored" on every line, which on a quiet day is the same eleven words eleven
 * times. The footer says it once; what the row needs is for the priced case to LOOK
 * different from the unpriced one, and `book 2.05 v fair 1.78` does that by itself.
 */
export const priceOf = (row) => {
  const p = row?.projection;
  const fair = num(p?.fair_odds);
  const book = num(p?.book_odds);
  const ev = num(p?.ev);
  if (book !== null) {
    const edge = ev === null ? "" : ` (${ev >= 0 ? "+" : ""}${ev.toFixed(0)}% EV)`;
    return `book ${book.toFixed(2)} v fair ${fair === null ? "?" : fair.toFixed(2)}${edge}`;
  }
  return fair === null ? "" : `fair ${fair.toFixed(2)}`;
};

/**
 * One row, four lines: the claim, the fixture, the reason, the link.
 *
 * FOUR SHORT LINES RATHER THAN TWO LONG ONES, because this is read on a phone. Joined
 * with separators onto one body line, a row ran past 130 characters and wrapped wherever
 * the handset felt like — mid-number, mid-name — and a wrapped row is harder to scan than
 * four deliberate ones. The split is also the row's own argument in order: what is
 * claimed, which game, why, and where to check it.
 */
export const digestRow = (row, { site = "", dayTime = null } = {}) => {
  const fid = row?.next_fixture?.fixture_id;
  const why = [ratesOf(row), priceOf(row)].filter(Boolean).join(" · ");
  const lines = [`${flagBullet(row?.league_id)} ${claimOf(row)}`];
  const fx = fixtureOf(row, dayTime);
  if (fx) lines.push(`   ${fx}`);
  if (why) lines.push(`   ${why}`);
  if (site && fid) lines.push(`   ↳ ${site}/fixture/${fid}`);
  return lines.join("\n");
};

const RULE = "━".repeat(3);

/**
 * The whole message.
 *
 * AN EMPTY BAND IS STILL A HEADING, and specifically the money band is. "Nothing in the
 * money band today" is the single most useful sentence this message can produce and it
 * only exists if the band is allowed to print itself empty — dropping it would make a day
 * with no 5+ runs look identical to a day the digest never ran, and the honest answer to
 * "what should I back today" is sometimes nothing. The other two bands are dropped when
 * empty, because they are context rather than the point.
 *
 * NOTHING AT ALL still sends, and says WHICH kind of nothing: no runs on the board, or
 * runs that all fell short of the floor. Those have different causes — a quiet calendar
 * and a hard filter — and silence cannot distinguish them.
 */
export function digestPost({ rows = [], site = "", dayLabel = "", dayTime = null,
                             minRun = DIGEST_MIN_RUN, caps = DIGEST_CAPS,
                             windowLabel = "" } = {}) {
  // `held` is deliberately not read here: each band prints its own overflow, and a second
  // total at the bottom was the same number a third time.
  const { bands, shown, qualified, skippedShort } = digestBands(rows, { minRun, caps });

  const head = `CORNER STREAKS${dayLabel ? ` · ${dayLabel}` : ""}`;
  const scope = windowLabel ? `, ${windowLabel}` : "";
  const out = [head];

  if (!qualified) {
    out.push(skippedShort
      ? `No run of ${minRun}+ on the board${scope}. ${skippedShort} shorter `
        + `${skippedShort === 1 ? "run" : "runs"} are running, which is not enough to post.`
      : `Nothing on the streak board${scope}.`);
    out.push("", "Streaks only — no chase board, no price list.");
    return out.join("\n");
  }

  out.push(`${shown} of ${qualified} runs of ${minRun}+${scope}. `
         + "Streaks only — no chase board, no price list.");

  bands.forEach(({ band, rows: mine, held: over }) => {
    if (!mine.length && band.id !== "money") return;
    out.push("", `${RULE} ${band.label.toUpperCase()} · ${band.verdict} ${RULE}`,
             bandRecord(band));
    if (band.note) out.push(band.note);
    if (!mine.length) {
      out.push("", "Nothing here today.");
      return;
    }
    out.push("");
    out.push(mine.map((r) => digestRow(r, { site, dayTime })).join("\n\n"));
    if (over) out.push(`+${over} more in this band on the site.`);
  });

  out.push("", BANDS_SOURCE);
  // THE ONE LINE THAT STOPS THE PRICES BEING MISREAD. `fair` is the model's own number and
  // the database holds a book price only where somebody typed one in, so most rows carry a
  // price with nothing on the other side of it. Said once at the bottom rather than on
  // every row, which is where the original "fair price with no context" came from.
  // SAID ONCE, AT THE BOTTOM. Every unpriced row used to carry "— no book price stored"
  // itself, which is the same sentence as many times as there are rows.
  out.push("Runs are live now. `fair` is the model's price; a book price appears only "
         + "where one has been typed into /prices.");
  return out.join("\n");
}
