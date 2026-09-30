// W / D / L going into the game — the first thing anyone wants to know about a fixture.
//
// WHY IT IS HERE AT ALL ON A CORNER SITE. It is not a corner stat and it does not feed the
// model. It is the sentence a reader needs before any of the corner numbers mean anything:
// a side winning every week and a side losing every week produce corners for opposite
// reasons, and the page previously opened on a lambda with no idea which of those you were
// looking at. It sits in the header for the same reason a scoreboard does — orientation, not
// evidence.
//
// DERIVED FROM THE GOALS ALREADY ON EACH GAME, not fetched. `recent` carries `gf` and `ga`
// per match, so this needs no new endpoint and cannot disagree with the results printed
// further down the page.
//
// A GAME WITH NO SCORE ON FILE IS A GAP, NOT A DRAW. Older cached rows carry corners and no
// goals until the backfill reaches them, and `gf === ga` on two nulls is true — which would
// print a confident D for a match nobody has the result of. That is the one way this can be
// wrong and look right, so it is the thing the type check exists for.

export const RESULTS = { win: "W", draw: "D", loss: "L" };

/** One game's result from the team's own point of view, or null when it is not on file. */
export function resultOf(game) {
  const gf = game?.gf;
  const ga = game?.ga;
  if (typeof gf !== "number" || typeof ga !== "number") return null;
  if (gf > ga) return RESULTS.win;
  if (gf < ga) return RESULTS.loss;
  return RESULTS.draw;
}

// `recent` arrives newest-first, which is the right order for a table and the wrong one for a
// run: "L W W D W" read towards the game is a side finding form, and the same characters the
// other way round is a side losing it.
export const FORM_GAMES = 10;

/**
 * The last `n` results, OLDEST FIRST so the strip reads left to right into the fixture.
 *
 * THIS SEASON ONLY when a season is given, and that is the whole reason the argument exists.
 * The sample pool mixes seasons on purpose — the sync tops up from last year while this one
 * is thin — so a five-game strip in August could be three games under a new manager and two
 * under the old one, read as one run. A form strip is the most glanceable thing on the page
 * and the least likely to be questioned, so it gets the strictest window rather than the
 * widest.
 *
 * Ungraded games are dropped rather than rendered as a gap, so every badge means a result.
 * `played` says how many were available, which is what stops three badges reading as a
 * three-game run when it is simply all there is.
 */
export function formRun(games = [], n = FORM_GAMES, currentSeason) {
  const pool = currentSeason == null
    ? (games || [])
    : (games || []).filter((g) => {
        const s = g?.season;
        // Unknown season counts as current — rows synced before the stamp shipped carry
        // none, and dropping them would empty the strip for a week after a deploy.
        return s === null || s === undefined || Number(s) >= Number(currentSeason);
      });
  const all = pool.map(resultOf).filter(Boolean);
  const shown = all.slice(0, n).reverse();
  return { run: shown, played: all.length };
}

/** "3W 1D 1L" over the games shown — the record, for anyone who does not read the strip. */
export function formSummary(run = []) {
  if (!run.length) return "";
  const n = (r) => run.filter((x) => x === r).length;
  return [[n(RESULTS.win), "W"], [n(RESULTS.draw), "D"], [n(RESULTS.loss), "L"]]
    .filter(([c]) => c > 0)
    .map(([c, l]) => `${c}${l}`)
    .join(" ");
}

/**
 * How many games since the last defeat, counting back from the most recent.
 *
 * FROM THE NEWEST END, because that is what "unbeaten in 4" means. Counting from the other
 * end reports a run that ended some time ago as one running into this fixture — the same
 * mistake the conceded-streak code had to be stopped from making.
 */
export function unbeatenRun(run = []) {
  let count = 0;
  for (let i = run.length - 1; i >= 0; i -= 1) {
    if (run[i] === RESULTS.loss) break;
    count += 1;
  }
  return count;
}

/** The one-line read: "unbeaten in 4" when it is worth saying, otherwise the record. */
export function formLabel(run = [], minRun = 3) {
  if (!run.length) return "";
  const unbeaten = unbeatenRun(run);
  if (unbeaten >= minRun && unbeaten === run.length) return `unbeaten in ${unbeaten}`;
  if (unbeaten >= minRun) return `unbeaten in ${unbeaten}`;
  return formSummary(run);
}
