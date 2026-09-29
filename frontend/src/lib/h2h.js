// Turning the head-to-head payload into the lines the panel prints.
//
// PURE, AND IN lib/ FOR THE USUAL REASON: jest cannot resolve react-router from a page
// module, so anything worth a test lives here and the component only arranges it.
//
// THE ONE RULE THIS FILE KEEPS. Every number arriving from the backend is stated from the
// CURRENT fixture's home side — h2h.py flips an away meeting before it leaves the server.
// So nothing here re-orients anything; it only labels. A second flip in the view layer
// would silently swap the two teams' corners back, and every number would still look
// perfectly plausible.

// Below this, a meeting count is a coincidence rather than a pattern worth a sentence.
export const MIN_FOR_AVERAGE = 2;

// How each split finishes the sentence "Unbeaten in the last 4 ...". `overall` adds
// nothing, because "meetings" is already in the stem.
const SPLIT_WORDS = {
  overall: "",
  home: " at home",
  away: " away",
};

/** "Arsenal 2-1 Chelsea" for one meeting, always in the current fixture's naming order. */
export function scoreLine(row, homeName, awayName) {
  const { goals_home_team: gh, goals_away_team: ga } = row || {};
  if (gh === null || gh === undefined || ga === null || ga === undefined) return null;
  return `${homeName} ${gh}-${ga} ${awayName}`;
}

/** "7-4 · 11 corners" — the half of a head-to-head a corner site is actually here for. */
export function cornerLine(row) {
  const { corners_home_team: ch, corners_away_team: ca, total_corners: total } = row || {};
  if (ch === null || ch === undefined || ca === null || ca === undefined) return null;
  return `${ch}-${ca} · ${total} corners`;
}

/**
 * The date as a short day, in the VIEWER's zone.
 *
 * Deliberately not pinned to Europe/London, unlike everything that goes into a post: a
 * post is composed once and read by everyone, so it has to name one zone, while this is
 * rendered fresh in the reader's browser and should agree with their own clock. Same
 * split as kickoff.js draws.
 */
export function meetingDate(iso, locale = undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
}

/** "H" or "A", from the point of view of the side at home in the fixture being viewed. */
export function venueMark(row) {
  return row?.venue === "home" ? "H" : "A";
}

/**
 * One meeting, ready to render.
 *
 * `score` is null on a row the results cache holds corners but no goals for. The panel
 * prints the corners and leaves the score blank rather than inventing a 0-0, which is
 * what a `?? 0` here would produce — a fabricated draw that also reads as "unbeaten".
 */
export function meetingRows(h2h) {
  const { meetings = [], home_name: homeName = "", away_name: awayName = "" } = h2h || {};
  return meetings.map((row, i) => ({
    key: `${row.date || "?"}-${i}`,
    date: meetingDate(row.date),
    venue: venueMark(row),
    competition: row.league_name || row.league_id || "",
    score: scoreLine(row, homeName, awayName),
    corners: cornerLine(row),
    total: row.total_corners,
    result: row.result,
    graded: row.graded,
  }));
}

/**
 * "Unbeaten in their last 4 meetings" / "...in their last 3 at home".
 *
 * `played` rides along because a run of 3 from 3 and a run of 3 from 9 are different
 * claims, and the shorter one is the one that sounds strongest when stated alone.
 */
export function runLabel(run) {
  if (!run) return "";
  const where = SPLIT_WORDS[run.split] ?? SPLIT_WORDS.overall;
  const noun = run.run === 1 ? "meeting" : "meetings";
  return `Unbeaten in the last ${run.run} ${noun}${where}`;
}

/** Every printable unbeaten run across both sides, each tagged with whose it is. */
export function unbeatenRows(h2h) {
  const { unbeaten = {}, home_name: homeName = "", away_name: awayName = "" } = h2h || {};
  const out = [];
  [["home_team", homeName], ["away_team", awayName]].forEach(([side, name]) => {
    (unbeaten[side] || []).forEach((run) => {
      out.push({
        key: `${side}-${run.split}`,
        side,
        team: name,
        label: runLabel(run),
        run: run.run,
        played: run.played,
      });
    });
  });
  out.sort((a, b) => b.run - a.run);
  return out;
}

/**
 * The record, as "3-1-2" with a word for what each number is.
 *
 * Returns null with nothing graded, so a panel holding two meetings with no scores on
 * file shows the corners and no record, instead of "0-0-0" — which reads as three
 * goalless draws rather than as an absence.
 */
export function recordLine(h2h, homeName, awayName) {
  const rec = h2h?.record;
  if (!rec || !rec.played) return null;
  const parts = [`${homeName} ${rec.home_wins}`, `${rec.draws} drawn`, `${awayName} ${rec.away_wins}`];
  return `${parts.join(" · ")} — ${rec.played} played`;
}

/**
 * The single sentence the collapsed header shows.
 *
 * ORDER IS DELIBERATE: the corner average first, because that is what this site is for
 * and what a reader opening a corner page wants off a closed panel. The longest unbeaten
 * run second, since it is the strongest single claim. Neither invents a number — with
 * fewer than MIN_FOR_AVERAGE meetings there is no average to quote and it says how many
 * meetings there are instead.
 */
export function summaryLine(h2h) {
  const rows = h2h?.meetings || [];
  if (!rows.length) return "No meetings on file";
  const corners = h2h?.corners;
  const bits = [];
  if (corners && corners.played >= MIN_FOR_AVERAGE) {
    bits.push(`${corners.avg_total} corners a game over ${corners.played} meetings`);
  } else {
    bits.push(rows.length === 1 ? "1 meeting on file" : `${rows.length} meetings on file`);
  }
  const best = unbeatenRows(h2h)[0];
  if (best) bits.push(`${best.team} unbeaten in ${best.run}`);
  return bits.join(" · ");
}

/** Is there anything at all to show? An empty panel should not render a header. */
export function hasH2H(h2h) {
  return Boolean((h2h?.meetings || []).length);
}
