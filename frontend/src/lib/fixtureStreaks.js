// The runs going into a fixture, as the fixture page shows them.
//
// WHY THIS EXISTS. /streaks tells you a team is on a run. Click the fixture and the run
// vanished: the page had `data.streaks` all along and spent it on a share button, so the
// one thing that made the reader click was the one thing the destination did not say.
// Everything below reads that same payload — no new endpoint, no second definition of
// what a streak is.
//
// THE FIRE IS A THRESHOLD, NOT A JUDGEMENT, and it is the one the rest of the site already
// uses (FIRE_RUN in shareText.js — eight). A mark that meant something different here from
// in the share text and the angle menu would be three marks wearing one emoji.
//
// AND IT IS NOT A RECOMMENDATION. A long run is the weakest reading of a team on its own:
// measure_chase_board.py replayed four orderings walk-forward and could not separate any
// of them from a shuffled control, so a run says what has happened and not what will.
// The page states the run, the sample it is out of, and the numbers behind it, and leaves
// the argument to the projection and the matchup that sit beside it.
import { FIRE_RUN } from "./shareText.js";

export { FIRE_RUN };

/** How many past legs the panel shows. Enough to see the shape, few enough to scan. */
export const RECENT_SHOWN = 6;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * 🔥 for a long run, 🚩 for the rest.
 *
 * Two marks rather than a scale. A run is either notable or it is a row on a list, and a
 * five-step ladder of emoji would imply a precision the ordering has not earned.
 */
export const markFor = (run) => ((num(run) || 0) >= FIRE_RUN ? "🔥" : "🚩");

/**
 * One streak, reduced to what the panel prints.
 *
 * THE RUN AND THE RECORD ARE DIFFERENT NUMBERS and both are shown. "9 in a row" is the
 * current run; "9 of 9" is how the window settled. They usually agree, and when they do
 * not — a void mid-window, or a run shorter than the window it sits in — the pair is the
 * honest answer and either alone is a flattering one.
 */
export const streakRow = (s = {}) => {
  const st = s.streak || {};
  const run = num(st.length) || 0;
  const settled = num(st.settled) || 0;
  const hits = num(st.hits) || 0;
  return {
    team: s.name || "",
    teamId: s.team_id || null,
    leagueId: s.league_id || null,
    // Straight from the API so the page cannot label a direction differently from the
    // board — mislabelling an under as an over is worse than saying less.
    label: st.line_label || "",
    line: num(st.line),
    run,
    mark: markFor(run),
    hot: run >= FIRE_RUN,
    hits,
    settled,
    voids: num(st.voids) || 0,
    avg: num(st.avg),
    lowest: num(st.min_won),
    recent: (st.recent || []).slice(0, RECENT_SHOWN).map((m) => ({
      corners: num(m.corners ?? m.value),
      result: m.result || "",
      opponent: m.opponent || "",
      home: !!m.home,
    })),
  };
};

/**
 * Both sides' runs, longest first.
 *
 * DESCRIPTIVE, and the panel says so. Ordering by length puts the biggest number at the
 * top because that is what a reader looks for, not because a longer run is a better bet —
 * see the note at the top of this file.
 */
export const fixtureStreaks = (streaks = []) =>
  streaks.filter((s) => (num(s?.streak?.length) || 0) >= 2)
    .map(streakRow)
    .filter((r) => r.label)
    .sort((a, b) => b.run - a.run);

/** "9 of 9 settled · avg 7.2 · lowest 5" — the sample behind the run, or as much as exists. */
export const streakDetail = (r = {}) => [
  r.settled ? `${r.hits} of ${r.settled} settled` : null,
  r.voids ? `${r.voids} void` : null,
  r.avg !== null && r.avg !== undefined ? `avg ${r.avg}` : null,
  r.lowest !== null && r.lowest !== undefined ? `lowest ${r.lowest}` : null,
].filter(Boolean).join("  ·  ");

/** A one-line summary for the panel's header. */
export const streakHeadline = (rows = []) => {
  if (!rows.length) return "";
  const hot = rows.filter((r) => r.hot).length;
  const n = `${rows.length} streak${rows.length === 1 ? "" : "s"} running into this game`;
  return hot ? `${n} · ${hot} on ${FIRE_RUN}+` : n;
};
