// How the starred GAMES on the Saved page are ordered.
//
// SCOPED TO THE GAMES, DELIBERATELY. The followed-teams list has its own ranking in
// lib/teamForm — SAVED_SORTS, VENUES, MIN_RANK_GAMES and rankTeams — which sorts sides by
// their recent corners won over the last 5/10/20 and remembers the choice. That is the
// right answer for a team and there is no reason for a second one.
//
// A starred fixture is a different question with no overlap: nobody has played it, so
// there is no "recent form" for the game itself. What it has is the model's projection,
// which is why this ranks on that and lives apart rather than being folded into
// rankTeams.
//
// EXTRACTED SO IT CAN BE TESTED. jest cannot resolve react-router from inside the page,
// and the part worth asserting is the one a reader would be misled by: a game the model
// has no view of must not sort as a zero.

export const GAME_SORTS = [
  { key: "kickoff", label: "Kick-off" },
  { key: "highest", label: "Highest" },
  { key: "lowest", label: "Lowest" },
];

export const GAME_SORT_DEFAULT = "kickoff";

/** The number a starred game is ranked on, or null when the model has no view of it. */
export const gameMetric = (f) => {
  const v = f?.projection?.lambda_total;
  return typeof v === "number" ? v : null;
};

const byDate = (a, b) => String(a?.date || "").localeCompare(String(b?.date || ""));

/**
 * Starred games in the chosen order, with everything unprojected LAST.
 *
 * UNPROJECTED GAMES STAY AT THE BOTTOM IN BOTH DIRECTIONS, which is the whole care here.
 * A star can sit further out than the board projects, so those rows have no number — and
 * sorting them as zero would put them top of "lowest", making the one list that looked
 * like an answer out of rows the model has no opinion about. They keep kick-off order
 * among themselves, so flipping the direction never reshuffles them.
 *
 * Ties fall back to kick-off, so two games projecting the same total come back in a fixed
 * order rather than whichever the server happened to return.
 */
export const sortSavedGames = (games, sort) => {
  const list = [...(games || [])];
  if (sort === "kickoff" || !sort) return list.sort(byDate);
  const measured = list.filter((g) => gameMetric(g) !== null);
  const rest = list.filter((g) => gameMetric(g) === null);
  measured.sort((a, b) => {
    const d = sort === "lowest"
      ? gameMetric(a) - gameMetric(b)
      : gameMetric(b) - gameMetric(a);
    return d !== 0 ? d : byDate(a, b);
  });
  rest.sort(byDate);
  return [...measured, ...rest];
};

/** How many starred games the model has no number for, so the page can say so. */
export const unprojectedCount = (games) =>
  (games || []).filter((g) => gameMetric(g) === null).length;
