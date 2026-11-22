// Will the side this line is on be CHASING? The server's game-state verdict, as a badge.
//
// The verdict is worked out in backend/game_state.py, so the board, the bot and the
// spreadsheet cannot disagree about it; this only decides how it looks.
//
// `neutral` GETS NO BADGE, for the same reason `credible` gets none on the edge: marking
// the normal case marks every row, and a board where everything wears a label has said
// nothing.
//
// UNMEASURED, AND THE BADGE SAYS SO on hover. measure_chase_filter replays these rules
// against every stored match; until that shows them separating, the label sits beside
// the price and does not move it — the board is not sorted on it.

export const GAME_STATE = {
  chase_spot: {
    label: "chase spot",
    cls: "text-emerald-400 border-emerald-400/40",
    note: "text-emerald-400/80",
  },
  caution: {
    label: "sits on a lead",
    cls: "text-amber-400 border-amber-400/40",
    note: "text-amber-400/80",
  },
  avoid: {
    label: "avoid",
    cls: "text-red-400 border-red-400/40",
    note: "text-red-400/80",
  },
};

export const UNMEASURED_HINT =
  "Game-state label — how this side's corners move when it trails or leads, and how "
  + "much stronger the opponent is. Not yet backtested: read it beside the price, "
  + "the board is not sorted on it.";

// The badge for a row, or null for neutral / a total line / an older server.
export function gameStateBadge(row) {
  const gs = row?.game_state;
  if (!gs) return null;
  const meta = GAME_STATE[gs.verdict];
  return meta ? { verdict: gs.verdict, ...meta } : null;
}

// The sentences to print under the row: the reasons the verdict rests on, capped so a
// phone screen is not mostly caveats. Neutral rows still say a reason when one exists —
// a market that makes the opponent odds-on is worth knowing with no verdict attached.
export function gameStateReasons(row, max = 2) {
  const reasons = row?.game_state?.reasons;
  return Array.isArray(reasons) ? reasons.slice(0, max) : [];
}
