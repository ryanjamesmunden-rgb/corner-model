// Reading the calibration record on the page: what it says, and what it cannot say.
//
// THE RISK THIS FILE EXISTS TO MANAGE. A calibration table is the most persuasive thing
// this site can show a stranger and therefore the easiest to overclaim with. Three rows of
// percentages under a green tick reads as proof, and on a hundred claims from twelve
// fixtures it is not proof of anything. Everything here is built so the page cannot show
// the number without the things that qualify it.
//
// THE CAVEATS ARE COMPUTED, NOT WRITTEN INTO THE JSX, for one reason: a sentence typed
// into a component is a sentence that stays true until the data changes and then silently
// does not. "Most of these were derived" has to stop appearing when they stop being
// derived, and only something reading the payload can know that.

/** Below this a band cannot carry a conclusion; the server marks rows `thin` too. */
export const READABLE_BAND = 25;

/**
 * How confident the page is allowed to sound.
 *
 * THREE TONES AND THE DEFAULT IS "unknown". A record with nothing settled in it is not
 * neutral-good, it is unknown, and a page that renders an empty table in a calm grey is
 * making a claim by omission.
 */
export const verdictTone = (summary) => {
  const bands = (summary?.bands || []).filter((b) => !b.thin && b.claims);
  if (!bands.length) return "unknown";
  const off = bands.filter((b) => !b.calibrated);
  if (!off.length) return "holding";
  return "off";
};

/** Is there enough here to put a headline on at all? */
export const hasEnough = (summary) =>
  (summary?.bands || []).some((b) => !b.thin && b.claims);

/**
 * The bands worth drawing, newest concern first — which is to say: in probability order.
 *
 * EVERY BAND IS KEPT, INCLUDING THE EMPTY AND THE THIN ONES. Dropping them would make the
 * table a list of the bands that happened to fill up, which is the same fault as a results
 * page that hides its losing months — and the empty high bands are themselves information,
 * because they say the model rarely claims to be that sure.
 */
export const bandRows = (summary) => (summary?.bands || []).map((b) => ({
  ...b,
  readable: !b.thin && b.claims > 0,
  // The gap a reader is actually looking for, phrased so a positive number is always good
  // news for the model's honesty in the same direction.
  miss: b.residual === null || b.residual === undefined ? null : b.residual,
}));

/**
 * Everything true about this record that weakens it, as sentences.
 *
 * ORDERED BY HOW MUCH THEY WEAKEN IT, because the list is long enough that a reader will
 * stop partway and the first one should be the one that matters most.
 */
export function caveats(summary) {
  const out = [];
  if (!summary) return out;
  const o = summary.overall || {};
  const claims = o.claims || 0;
  const fixtures = o.fixtures || 0;

  // FIRST, ALWAYS, WHEN IT APPLIES. Claims inside a fixture are not independent — six
  // team lines on one side all land together when a game goes to twelve corners — so the
  // claim count overstates the sample, and it is the number a reader's eye goes to.
  if (claims && fixtures && claims > fixtures) {
    out.push(`${claims.toLocaleString()} lines from ${fixtures.toLocaleString()} `
      + `fixtures. Lines on the same game rise and fall together, so the real sample is `
      + `nearer the ${fixtures.toLocaleString()} than the ${claims.toLocaleString()}.`);
  }
  const derived = summary.derived_claims || 0;
  if (derived) {
    // TWO WHOLE SENTENCES PER CASE, not one with four ternaries spliced into it. The
    // first version built this inline and produced "Every probabilities one is derived
    // from…" on the page — grammatical nonsense in the caveat whose whole job is to be
    // believed, which is the one place broken English costs the most.
    const all = derived >= claims;
    out.push((all
      ? "Every one of these probabilities is derived from the expected corners "
      : `${Math.round(100 * derived / claims)}% of these probabilities are derived `
        + "from the expected corners ")
      + "frozen before kick-off, rather than stored at the time. The forecast knew "
      + "nothing about the result either way, but it is today's distribution applied "
      + "to it.");
  }
  if (summary.ungraded) {
    out.push(`${summary.ungraded.toLocaleString()} frozen fixtures have no result yet and `
      + `are left out rather than counted as misses.`);
  }
  const thin = (summary.bands || []).filter((b) => b.thin && b.claims).length;
  if (thin) {
    out.push(`${thin} band${thin === 1 ? " has" : "s have"} fewer than `
      + `${summary.min_band ?? READABLE_BAND} lines behind `
      + `${thin === 1 ? "it" : "them"} and cannot be read yet. `
      + `${thin === 1 ? "It is" : "They are"} shown anyway.`);
  }
  return out;
}

/**
 * The one-line headline.
 *
 * TAKEN FROM THE SERVER'S OWN VERDICT where there is one, rather than recomputed here. Two
 * implementations of "is this model honest" on one codebase is two answers, and the one
 * that disagreed would be whichever was edited second.
 */
export const headline = (summary) => {
  if (!summary) return "";
  if (!hasEnough(summary)) {
    return "Not enough settled fixtures yet to say whether the percentages hold up.";
  }
  return summary.verdict || "";
};

/** "65-70%" → the plain-English version a first-time reader needs. */
export const bandSentence = (band) => {
  if (!band || !band.claims || band.actual === null || band.actual === undefined) return "";
  return `When the model said about ${band.promised}%, it happened `
       + `${band.actual}% of the time (${band.claims.toLocaleString()} lines, `
       + `${band.fixtures.toLocaleString()} fixtures).`;
};
