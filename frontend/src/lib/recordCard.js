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
