// What a record card may claim, and what it must admit.
//
// WHY THIS IS NOT JUST A LAYOUT FILE. A results graphic is the single most over-claimed
// object in this whole industry, and the reason is structural: whoever makes it chooses
// which games go on it. So the choosing happens here, in a tested function, rather than in
// the drawing code where nobody would ever look at it again.
//
// THREE RULES, and each exists because breaking it is the normal thing to do:
//
//   1. A card that hides every miss is a lie told with true numbers. If the period
//      contains a loss, the strip has to show one — even when the most recent results
//      happen to be a clean sweep. See stripOf.
//   2. A rate without its denominator is unfalsifiable. "66%" is a claim nobody can check;
//      "31 of 47" is one anybody can. The denominator is never optional.
//   3. No profit figure, because this data cannot support one. Posted angles are stored
//      with a line and no price (see db.posted_angles), and the record is graded off a
//      snapshot that records the line too. Deriving units from that means inventing odds
//      after the fact — which is precisely what the picks ledger already refuses to do.
//      A units claim has to come from priced picks or not at all.

export const WIN = "win";
export const LOSS = "loss";
export const VOID = "void";

/** How many results fit on each card shape before they stop being legible. */
export const STRIP_MAX = { feed: 24, story: 32 };

/**
 * The strip of recent outcomes, newest last — and it always tells the truth about misses.
 *
 * A trim takes the most recent N, and the most recent N can happen to be all wins. The
 * headline would still say "31 of 47" and the picture underneath would say "unbeaten",
 * which is the impression people actually take away. So when the cut would hide every
 * loss in the period, the OLDEST kept win gives up its place to a real miss.
 */
export const stripOf = (rows = [], max = STRIP_MAX.feed) => {
  const graded = rows.filter((r) => r?.result === WIN || r?.result === LOSS
                                 || r?.result === VOID);
  const settled = graded.filter((r) => r.result !== VOID);
  if (graded.length <= max) return graded.map((r) => r.result);

  const kept = graded.slice(-max);
  const misses = settled.filter((r) => r.result === LOSS);
  if (misses.length && !kept.some((r) => r.result === LOSS)) {
    return [misses[0].result, ...kept.slice(1).map((r) => r.result)];
  }
  return kept.map((r) => r.result);
};

/**
 * The headline, and it is a fraction rather than a percentage.
 *
 * Returns null when nothing has settled. A card reading "0 of 0" or "—%" is a claim about
 * a record that does not exist yet, and the honest response to an empty period is not to
 * make the graphic at all.
 */
export const headlineOf = ({ landed = 0, settled = 0 } = {}) => {
  if (!settled) return null;
  return { big: `${landed} of ${settled}`,
           rate: Math.round((landed / settled) * 100),
           landed, settled };
};

// SPELLED OUT RATHER THAN LOCALE-FORMATTED. This card is drawn in two places — the
// browser, from the Results page, and headlessly in CI for the scheduled post — and
// toLocaleDateString does not agree between them: Node's ICU renders September as "Sept"
// where other builds give "Sep". A graphic whose date changes depending on which machine
// made it is one that cannot be checked against another copy of itself.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "1 Sep – 14 Sep", from the rows themselves rather than from today's date. */
export const periodOf = (rows = []) => {
  const dates = rows.map((r) => r?.kickoff).filter(Boolean)
    .map((d) => new Date(d)).filter((d) => !Number.isNaN(d.getTime()))
    .sort((a, b) => a - b);
  if (!dates.length) return "";
  const f = (d) => `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
  const [a, b] = [dates[0], dates[dates.length - 1]];
  return f(a) === f(b) ? f(a) : `${f(a)} – ${f(b)}`;
};

/**
 * Everything the card is allowed to say, assembled from one /api/results payload.
 *
 * `claimed` ONLY. The endpoint splits posted angles by a server-clock stamp taken when
 * they were logged: `recalled` is the ones added after kick-off. Both are published on the
 * site because hiding them would be worse, and only the first can count towards a rate —
 * an angle written down after the result is known is not a prediction.
 */
export const cardFrom = (results = {}, { shape = "feed" } = {}) => {
  const claimed = results?.posted?.claimed || {};
  const rows = claimed.rows || [];
  const head = headlineOf(claimed);
  if (!head) return null;
  return {
    ...head,
    strip: stripOf(rows, STRIP_MAX[shape] ?? STRIP_MAX.feed),
    voided: claimed.voided || 0,
    pending: claimed.pending || 0,
    period: periodOf(rows),
    // THE DIFFERENTIATOR, and the only line on the card that is an argument rather than a
    // number. A streak row stops existing the moment it breaks, so a record built from the
    // live board counts survivors and reports a near-perfect week every week. Grading off a
    // snapshot frozen before kick-off is what makes the fraction above mean anything, and
    // almost nobody else posting these can say it.
    basis: "Graded from a snapshot frozen before kick-off",
    // Required on any gambling creative, and independently just better marketing: a claim
    // hedged by its own limits reads as real, and certainty reads as a scam.
    legal: "18+ · begambleaware.org · Past results do not predict future ones",
  };
};

// ----------------------------- One day -----------------------------
//
// "Yesterday: 4 from 4" is a different graphic from the monthly record, and a more
// dangerous one. A month card is whatever the month was; a DAY card is chosen, and the day
// that gets chosen is the good one. Nobody posts their 1-from-5.
//
// SO THE RUNNING RECORD IS NOT OPTIONAL ON IT. Every day card carries the month beside the
// day — "4 from 4 yesterday · 34 of 45 this month" — and that single addition is what turns
// a cherry-picked graphic into an honest one. It is also the only version of this post
// anyone else in the space cannot copy, because copying it means showing their month.

/** Local YYYY-MM-DD for an ISO timestamp, so "yesterday" means the day the game kicked off. */
const dayKey = (iso) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
};

/** The days that have at least one settled pick, newest first. Used to offer a choice. */
export const settledDays = (results = {}) => {
  const rows = results?.posted?.claimed?.rows || [];
  const days = new Set();
  rows.forEach((r) => {
    if (r?.result === WIN || r?.result === LOSS) days.add(dayKey(r.kickoff));
  });
  return [...days].filter(Boolean).sort().reverse();
};

/**
 * Units for a set of rows, or null — and the null is the point.
 *
 * A win at an unknown price has no computable return. Totalling only the rows that HAVE a
 * price would publish a figure over an unstated subset, which is worse than publishing
 * none: the number looks complete and is not. So this answers null unless every settled
 * row on the day carries a price, and reports how many did not.
 */
export const unitsFor = (rows = []) => {
  const settled = rows.filter((r) => r?.result === WIN || r?.result === LOSS);
  if (!settled.length) return { units: null, unpriced: 0, whole: false };
  const unpriced = settled.filter((r) => !(Number(r.price) > 1)).length;
  if (unpriced) return { units: null, unpriced, whole: false };
  const units = settled.reduce((n, r) => {
    const stake = Number(r.stake) > 0 ? Number(r.stake) : 1;
    return n + (r.result === WIN ? (Number(r.price) - 1) * stake : -stake);
  }, 0);
  return { units: Math.round(units * 100) / 100, unpriced: 0, whole: true };
};

/**
 * One day's card. `date` is a YYYY-MM-DD key from settledDays.
 *
 * Returns null when that day settled nothing — the same refusal the month card makes, for
 * the same reason.
 */
export const dayCardFrom = (results = {}, { date, shape = "feed" } = {}) => {
  const all = results?.posted?.claimed?.rows || [];
  const rows = all.filter((r) => dayKey(r.kickoff) === date);
  const settled = rows.filter((r) => r?.result === WIN || r?.result === LOSS);
  if (!settled.length) return null;

  const landed = settled.filter((r) => r.result === WIN).length;
  const { units, unpriced } = unitsFor(rows);
  const month = headlineOf(results?.posted?.claimed || {});

  return {
    big: `${landed} from ${settled.length}`,
    clean: landed === settled.length,
    strip: stripOf(rows, STRIP_MAX[shape] ?? STRIP_MAX.feed),
    picks: rows.filter((r) => r.result !== "pending").map((r) => ({
      name: r.name, line: r.line_label || "", result: r.result,
      price: Number(r.price) > 1 ? Number(r.price) : null,
    })),
    units,
    // Said outright when a units figure cannot be published, rather than the line simply
    // being absent — an absent number reads as a bad day.
    unitsNote: units == null && unpriced
      ? `${unpriced} of ${settled.length} logged without a price`
      : "",
    date,
    // THE HONESTY MECHANISM. Not decoration and not optional — see the note above.
    context: month ? `${month.big} this month` : "",
    voided: rows.filter((r) => r.result === VOID).length,
    legal: "18+ · begambleaware.org · Past results do not predict future ones",
  };
};
