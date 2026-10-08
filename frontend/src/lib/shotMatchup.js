// One side's shot volume against the OTHER side's shot volume conceded.
//
// WHY THIS IS A FILE AND NOT SIX LINES IN THE COMPONENT. "20 shots a game" is half a
// fixture: a side taking twenty reads the same whether its opponent allows twenty or
// allows seven, and the second of those is the game worth having. Pairing the two is the
// whole value — and it is also the one operation on this page where a mistake is
// invisible, because a number labelled with one team's name while belonging to the other
// looks exactly like a number that is right. So the pairing lives here, with tests that
// would fail if the sides were swapped, rather than inline where nothing can check it.
//
// IT INVENTS NOTHING. There is no "expected shots" here and there should not be: the
// model does not price shots that way, and an average of the two columns would be a new
// number with nothing behind it, on a page whose credibility rests on every figure being
// traceable to games that were played. Two measured averages, side by side, and the
// reader does the comparing.
//
// COVERAGE TRAVELS WITH EVERY ROW. These averages come from whichever games actually
// carried the stat, which on some leagues is a minority of them — an average over 3 of 12
// is not the same evidence as one over 12, and a pairing hides that twice over.

/** The columns worth pairing. `dangerous_attacks` is excluded for the reason the fixture
 *  page already excludes it: the provider returns it empty for these leagues. */
export const MATCHUP_COLS = [
  ["shots", "Shots"],
  ["shots_on_target", "On target"],
  ["blocked_shots", "Blocked"],
];

/** Below this the pairing is arithmetic on a handful of games and says so. */
export const THIN_COVER = 4;

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/**
 * One attacking side against one defending side.
 *
 * `attack` and `defence` are the two teams' `features[split]` blocks — the SAME shape the
 * fixture payload already carries, so nothing new has to be computed server-side.
 *
 * `takes` comes from the attacking side's `_for`. `allows` comes from the defending
 * side's `_against`. Those two lines are the entire point of this file.
 */
export const matchupRows = (attack, defence) => {
  if (!attack && !defence) return [];
  return MATCHUP_COLS.map(([key, label]) => {
    const takes = num(attack?.[`${key}_for`]);
    const allows = num(defence?.[`${key}_against`]);
    const takesCover = num(attack?.covered?.[key]) ?? 0;
    const allowsCover = num(defence?.covered?.[key]) ?? 0;
    return {
      key,
      label,
      takes,
      allows,
      takesCover,
      allowsCover,
      // BOTH HALVES HAVE TO BE THERE FOR IT TO BE A PAIRING. One number on its own is the
      // thing this panel exists to stop being read as a matchup.
      paired: takes !== null && allows !== null,
      thin: Math.min(takesCover, allowsCover) < THIN_COVER,
    };
  });
};

/**
 * Both directions of one fixture.
 *
 * SPLIT PER SIDE, NOT ONE SPLIT FOR THE FIXTURE. The home team's home games against the
 * away team's away games is the pairing that describes this match; "overall" is the
 * escape hatch for a short season, where a venue split is three games and says nothing.
 * Either way both sides move together, because comparing one team's home form against
 * the other's whole season is a comparison of two different things.
 */
export const fixtureMatchup = ({ home, away, homeName, awayName, overall = false } = {}) => {
  const hs = overall ? "overall" : "home";
  const as = overall ? "overall" : "away";
  const hf = home?.features?.[hs];
  const af = away?.features?.[as];
  return [
    { side: "home", team: homeName, opponent: awayName, rows: matchupRows(hf, af) },
    { side: "away", team: awayName, opponent: homeName, rows: matchupRows(af, hf) },
  ];
};

/** "20.1 taken against 18.9 allowed" has no meaning if neither number exists. */
export const hasMatchup = (blocks = []) =>
  blocks.some((b) => b.rows.some((r) => r.paired));
