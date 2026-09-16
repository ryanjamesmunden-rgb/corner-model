// Reading a cup tie, where the two sides' form comes from two different leagues.
//
// THE CAVEAT IS THE PRODUCT HERE, not decoration on it. A cup row looks exactly like a
// domestic one — same λ, same edge percentage, same chips — and it is built on evidence
// that transfers less well: Arsenal's corner count was earned against Fulham and Brentford,
// and it is being pointed at Bayern. That is still the best evidence available, and a row
// that does not say so is quietly claiming more than it has.
//
// WHAT THE BACKEND ALREADY DECIDED, and why this file does not re-decide it:
//
//   - A tie where either side is unknown, or has under eight domestic games, is never
//     stored (see backend/cups.py). So there is no "partial" state to render.
//   - `cross_league` is FALSE for an all-English tie in Europe. Both records are Premier
//     League records, directly comparable, and a transfer warning there would be a
//     warning about nothing — which is how people learn to ignore the real ones.
//
// ROTATION IS THE LIMIT NOTHING CAN SEE. Cup weeks are when managers rest players, and no
// corner count in this app knows a team sheet changed. It is said on the row rather than
// modelled, because the alternative is a haircut on the projection with no measurement
// behind it.

/** Is this fixture row a cup tie? */
export const isCup = (row) => Boolean(row?.is_cup);

/** Does this row's evidence come from two different leagues? */
export const isCrossLeague = (row) => Boolean(row?.cross_league);

/**
 * The short marker for a cup row — the competition, said plainly.
 *
 * Returns "" for a domestic fixture, so a caller can render it unconditionally and get
 * nothing on the 27 leagues.
 */
export const cupLabel = (row) => (isCup(row) ? (row?.league_name || "Cup") : "");

/**
 * The one-line caveat, or "" when there is nothing to warn about.
 *
 * PREFERS THE BACKEND'S OWN SENTENCE. It names the two leagues, and it is the same string
 * the API export and any posted pick carry — two versions of this warning that drifted
 * apart would eventually have the page and the post disagreeing about what the row means.
 * The fallback covers a row from an older payload that predates the field.
 */
export const transferNote = (row) => {
  if (!isCrossLeague(row)) return "";
  if (row?.transfer_note) return row.transfer_note;
  const h = row?.home_league_name;
  const a = row?.away_league_name;
  return h && a
    ? `Form is from each side's own league — ${h} and ${a} — so the two records were `
      + `earned against different opposition. Cup weeks also bring rotation, which no `
      + `corner count can see.`
    : "Each side's form comes from its own league, so the two records were earned against "
      + "different opposition. Cup weeks also bring rotation, which no corner count can see.";
};

/**
 * A compact "PL v BUN" style tag for the two leagues behind a cross-league row.
 *
 * Returns "" unless the row is genuinely cross-league, so it never appears on a domestic
 * fixture and never appears on an all-English European tie.
 */
export const leaguePair = (row) => {
  if (!isCrossLeague(row)) return "";
  const h = row?.home_league_name;
  const a = row?.away_league_name;
  return h && a ? `${h} v ${a}` : "";
};

/**
 * How confident the row's evidence is, as a word: "domestic" | "cross-league".
 *
 * Deliberately NOT a number. A discount factor would need a measurement — how much does a
 * corners-won rate actually survive a change of opposition — and this app has never made
 * one. See the falsified-ranking notes in backend/test_chase_score.py for what happens to
 * plausible-sounding adjustments here when they are finally measured.
 */
export const evidenceKind = (row) => (isCrossLeague(row) ? "cross-league" : "domestic");

/**
 * The tooltip for the λ chip on a cup row — the edge percentage needs explaining
 * differently there.
 *
 * On a domestic row "this league averages 10.4" is exact. On a cross-league tie the
 * comparison is against the MIDPOINT of the two leagues, because the match belongs to
 * neither, and a tooltip saying "this league" would be naming a league that is not in the
 * fixture.
 */
/**
 * The marker for a CARD row whose next fixture is a cross-league cup tie.
 *
 * The angle card carries a streak and the opponent that streak is about to meet. Both come
 * from the team's domestic season; the opponent, in a European tie, does not. That makes
 * the corroboration weaker than the identical-looking row above it — the opponent's
 * conceded rate was measured in a different league — and the card is the thing people pay
 * for, so it says so rather than letting the row read as a domestic one.
 *
 * Takes a `next_fixture`, which is what a card row carries, and returns "" for the
 * domestic case, which is almost every row.
 */
export const fixtureCaveatTag = (nextFixture) =>
  (nextFixture?.cross_league ? "cup · different leagues" : "");

export const edgeTitle = (row) => {
  const total = row?.lambda_total;
  const avg = row?.league_avg_total;
  if (isCrossLeague(row)) {
    return `Model projects ${total} corners; ${avg} is the midpoint of the two leagues `
      + `involved, since the tie belongs to neither.`;
  }
  return `Model projects ${total} corners; this league averages ${avg}`;
};
