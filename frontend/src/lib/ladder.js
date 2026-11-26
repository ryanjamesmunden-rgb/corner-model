/**
 * The rung above a run, and whether its price is worth the drop in hit rate.
 *
 * WHY THIS EXISTS. A run is measured at the LOWEST line it never missed, so the line it
 * is named for is the one the market has least trouble pricing — a 3+ run gets quoted at
 * 1.27 and nobody backs that. What the run does not say, and what is sitting in the same
 * games, is how far clear the side actually lands. Measured over 683 active runs and the
 * five games BEFORE each one, so the selection cannot flatter it: a side on a run clears
 * its line by one in 61% of games and by two in 47%.
 *
 * THE TEAM'S OWN RECORD, NOT THAT AVERAGE. 61% is the population; this side is not the
 * population. The ten games riding on the row say what THIS team did at the laddered
 * line, and the five that predate the run say it without the selection in the way — a
 * side whose 4+ record is 9 of 10 but 2 of 5 before the run is a hot streak, and one
 * that is 5 of 5 both halves is a habit. They are printed separately for exactly that
 * reason.
 *
 * NOTHING HERE RECOMMENDS A BET. It puts the model's chance, the book's number and the
 * side's own record at the same line next to each other. The reader decides whether the
 * price pays for the drop.
 */

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** How many of `games` reached `line`, and how many were counted at all. */
export const recordAt = (games, line) => {
  const vals = (games || []).map((g) => num(g?.value)).filter((v) => v !== null);
  if (!vals.length || line === null) return null;
  return { hits: vals.filter((v) => v >= line).length, games: vals.length };
};

/**
 * What a record of `hits` in `games` is worth as a price, with the small sample shrunk.
 *
 * NOT hits/games, AND THE DIFFERENCE IS THE WHOLE POINT ON TEN GAMES. Ten from ten reads
 * as a certainty and prices at 1.00, so every number a book could possibly offer "beats
 * the record" and the comparison says nothing at all — which is exactly what the test
 * for it caught. Adding one hit and one miss before dividing (Laplace) turns 10 of 10
 * into 11 of 12, a price of 1.09, which is a claim a sample this size can support.
 *
 * It costs accuracy on a long record and buys honesty on a short one, and every record
 * here is short.
 */
export const impliedPrice = (rec) => {
  if (!rec || !rec.games) return null;
  return (rec.games + 2) / (rec.hits + 1);
};

/**
 * One rung: the line, the price, the model, and this side's record at it.
 *
 * `run` is the games the run was measured over (the newest five) and `before` the five
 * that predate it. `before` is the honest half and is marked as such.
 */
export const rung = (step, row) => {
  const line = num(step?.line);
  if (line === null) return null;
  const all = row?.last_games || [];
  const book = num(step.book_odds);
  const prob = num(step.prob);
  const whole = recordAt(all, line);
  const pre = recordAt(all.slice(5), line);
  return {
    line,
    label: step.label || `${line}+`,
    book,
    fair: num(step.fair_odds),
    prob,
    ev: num(step.ev),
    whole,
    pre,
    implied: impliedPrice(whole),
    // THE COMPARISON THAT MATTERS, and it is not the model's. A price pays for itself
    // when it beats what the side's OWN record implies.
    beatsRecord: book !== null && impliedPrice(whole) !== null
      && book > impliedPrice(whole),
  };
};

/** Every rung above the run, newest row shape in, drawable rows out. */
export const ladderOf = (row) =>
  ((row?.projection?.ladder) || []).map((s) => rung(s, row)).filter(Boolean);

/**
 * The one rung worth leading with, or null.
 *
 * PRICED, AND BETTER THAN THE SIDE'S OWN RECORD IMPLIES, and backed by a record at that
 * line rather than at the line below it. Where two qualify the higher one is taken: it
 * is the longer price and the record has already been asked to carry it.
 */
export const bestRung = (row, minHits = 8) => {
  const ok = ladderOf(row).filter((r) => r.book !== null && r.beatsRecord
    && r.whole && r.whole.hits >= minHits);
  return ok.length ? ok[ok.length - 1] : null;
};

/** "4+ at 1.85 · 9 of 10, 5 of 5 before the run" */
export const rungText = (r) => {
  if (!r) return "";
  const price = r.book === null ? `fair ${r.fair?.toFixed(2)}` : r.book.toFixed(2);
  const rec = r.whole ? ` · ${r.whole.hits} of ${r.whole.games}` : "";
  const pre = r.pre && r.pre.games
    ? `, ${r.pre.hits} of ${r.pre.games} before the run` : "";
  return `${r.label} at ${price}${rec}${pre}`;
};
