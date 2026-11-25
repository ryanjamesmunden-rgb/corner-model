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
 * The price and what it is worth.
 *
 * IT USED TO BE DRAWN RED, which was wrong on this site specifically. Red already means
 * one thing here and means it everywhere else — `PICK_RESULT.lost` is "missed",
 * `RESULT_TONE.lost` is "missed", `STATE_TONE.avoid` is "avoid" — so a red number above
 * a game that has not kicked off read as a loss that had already happened. The price is
 * now the plain foreground at a size nothing else on the row has: weight carries the
 * headline, and colour is left to mean an outcome and nothing else.
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

/** A record this strong over the window is what "it keeps landing" means here. */
export const BACKED_RATE = 0.8;

/**
 * Whether the evidence on this side argues FOR the price beside it, against it, or
 * neither — the traffic light the price is drawn in.
 *
 * WHY THE PRICE AND NOT A BADGE. The price is the thing the eye lands on, so it is the
 * thing that has to carry whether the bet is backed. A card that prints 13.00 in the
 * same weight as 1.73 is telling you the two are the same kind of claim, and they are
 * not: one is a line this side has cleared four times in five, the other is a line its
 * record never reaches.
 *
 * Returns `{ tone, why }`. `tone` is "backed", "warning" or "plain".
 *
 * BACKED needs the record to cover THIS bet and to be a record worth the name: the run's
 * line at or above the one priced (a side that got 5+ four times in five also got 4+
 * four times in five — a record reaches down, never up), and at least four of its last
 * five.
 *
 * WARNING is the louder half and the reason this exists. Either:
 *   - the bet sits ABOVE the run's line, so the record printed under it is a record of a
 *     different bet — the "8+ at 13.00 under a 4+ run" case
 *   - the opponent gives up fewer corners than the line asks for, which no amount of
 *     this team's form can answer: the run is five games against five other opponents
 *
 * A SIDE WITH NO RUN IS PLAIN, NOT RED. Red has to mean the evidence points the other
 * way, and no evidence is not evidence against — most sides on a card have no run, so
 * colouring them all would put the board back where it started, with red everywhere and
 * meaning nothing. It simply does not earn green.
 *
 * PLAIN is everything else, and most rows are plain. If a third colour meant something
 * too, the two that do mean something would stop being noticeable.
 */
export const priceTone = (side) => {
  const pick = side?.pick;
  const line = num(pick?.line);
  if (!pick || line === null || num(pick.book_odds) === null) {
    return { tone: "plain", why: "" };
  }
  const run = side?.run;
  const runLine = num(run?.line);
  const hits = num(run?.hits);
  const settled = num(run?.settled);
  const opp = num(side?.opp_conceded);

  if (opp !== null && opp < line && runLine !== null && runLine < line) {
    return { tone: "warning",
             why: `The run is at ${runLine}+ and the opponent concedes ${opp} a game — `
                  + `neither reaches the ${line} this bet needs` };
  }
  if (runLine === null || hits === null || !settled) {
    return opp !== null && opp < line
      ? { tone: "warning",
          why: `Opponent concedes ${opp} a game, under the ${line} this bet needs` }
      : { tone: "plain", why: "" };
  }
  if (runLine < line) {
    return { tone: "warning",
             why: `The run is at ${runLine}+. This bet is ${line}+ — the record below `
                  + "does not reach it" };
  }
  if (opp !== null && opp < line) {
    return { tone: "warning",
             why: `Opponent concedes ${opp} a game, under the ${line} this bet needs` };
  }
  if (hits / settled >= BACKED_RATE) {
    return { tone: "backed", why: `${hits} of the last ${settled} at ${runLine}+` };
  }
  return { tone: "plain", why: "" };
};

/**
 * How many settled instances a line needs before "it has landed consistently" is a
 * sentence worth printing. Two is already a thin claim and is printed WITH its
 * denominator for exactly that reason — "all 2" cannot be mistaken for a long record.
 */
export const VALUE_MIN_GAMES = 2;

/**
 * The case for taking a price: this same line has come in every time it was priced, and
 * what you are being offered now is longer than any price it came in at.
 *
 * WHY THIS AND NOT THE MODEL'S EDGE. The edge is an opinion — a probability the model
 * worked out, multiplied by a price — and the biggest edge on a board is very often the
 * model's worst error. This is two facts and a subtraction: the line was offered at
 * 1.62 and 1.70 and landed both times, and today it is 1.73. Nothing is predicted. A
 * reader can check every number in it against the games.
 *
 * EVERY TIME, NOT MOST. "Landed consistently" is the thing being claimed, so one miss in
 * the window ends it; a 2-of-3 record is still printed, just as the ordinary history
 * sentence rather than as an argument for the bet. A push is left out of the count
 * entirely — it is neither a hit nor a miss and would quietly pad the denominator.
 *
 * Returns null unless the whole case holds, so the caller has one thing to test.
 */
export const priceValue = (pick) => {
  const now = num(pick?.book_odds);
  const settled = (pick?.history?.games || [])
    .filter((g) => g?.result && g.result !== "void");
  if (now === null || settled.length < VALUE_MIN_GAMES) return null;
  if (settled.some((g) => g.result !== "won")) return null;
  const prices = settled.map((g) => num(g.book_odds)).filter((p) => p !== null);
  if (prices.length !== settled.length) return null;
  const best = Math.max(...prices);
  return now > best ? { games: settled.length, best, now } : null;
};

/** "Landed all 3 · best was 1.70, now 1.73" — the case above, in one line. */
export const valueText = (pick) => {
  const v = priceValue(pick);
  return v ? `Landed all ${v.games} · best was ${v.best.toFixed(2)}, now ${v.now.toFixed(2)}`
    : null;
};

/** The same case at column width, for the table layout. */
export const valueShort = (pick) => {
  const v = priceValue(pick);
  return v ? `All ${v.games} landed, best ${v.best.toFixed(2)}` : null;
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
/**
 * The result on a played card: "7-4 corners · 2-1".
 *
 * Null while the game is still to come, and a distinct sentence when the statistics never
 * arrived — 0-0 corners is a real result and "nobody fetched it" is not, and they must not
 * render the same way.
 */
export const resultText = (card) => {
  const r = card?.result;
  if (!r) return null;
  if (!r.corners_known) return "played — corner count not in yet";
  const goals = (num(r.home_goals) !== null && num(r.away_goals) !== null)
    ? ` · ${r.home_goals}-${r.away_goals}` : "";
  return `${r.home_corners}-${r.away_corners} corners${goals}`;
};

/** How a settled pick is drawn. Word and sign, never the colour alone. */
export const PICK_RESULT = {
  won: { word: "landed", cls: "text-emerald-600 dark:text-emerald-400" },
  lost: { word: "missed", cls: "text-rose-600 dark:text-rose-400" },
  void: { word: "push", cls: "text-muted-foreground" },
  half_won: { word: "half", cls: "text-emerald-600 dark:text-emerald-400" },
  half_lost: { word: "half", cls: "text-rose-600 dark:text-rose-400" },
};

export const cardNote = (card) => {
  if (!card) return "";
  // A PLAYED CARD LEADS WITH ITS SCORE, not with what it once suggested.
  if (card.result) {
    const n = num(card.settled) || 0;
    return n ? `${num(card.landed) || 0} of ${n} landed` : "played";
  }
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

/**
 * The strip above the card: `back` days behind, today, then `count - 1` ahead.
 *
 * IT REACHES BACKWARDS NOW. The card used to start at today, because a played day was a
 * 400 — and the day you most want to look at a card is the day after it, with the corner
 * count beside each line you were offered.
 */
export const dayStrip = (now = new Date(), count = 7, back = 3) => {
  const out = [];
  for (let i = -back; i < count; i += 1) {
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
      past: i < 0,
      short: i === 0 ? "Today" : i === 1 ? "Tomorrow" : i === -1 ? "Yesterday"
        : get("weekday"),
      label: `${get("weekday")} ${get("day")} ${get("month")}`,
    });
  }
  return out;
};
