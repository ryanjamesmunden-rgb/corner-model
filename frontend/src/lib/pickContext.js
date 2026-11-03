/**
 * The context lines under a pick, as a panel can render them.
 *
 * WHY A SEPARATE MODULE. The same reason as boardBreakdown: the decisions here are the
 * ones that are easy to get quietly wrong, and none of them are about React. The repo
 * tests logic in src/lib and has no component renderer, so anything worth pinning lives
 * here rather than inside JSX.
 *
 * THE ONE RULE THIS FILE EXISTS FOR: evidence and colour must not look alike. The
 * backend already labels every line (`tier`), and a panel that styles them identically
 * throws that away — "unbeaten in 5" rendered in the same type as "won 5+ corners in 9
 * of 10" reads as a second reason to back the pick, and it is not a reason at all.
 *
 * SO COLOUR IS NEVER PROMOTED. If a side has no evidence lines, the panel says there is
 * nothing to show rather than filling the space with form chatter. An empty panel is an
 * honest answer; a full one made of colour is not.
 *
 * AND AMBIGUOUS LINES CARRY THEIR AMBIGUITY. A clean-sheet run points both ways — a side
 * conceding every week may be getting overrun, or playing stretched open games. The
 * backend marks it; this keeps the mark attached so it cannot be read as directional.
 */

export const EVIDENCE = "evidence";
export const COLOUR = "colour";

/** What each group is, in the words a reader needs. Order is display order. */
export const GROUP_LABEL = {
  corners: "Corners",
  opponent: "Opponent",
  pressure: "Pressure",
  state: "Game state",
  colour: "Form",
};

export const GROUP_ORDER = ["corners", "opponent", "pressure", "state", "colour"];

const str = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);

const isEvidence = (c) => c?.tier === EVIDENCE;

/** A line the panel can draw: text, what kind of claim it is, and its sample. */
export const contextLine = (c) => {
  const text = str(c?.text);
  if (!text) return null;
  const group = GROUP_LABEL[c.group] ? c.group : "colour";
  return {
    key: str(c.key) || text.slice(0, 24),
    text,
    group,
    groupLabel: GROUP_LABEL[group],
    tier: isEvidence(c) ? EVIDENCE : COLOUR,
    ambiguous: c.ambiguous === true,
    // n travels so a thin line can be read as thin. Never inferred from the sentence.
    n: Number.isFinite(Number(c?.n)) ? Number(c.n) : null,
    subject: c?.subject === "opponent" ? "opponent" : "team",
  };
};

const lines = (arr) => (Array.isArray(arr) ? arr : []).map(contextLine).filter(Boolean);

/**
 * One side's context, ready to render.
 *
 * `shown` is what the panel prints and is EVIDENCE ONLY. `colour` is kept separate so a
 * panel can offer it as what it is, under its own heading, rather than mixed in.
 */
export const contextView = (ctx) => {
  if (!ctx || typeof ctx !== "object") return null;
  const all = lines(ctx.all);
  const picked = lines(ctx.lines);
  const compound = lines(ctx.compound);

  const evidence = picked.filter((c) => c.tier === EVIDENCE);
  const colour = all.filter((c) => c.tier === COLOUR);

  // The compound is only offered when BOTH halves were evidence. The backend already
  // downgrades a half-colour compound to colour; this keeps that decision rather than
  // re-deriving it from the joined sentence, which cannot be read back apart.
  const joined = compound.filter((c) => c.tier === EVIDENCE);

  const games = Number.isFinite(Number(ctx.games_on_file))
    ? Number(ctx.games_on_file)
    : null;

  return {
    team: str(ctx.team) || "This side",
    opponent: str(ctx.opponent) || "the opponent",
    venue: ctx.venue === "away" ? "away" : "home",
    games,
    thin: ctx.thin === true,
    headline: str(ctx.headline),
    joined,
    shown: evidence,
    colour,
    // Nothing verifiable at all is a real state and gets said out loud.
    empty: evidence.length === 0 && joined.length === 0,
    total: all.length,
  };
};

/**
 * Which side the panel opens on.
 *
 * The side with the stronger case, measured by how many EVIDENCE lines it has, because
 * that is the side a pick is most likely to be about. Ties go to the home team, which is
 * the one the page is titled after. Never decided by lambda: a projection is the model's
 * opinion and this panel's job is to show what is behind it, not to re-rank it.
 */
export const defaultSide = (context) => {
  const n = (side) => lines(context?.[side]?.lines)
    .filter((c) => c.tier === EVIDENCE).length;
  return n("away") > n("home") ? "away" : "home";
};

/** The standing caveat. Shown whenever the panel has anything at all. */
export const CONTEXT_FOOTNOTE =
  "These explain the pick. They do not confirm it — only the graded record does that.";

/** Said when a record is too short for its averages to mean much. */
export const thinNote = (games) =>
  games == null ? null : `Only ${games} game${games === 1 ? "" : "s"} on file.`;
