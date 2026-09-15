// What the angle panel is allowed to say, kept out of the component.
//
// THE WHOLE RISK IN THIS FEATURE IS A SENTENCE, not a layout. "88% strike rate" and "7 of
// 8 so far" describe the same eight games; one is a track record and the other is a small
// sample, and which one appears is decided by a boolean that is easy to loosen inside JSX
// on a quiet afternoon. So the decision lives here, where it can be tested without a DOM,
// and the component renders whatever this returns.
//
// The backend has already gated the rate (see angle_of_day.gate — MIN_SAMPLE). This does
// not re-derive that judgement; it turns it into words, and refuses to invent a percentage
// the server withheld.

/**
 * A graded tally -> the line the panel prints.
 *
 * `strong` is the big number, or null when there is no number honest enough to be big.
 * That is the point of it: a panel with nothing worth shouting does not shout.
 */
export function statedRecord(tally) {
  if (!tally) return null;
  const settled = tally.settled || 0;
  const landed = tally.landed || 0;
  const pending = tally.pending || 0;
  const voided = tally.voided || 0;

  // NOTHING SETTLED IS NOT NOUGHT PER CENT. A panel that prints 0% before a single game
  // has been played is claiming a record it has not got, in the worst possible direction.
  if (!settled) {
    return {
      strong: null,
      text: pending
        ? `${pending} still to play — nothing has settled yet`
        : "Nothing has settled yet",
      pending,
      voided,
    };
  }

  if (tally.show_rate && tally.hit_rate != null) {
    return {
      strong: `${tally.hit_rate}%`,
      // THE DENOMINATOR RIDES WITH THE RATE, ALWAYS. A percentage without the count it
      // came from is an advert, and this panel sits directly above a list of bets.
      text: `landed — ${landed} of ${settled} settled`,
      pending,
      voided,
    };
  }

  // Below the floor: the raw fraction, and a plain reason it is not a percentage. Saying
  // why matters — a bare "7 of 8" invites the reader to do the division themselves and
  // arrive at exactly the number that was withheld, without the caveat attached to it.
  return {
    strong: null,
    text: `${landed} of ${settled} landed so far`,
    caveat: `Too few settled to quote a strike rate — ${settled} of the ${tally.min_sample || 20} needed.`,
    pending,
    voided,
  };
}

// What a dead day says. Written out rather than assembled, because each of these is a
// different admission and a generic "no angles today" would flatten three facts into one.
const DEAD = {
  stale: {
    title: "Not publishing today",
    body: "The match data is older than this panel will make a call on. An angle off stale form is still an angle, and someone would back it.",
  },
  no_fixtures: {
    title: "Nothing on today",
    body: "No fixtures in the leagues this model covers. Back tomorrow.",
  },
  no_qualifier: {
    title: "No angle today",
    body: "There is football on and none of it clears the bar. A team only appears here having cleared its line in all five of its last five — today nobody has.",
  },
};

export function deadMessage(payload) {
  if (!payload?.dead) return null;
  const copy = DEAD[payload.reason] || {
    title: "No angle today",
    body: "Nothing clears the bar.",
  };
  return { ...copy, reason: payload.reason };
}

/**
 * Split the list into the one being led with and the rest.
 *
 * The top angle is not a different KIND of pick — it is the same rule's first row — so it
 * is separated for emphasis and never relabelled as something stronger than it is.
 */
export function splitAngles(payload) {
  const angles = payload?.angles || [];
  return { top: angles[0] || null, rest: angles.slice(1) };
}

/** "Middlesbrough 6+ team corners" — what the angle actually claims, in one line. */
export function angleLabel(angle) {
  if (!angle) return "";
  const line = angle.line_label || (angle.line != null ? `${angle.line}+` : "");
  return [angle.name, line].filter(Boolean).join(" ");
}

/** "5 of 5 · 4 in a row" — the run behind it, which is the entire reason it is here. */
export function runLabel(angle) {
  if (!angle) return "";
  const settled = angle.settled ?? angle.window;
  const bits = [];
  if (angle.hits != null && settled != null) bits.push(`${angle.hits} of ${settled}`);
  if (angle.voids) bits.push(`${angle.voids} push`);
  const len = angle.streak?.length;
  if (len) bits.push(`${len} in a row`);
  return bits.join(" · ");
}

/**
 * Does the panel have anything to draw at all?
 *
 * A dead day still draws — the refusal IS the content, and hiding the panel on a quiet day
 * would mean the only days anyone sees it are the days it makes a call, which is how a
 * reader concludes the bar never turns anything away.
 */
export function hasPanel(payload) {
  return Boolean(payload && (payload.dead || (payload.angles || []).length));
}
