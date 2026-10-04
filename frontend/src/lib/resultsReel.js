// The week's results as ONE clip, instead of one card per pick.
//
// WHY A REEL AND NOT TEN GRAPHICS. Ten stills is ten exports, ten uploads and ten chances
// to quietly drop the one that lost. A single clip that steps through every settled pick
// in the period is less work AND harder to shade: the rows come off one list, in kick-off
// order, and the tally at the end counts exactly what went past.
//
// A WEEK IS A CHOSEN PERIOD, and recordCard.js already wrote the rule for that hazard:
//
//   "A month card is whatever the month was; a DAY card is chosen, and the day that gets
//    chosen is the good one. Nobody posts their 1-from-5. SO THE RUNNING RECORD IS NOT
//    OPTIONAL ON IT."
//
// Everything in that paragraph is true of a week. "Another week of 10/10" is exactly the
// graphic somebody posts in a good week and not in a bad one, so the overall record rides
// on the end card beside it — not as a disclaimer, as the thing that makes the week worth
// believing. `context` is therefore built here and is not optional.
//
// NOTHING SETTLED IS NOT A REEL. Like every other card here, this returns null rather than
// drawing an empty frame, because a clip that says "0 of 0" is a claim about a record that
// does not exist.
import { WIN, LOSS, VOID, headlineOf, periodOf, unitsFor } from "./recordCard.js";

export { WIN, LOSS, VOID };

/** Beyond this the rows go past too fast to read on a phone. */
export const MAX_REEL_ROWS = 14;
/** Fewer than this is a card, not a clip — one result does not need an animation. */
export const MIN_REEL_ROWS = 2;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const ms = (iso) => {
  const t = new Date(iso || "").getTime();
  return Number.isFinite(t) ? t : 0;
};

/** "8 corners" — what actually happened, which is the half a result card is FOR. */
export const valueText = (row = {}) => {
  const v = num(row.value);
  return v === null ? "" : `${v} corner${v === 1 ? "" : "s"}`;
};

/**
 * One settled pick, reduced to what a frame shows.
 *
 * A VOID IS KEPT AND MARKED, not dropped. An exact-line push is a real outcome that
 * happened to the money, and a reel that silently skipped them would show a cleaner run of
 * ticks than the week actually produced.
 */
export const reelRow = (r = {}) => ({
  name: r.name || "",
  line: r.line_label || "",
  result: r.result,
  won: r.result === WIN,
  lost: r.result === LOSS,
  voided: r.result === VOID,
  value: valueText(r),
  // THE TWO NUMBERS THE BAR IS DRAWN FROM, kept as numbers. `line_label` is "6+" or
  // "under 9" — right for a caption and useless for arithmetic — and `value` above is
  // already prose. A renderer that had to parse either back into a number would be one
  // bad regex away from drawing a bar at the wrong place on a result that is correct.
  count: num(r.value),
  lineValue: num(r.line),
  direction: r.direction === "under" ? "under" : "over",
  price: num(r.price) > 1 ? num(r.price) : null,
  kickoff: r.kickoff || null,
  key: `${r.name}-${r.line_label}-${r.kickoff}`,
});

/**
 * The reel, from one /api/results payload.
 *
 * `claimed` ONLY, for the reason that endpoint states: `recalled` rows were logged after
 * kick-off, and an angle written down once the result is known is not a prediction. Both
 * are published on the site; only one may be animated into a highlight reel.
 */
export const reelFrom = (results = {}, { days = 7, now = Date.now(),
                                          max = MAX_REEL_ROWS, next = null,
                                          join = "" } = {}) => {
  const claimed = results?.posted?.claimed || {};
  const since = now - days * 86400000;
  const inWindow = (claimed.rows || []).filter((r) => {
    const t = ms(r?.kickoff);
    return t >= since && t <= now;
  });
  const settled = inWindow.filter((r) => r.result === WIN || r.result === LOSS
                                         || r.result === VOID);
  const graded = settled.filter((r) => r.result !== VOID);
  if (graded.length < MIN_REEL_ROWS) return null;

  // KICK-OFF ORDER, so the clip replays the week in the order it was lived. Sorting by
  // outcome would group the winners, which is the same cherry-pick done with the whole set
  // present.
  const ordered = [...settled].sort((a, b) => ms(a.kickoff) - ms(b.kickoff));
  // THE TRIM TAKES THE OLDEST OFF, NOT THE LOSERS. If the period will not fit, the clip
  // says so in `more` rather than quietly becoming a different, better week.
  const rows = ordered.slice(-Math.max(MIN_REEL_ROWS, max)).map(reelRow);
  const landed = graded.filter((r) => r.result === WIN).length;
  const { units, unpriced } = unitsFor(settled);
  const overall = headlineOf(claimed);

  return {
    rows,
    n: rows.length,
    more: Math.max(0, ordered.length - rows.length),
    landed,
    settled: graded.length,
    big: `${landed} from ${graded.length}`,
    clean: landed === graded.length,
    voided: settled.filter((r) => r.result === VOID).length,
    period: periodOf(settled),
    units,
    unitsNote: units == null && unpriced
      ? `${unpriced} of ${graded.length} logged without a price`
      : "",
    // THE HONESTY MECHANISM, not decoration. See the note at the top of this file.
    context: overall ? `${overall.big} overall` : "",
    basis: "Graded from a snapshot frozen before kick-off",
    legal: "18+ · begambleaware.org · Past results do not predict future ones",
    // Both optional. No fixtures fetched, or no join link configured, and the clip simply
    // ends on the tally — which is what it did before and is still a complete post.
    next,
    join: join || "",
  };
};

/**
 * What is coming, as a tease rather than a team sheet.
 *
 * THE CALLS ARE THE PRODUCT, AND THIS CLIP IS FREE. /value-board is members-only for a
 * stated reason — "it is not a list of teams in form, it is a ranked list of LIVE PRICES
 * THE MODEL DISAGREES WITH — the finished product" — and the fixture stories blur the
 * model's price for the same one. An end card that listed next weekend's lines would hand
 * over the thing the channel sells, in the post whose job is to make people want it.
 *
 * So this carries FIXTURES and SCALE: how many games the model has projections on, across
 * how many leagues, and the few with the most corners expected. Every one of those is a
 * fact about the fixture list. None of them is a bet.
 */
export const MAX_NEXT_GAMES = 3;

export const nextFrom = (fixtures = [], { max = MAX_NEXT_GAMES } = {}) => {
  const rows = (fixtures || []).filter((f) => f && f.home && f.away);
  if (!rows.length) return null;
  const leagues = new Set(rows.map((f) => f.league_name).filter(Boolean));
  // Ordered by projected total, which is a property of the fixture rather than a
  // selection among them — "the biggest corner games on the card", not "our picks".
  const games = [...rows]
    .sort((a, b) => (Number(b.lambda_total) || 0) - (Number(a.lambda_total) || 0))
    .slice(0, Math.max(1, max))
    .map((f) => ({ home: f.home, away: f.away, league: f.league_name || "" }));
  return {
    count: rows.length,
    leagues: leagues.size,
    games,
    when: periodOf(rows.map((f) => ({ kickoff: f.date }))),
  };
};

/**
 * How much of the reel is on screen at `progress` (0..1).
 *
 * THE LAST BEAT IS THE TALLY, and it gets a share of the clip rather than appearing in the
 * final frame. A number that arrives on the last frame is a number nobody reads: the
 * render holds on it afterwards, and this is what hands it something to hold.
 */
export const TALLY_SHARE = 0.26;
/** The end card gets its own beat, and takes it from the rows rather than from the tally. */
export const NEXT_SHARE = 0.22;

export const reelAt = (reel = null, progress = 0) => {
  if (!reel || !reel.n) return { shown: 0, tally: 0, next: 0, growth: 1 };
  const p = Math.max(0, Math.min(1, Number(progress) || 0));
  const hasNext = Boolean(reel.next || reel.join);
  const nextShare = hasNext ? NEXT_SHARE : 0;
  const tallyEnd = 1 - nextShare;
  const rowsEnd = tallyEnd - TALLY_SHARE;
  if (p >= tallyEnd) {
    // The tally stays at full once the end card starts: it is still the frame underneath,
    // and a number that fades out as the advert arrives reads as a number being taken away.
    // THE LAST FRAME IS PINNED RATHER THAN DIVIDED. (1 - 0.78) / 0.22 is 0.9999999999999999
    // in binary floating point, so the end card finished a hair short of full on the one
    // frame that matters most: the held frame of the video, and the still.
    return { shown: reel.n, tally: 1, growth: 1,
             next: nextShare ? (p >= 1 ? 1 : Math.min(1, (p - tallyEnd) / nextShare)) : 0 };
  }
  if (p >= rowsEnd) {
    return { shown: reel.n, tally: Math.min(1, (p - rowsEnd) / TALLY_SHARE),
             next: 0, growth: 1 };
  }
  const slot = (p / rowsEnd) * reel.n;
  // `growth` is how far the NEWEST row's bar has run out to its finishing count — the
  // whole point of the bar is watching it pass the line, and a bar that arrived already
  // full would show the result without ever showing the margin. Every row behind it sits
  // at 1: a list where every line is still moving is a list nobody can read mid-clip.
  //
  // It runs at twice the pace of the row slot so the bar settles before the next row
  // lands, rather than being interrupted halfway by its successor.
  return {
    shown: Math.min(reel.n, Math.floor(slot) + 1),
    tally: 0,
    next: 0,
    growth: Math.max(0, Math.min(1, (slot - Math.floor(slot)) * 2)),
  };
};

/** The caption that goes with the clip. The video is the hook; this is the claim. */
export const reelPost = ({ reel = null, site = "", heading = "" } = {}) => {
  if (!reel) return "";
  const title = heading || `${reel.big} this week`;
  const lines = [title, ""];
  reel.rows.forEach((r) => {
    const mark = r.won ? "✅" : r.lost ? "❌" : "➖";
    const got = r.value ? ` — ${r.value}` : "";
    lines.push(`${r.name} ${r.line}${got} ${mark}`);
  });
  if (reel.more) {
    lines.push(`+${reel.more} more in the period`);
  }
  lines.push("");
  if (reel.voided) lines.push(`${reel.voided} void (exact line — stake back)`);
  if (reel.units != null) lines.push(`${reel.units > 0 ? "+" : ""}${reel.units}u`);
  else if (reel.unitsNote) lines.push(reel.unitsNote);
  if (reel.context) lines.push(reel.context);
  lines.push(reel.basis);
  if (reel.next) {
    lines.push("");
    lines.push(`Next up: ${reel.next.count} games across ${reel.next.leagues} leagues`
               + (reel.next.when ? `, ${reel.next.when}` : ""));
  }
  if (reel.join) {
    // The lines themselves are not in the caption either, for the reason at nextFrom.
    lines.push(`Calls go out in the channel before kick-off — ${reel.join}`);
  }
  if (site) {
    lines.push("");
    lines.push(site);
  }
  return lines.filter((l, i, a) => !(l === "" && a[i - 1] === "")).join("\n");
};
