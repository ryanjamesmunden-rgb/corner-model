// What is actually CONSISTENT across a team's recent games.
//
// THE PROBLEM THIS SOLVES. The fixture page's bottom section is a ten-column table of raw
// per-game numbers. Everything needed to judge a side is in it and none of it is legible:
// deciding whether a team reliably clears 5 corners means reading a column downwards,
// holding five numbers in your head and comparing each to 5. Readers do that by eye, and
// by eye is where a miscount comes from — the row that looks like a pattern is the row
// with one big number in it.
//
// So this states it instead of leaving it to be worked out. The same games, the same
// split, the same window the reader already chose — reduced to the one thing a corner bet
// turns on: which line did they clear EVERY time, and where does that stop being true.
//
// THE FLOOR IS THE HEADLINE, not the average. An average of 5.4 is true of a side that
// goes 5,5,6,5,6 and of one that goes 1,2,9,6,9, and only the first is worth a line at 5.
// "4+ in all five" is a claim a reader can size up in one glance and act on without
// re-deriving it; a mean is not.
//
// AND IT IS DESCRIPTION, NOT PREDICTION. measure_chase_board.py replayed four orderings
// walk-forward and could not separate any from a shuffled control, so what a side has done
// is not a forecast of what it will do. Every label here is past tense on purpose.

/** The three things worth laddering on a corner page, and where each lives on a game row. */
export const SUBJECTS = [
  { key: "won", label: "Corners won", pick: (m) => m.won, tone: "for" },
  { key: "conceded", label: "Corners conceded", pick: (m) => m.conceded, tone: "against" },
  { key: "total", label: "Match total", pick: (m) => m.total, tone: "total" },
];

// How many rungs to print above the floor. Three is enough to show where reliability runs
// out and short enough to stay one glanceable row on a phone.
export const RUNGS = 3;

// null AND undefined BOTH HAVE TO BE REJECTED EXPLICITLY, because `Number(null)` is 0 and
// finite. A game the provider did not cover carries null, and letting it through as a zero
// drags the floor to 0 — which silently destroys the strongest claim on the panel and
// leaves a number that looks like a measurement.
const num = (v) => {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** The values for one subject across the games shown, missing ones dropped. */
export function valuesFor(games = [], pick) {
  return (games || []).map((m) => num(pick(m || {}))).filter((v) => v !== null);
}

/**
 * The highest line every one of these games cleared.
 *
 * That is just the minimum, and naming it "floor" rather than "min" is the point: as a
 * betting line it reads "they have not been below this", which is the sentence a reader
 * wants. Returns null on no games, never 0 — a floor of 0 is a real and meaningful
 * result (a side kept to nothing once), so it must not be the same value as "no data".
 */
export function floorOf(values = []) {
  return values.length ? Math.min(...values) : null;
}

/** How many of these games reached `line`, with the count it was out of. */
export function hitsAt(values = [], line) {
  const n = values.length;
  const hits = values.filter((v) => v >= line).length;
  return { line, hits, n, pct: n ? Math.round((hits / n) * 100) : 0 };
}

/**
 * The ladder to print: the floor first, then the next few rungs up.
 *
 * STARTS AT THE FLOOR, so the first rung is always 100% and the reader's eye lands on the
 * claim that holds. Rungs above it are where it stops holding, which is the other half of
 * the same question — a side that is 5/5 at 4+ and 4/5 at 5+ is a different bet from one
 * that is 5/5 and 1/5.
 *
 * A floor of 0 starts at 1 instead. "0+ in all five" is true of every team that has ever
 * played and says nothing; the ladder should open on the lowest line that is a claim.
 */
export function ladderFor(values = [], rungs = RUNGS) {
  if (!values.length) return [];
  const start = Math.max(1, floorOf(values));
  const top = Math.max(...values);
  const out = [];
  for (let line = start; line <= start + rungs && line <= Math.max(top, start); line += 1) {
    out.push(hitsAt(values, line));
  }
  return out;
}

/**
 * One subject, reduced to what the strip prints.
 *
 * `every` is the line they never went below AS A CLAIM — null when the floor is 0, because
 * there is no line to name. `range` is there because two sides with the same floor and the
 * same average can still be 4,4,5,5 and 4,9,4,9, and the second is not the same bet.
 */
export function consistencyRow(games, subject) {
  const values = valuesFor(games, subject.pick);
  if (!values.length) return null;
  const floor = floorOf(values);
  const high = Math.max(...values);
  const avg = values.reduce((s, v) => s + v, 0) / values.length;
  return {
    key: subject.key,
    label: subject.label,
    tone: subject.tone,
    n: values.length,
    // The headline claim, or null when the floor is 0 and there is nothing to claim.
    every: floor > 0 ? floor : null,
    low: floor,
    high,
    range: high - floor,
    avg: Math.round(avg * 10) / 10,
    ladder: ladderFor(values),
  };
}

/** All three subjects for the games currently on screen. */
export function consistencyRows(games = []) {
  return SUBJECTS.map((s) => consistencyRow(games, s)).filter(Boolean);
}

/**
 * The sentence for one subject: "4+ every game · 5+ in 4 of 5".
 *
 * Two facts, not five. The floor is what holds and the next rung is where it stops, and a
 * strip that printed the whole ladder in words would be the per-game table again with
 * more characters.
 */
export function consistencyLabel(row) {
  if (!row) return "";
  if (row.every === null) return `as low as 0 · up to ${row.high}`;
  const parts = [`${row.every}+ every game`];
  const next = row.ladder.find((l) => l.line === row.every + 1 && l.hits > 0);
  if (next) parts.push(`${next.line}+ in ${next.hits} of ${next.n}`);
  return parts.join(" · ");
}

/**
 * One line for the whole side: the two floors that matter, won and conceded.
 *
 * Sits on the panel header so the section says something before it is read. Match total is
 * left out deliberately — it is derived from the other two, and a header of three claims
 * is a paragraph.
 */
export function consistencyHeadline(rows = []) {
  const won = rows.find((r) => r.key === "won");
  const conc = rows.find((r) => r.key === "conceded");
  const bits = [];
  if (won?.every) bits.push(`wins ${won.every}+ every game`);
  if (conc?.every) bits.push(`concedes ${conc.every}+ every game`);
  if (!bits.length) return rows.length ? "no line held in every game" : "";
  return bits.join(" · ");
}
