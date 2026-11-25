/**
 * The week card: one fixture, both sides, the bet in red and the record in green.
 *
 * THE TWO COLOURS ARE THE WHOLE IDEA, and they come straight off the paper version: the
 * PRICE is what you are being offered and the RECORD is why you would take it. Keeping
 * them visually separate stops the eye reading "6+ at 1.73, 9/10" as one claim, because
 * it is two — a bookmaker's number and a history — and only one of them is a fact about
 * the future.
 *
 * WHICH IS WHY `run_matches_pick` IS NOT DECORATION. A side can have a 5+ run of nine in
 * ten and a 6+ price. Printed together with no comment that reads as a 6+ record. The
 * backend already prefers the rung at the run's own line; when it cannot have it, the
 * green half has to say which line it is actually a record of.
 *
 * NOTHING HERE RANKS ANYTHING. The card is a diary — kick-off order, every game with
 * something on it — and the boards are where ranking belongs.
 */

const BOARD_LABEL = {
  quick_scan: "Quick Scan",
  streaks: "Streaks",
  perfect_games: "Perfect Games",
};

/** The verdicts game_state can return, in the words the card uses for them. */
export const STATE_LABEL = {
  chase_spot: "Chase spot",
  caution: "Caution",
  avoid: "Avoid",
  neutral: "Neutral",
};

/**
 * How a verdict is drawn. `chase_spot` is the only one that argues FOR the bet, and even
 * that one is unmeasured — see game_state.py — so nothing here is coloured like a result.
 */
export const STATE_TONE = {
  chase_spot: "text-emerald-600 dark:text-emerald-400",
  caution: "text-amber-600 dark:text-amber-400",
  avoid: "text-rose-600 dark:text-rose-400",
  neutral: "text-muted-foreground",
};

export const boardLabel = (id) => BOARD_LABEL[id] || id;

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** "6+" — the line as it is bet, from whichever of the two shapes carries it. */
export const lineLabel = (pick) => {
  if (!pick) return "";
  if (pick.line_label) return pick.line_label;
  const line = num(pick.line);
  return line === null ? "" : `${line}+`;
};

/**
 * The red half: the price and what it is worth.
 *
 * Returns `{ odds, ev, fair, quoted }`. `quoted` false means no bookmaker has priced it
 * and `odds` is the MODEL's number — which is a different kind of thing and has to be
 * labelled as one, never shown as a price you can take.
 */
export const priceOf = (pick) => {
  if (!pick) return null;
  const book = num(pick.book_odds);
  const fair = num(pick.fair_odds);
  if (book !== null) {
    return { odds: book, ev: num(pick.ev), fair, quoted: true };
  }
  if (fair === null) return null;
  return { odds: fair, ev: null, fair, quoted: false };
};

/**
 * The green half: the record standing behind the bet.
 *
 * `atPick` false means this run is a record at a DIFFERENT line from the one priced
 * above it, and `line` says which — the caller must print it rather than imply agreement.
 */
export const recordOf = (side) => {
  const run = side?.run;
  if (!run) return null;
  const hits = num(run.hits);
  const settled = num(run.settled);
  if (hits === null || !settled) return null;
  return {
    hits,
    settled,
    floor: num(run.floor),
    length: num(run.length) || 0,
    line: num(run.line),
    lineLabel: run.line_label || (num(run.line) !== null ? `${run.line}+` : ""),
    atPick: Boolean(side.run_matches_pick),
  };
};

/**
 * The sentence under a side: what the record says, and at which line.
 *
 * "9 of 10, lowest 4" when the run and the bet agree.
 * "3+ · 4 of 5, lowest 1" when they do not — the line named first, so the figure can
 * never be read as a record of the bet printed beside it.
 *
 * THE DISTINCTION IS CARRIED BY COLOUR, NOT BY A SENTENCE. The first version appended
 * "— not this line" in the same green, which was right about the fact and wrong about
 * the weight: on a real day most runs are at a different line from the best price, so
 * every row carried the caveat and the green stopped meaning anything. Green now means
 * exactly one thing — this record is a record of THIS bet — and a run at another line
 * is drawn muted, with its own line in front of it. `recordOf(...).atPick` is what the
 * caller switches on.
 */
export const recordText = (side) => {
  const rec = recordOf(side);
  if (!rec) return "";
  const floor = rec.floor === null ? "" : `, lowest ${rec.floor}`;
  const run = `${rec.hits} of ${rec.settled}${floor}`;
  return rec.atPick ? run : `${rec.lineLabel} · ${run}`;
};

/**
 * Whether a card is worth opening, and why, in one short phrase.
 *
 * NOT A SCORE. Two sides with runs is not twice as good as one, and a card with a big
 * edge on it is not a better card — it is a card with a bigger number on it, which the
 * boards already rank by.
 */
export const cardNote = (card) => {
  if (!card) return "";
  if (card.status === "no_price") return "No price yet — research game";
  const runs = num(card.run_count) || 0;
  if (runs === 2) return "Both sides on a run";
  if (runs === 1) return "One side on a run";
  return "Priced, no run behind either side";
};

/** The three slots on a card, in the order the paper version writes them. */
export const slotsOf = (card) => [
  { key: "home", side: card?.home, venue: "H" },
  { key: "away", side: card?.away, venue: "A" },
];

/**
 * Every warning on the card, each said once.
 *
 * Both sides raise "the opponent's venue record is thin" about each other, so the same
 * sentence can arrive twice on one fixture; a card that says it twice reads as two
 * separate problems.
 */
export const warningsOf = (card) => {
  const seen = new Set();
  const out = [];
  for (const { side } of slotsOf(card)) {
    for (const w of side?.warnings || []) {
      if (typeof w === "string" && !seen.has(w)) {
        seen.add(w);
        out.push(w);
      }
    }
  }
  return out;
};

/** The next `count` UK days, as { value, label, short } — the strip above the card. */
export const dayStrip = (now = new Date(), count = 7) => {
  const out = [];
  for (let i = 0; i < count; i += 1) {
    const d = new Date(now.getTime() + i * 86400000);
    const value = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(d);
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/London", weekday: "short", day: "numeric", month: "short",
    }).formatToParts(d);
    const get = (t) => parts.find((p) => p.type === t)?.value || "";
    out.push({
      value,
      short: i === 0 ? "Today" : i === 1 ? "Tomorrow" : get("weekday"),
      label: `${get("weekday")} ${get("day")} ${get("month")}`,
    });
  }
  return out;
};
