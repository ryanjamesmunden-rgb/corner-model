/**
 * A side's record in the competition the fixture is actually being played in.
 *
 * WHAT THIS IS FOR. Open a Champions League tie and every game the page lists is Serie A
 * or Bundesliga, because a cup has no teams of its own — the fixture points at the
 * domestic rows, and the model prices off twenty league games rather than four European
 * ones. That is right for the model and wrong for the reader, who opened a European page
 * and is asking a European question.
 *
 * IT IS ADDED ABOVE THE DOMESTIC FORM, NOT INSTEAD OF IT. A European league phase is
 * eight games a side spread over four months, and the results store keeps a window —
 * most sides have one or two on file. Swapping forty domestic games for one European one
 * would answer the question asked and leave a worse page. Both facts are true at once:
 * the domestic record is the larger sample, the European one is the closer match, and
 * the count is what lets a reader weigh them.
 *
 * SO EVERY NUMBER HERE IS PRINTED WITH ITS DENOMINATOR, and a single game is described as
 * a single game rather than as an average of one.
 */

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** "3 Nov" — short, because the round beside it carries the context. */
export const gameDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London", day: "numeric", month: "short",
  }).format(d);
};

/**
 * One game as a row: when, where, who, and the corners from THIS side's point of view.
 *
 * `won` arrives already resolved to this team's corners whichever end of the fixture it
 * was at — see cup_form.py — so nothing here has to know which side it is looking at.
 */
export const gameRow = (g) => {
  const won = num(g?.won);
  const conceded = num(g?.conceded);
  if (won === null || conceded === null) return null;
  const gf = num(g?.gf);
  const ga = num(g?.ga);
  return {
    key: g.fixture_id || `${g.date}-${g.opponent}`,
    when: gameDate(g.date),
    venue: g.home ? "H" : "A",
    opponent: g.opponent || "",
    round: g.round || "",
    won,
    conceded,
    corners: `${won}-${conceded}`,
    // Null rather than "0-0" when the score is missing: a goalless game is a result and
    // an unfetched one is not.
    score: gf === null || ga === null ? null : `${gf}-${ga}`,
    // FT, AET or PEN. Extra time is thirty more minutes of corners, which is the one
    // thing a corner count on its own cannot explain.
    extra: g.finished_as && g.finished_as !== "FT" ? g.finished_as : null,
  };
};

export const gameRows = (form) => ((form?.games || []).map(gameRow).filter(Boolean));

/**
 * The summary line, worded for the size of the sample it is describing.
 *
 * ONE GAME IS NOT AN AVERAGE. "5.0 corners a game" over a single match is technically
 * true and reads as a rate — the one reading this is thin enough that it must not invite.
 * So a single game is described as what it is, and only a real sample gets a per-game
 * figure, always with its count and its range.
 */
export const summaryText = (form) => {
  const s = form?.summary;
  const games = num(s?.games);
  if (!games) return "";
  if (games === 1) {
    const only = gameRows(form)[0];
    return only
      ? `One game in this competition: ${only.won} corners won, ${only.conceded} conceded`
      : "One game in this competition";
  }
  const won = num(s.avg_won);
  const conceded = num(s.avg_conceded);
  const range = num(s.low) === null || num(s.high) === null
    ? "" : ` (${s.low}–${s.high})`;
  return `${games} games in this competition · ${won?.toFixed(1)} won`
    + `${conceded === null ? "" : `, ${conceded.toFixed(1)} conceded`} a game${range}`;
};

/** Whether there is anything at all to draw for this side. */
export const hasForm = (form) => gameRows(form).length > 0;

/**
 * What the panel says when a side has nothing on file.
 *
 * NOT "THEY HAVE PLAYED NONE", which the store cannot support: it keeps a window of
 * results, so an empty list means "none we hold a corner count for", and the honest
 * sentence names the competition rather than making a claim about the team.
 */
export const emptyText = (name, competition) =>
  `No ${competition || "competition"} game on file for ${name || "this side"} with a `
  + "corner count — the form below is their league season.";
