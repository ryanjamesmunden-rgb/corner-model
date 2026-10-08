// The runs going into a fixture, as the fixture page shows them.
//
// WHY THIS EXISTS. /streaks tells you a team is on a run. Click the fixture and the run
// vanished: the page had `data.streaks` all along and spent it on a share button, so the
// one thing that made the reader click was the one thing the destination did not say.
// Everything below reads that same payload — no new endpoint, no second definition of
// what a streak is.
//
// THE SHAPE IS fixture_streaks', NOT THE STREAK BOARD'S, and they are not the same. The
// board's rows nest everything under `streak` and carry the settled record and the last
// legs; these come from `live_streak` and are flat — `team`, `run`, `line`, `subject`,
// `direction`, `venue`, `games`, `since`. Writing this against the board's shape produced
// a panel that filtered every row away and rendered nothing on every fixture, which looks
// exactly like a quiet page. Read the endpoint, not the other caller.
//
// SUBJECT IS PRINTED, AND THAT IS THE POINT OF PRINTING IT. `line_label` is "5+" for a
// team's own corners and "5+" for the MATCH total — the same two characters for two bets
// roughly a factor of two apart. A panel that showed the label alone would be handing the
// reader the wrong number half the time. chaseSlate.js carries the same warning for the
// same reason.
//
// THE FIRE IS A THRESHOLD, NOT A JUDGEMENT, and it is the one the rest of the site already
// uses (FIRE_RUN in shareText.js — eight). A mark that meant something different here from
// in the share text and the angle menu would be three marks wearing one emoji.
//
// AND IT IS NOT A RECOMMENDATION. A long run is the weakest reading of a team on its own:
// measure_chase_board.py replayed four orderings walk-forward and could not separate any
// of them from a shuffled control, so a run says what has happened and not what will.
import { FIRE_RUN, SHARE_MIN_RUN } from "./shareText.js";

export { FIRE_RUN, SHARE_MIN_RUN };

/**
 * The floor for the PANEL, which is not the floor for a post.
 *
 * On screen a reader can weigh a three-game run themselves — it carries its own length and
 * the games behind it. A post cannot be weighed, so the share builder keeps the stricter cut
 * at SHARE_MIN_RUN. One payload, two consumers, and the stricter standard belongs where the
 * reader cannot answer back.
 *
 * THIS WAS 5 AND IT HID THE CONCEDED RUNS. Five in a row at the same line on the same venue
 * is rare, so most fixtures showed nothing at all and the newest subject on the panel almost
 * never surfaced.
 */
export const MIN_RUN = 3;

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
 * WHOSE corners, in words.
 *
 * "corners" alone is the ambiguity this exists to remove: a team line of 5+ and a match
 * total of 5+ are different bets about the same game, and the match number is roughly
 * twice the team one.
 */
export const subjectLabel = (subject) =>
  (subject === "match" ? "in the match"
    : subject === "conceded" ? "corners against them"
    : "their own corners");

// The subjects the API actually sends. A WHITELIST, not a two-way normalisation: the
// original `subject === "match" ? "match" : "team"` turned every unrecognised subject
// into "team", so a conceded run would have printed "their own corners" — the exact
// opposite of what it is, on a row that otherwise looks correct.
const SUBJECTS = ["team", "match", "conceded"];

// WHICH POOL THE RUN CAME FROM, in words. The fixture payload carries overall runs beside
// the venue ones now, and this used to read `s.venue === "away" ? "away" : "home"` — which
// did not merely lose the distinction, it ASSERTED the wrong one: every overall run was
// relabelled as a home run, in the detail line and in anything else reading this row.
//
// A whitelist for the same reason SUBJECTS is one. Silently mapping an unknown value onto
// a real venue is how a row ends up making a confident claim about games it never looked
// at.
const VENUES = {
  home: "at home",
  away: "away",
  // Not "overall": the panel is read a line at a time and "home and away" cannot be
  // misread as a venue, where "overall" sits next to "at home" and looks like one.
  overall: "home and away",
};
const VENUE_TAGS = { home: "Home", away: "Away", overall: "Overall" };

/** One streak, reduced to what the panel prints. */
export const streakRow = (s = {}) => {
  const run = num(s.run) || 0;
  const line = num(s.line);
  const direction = s.direction === "under" ? "under" : "over";
  const subject = SUBJECTS.includes(s.subject) ? s.subject : "team";
  const team = s.team || "";
  const label = s.line_label || "";
  const venue = VENUES[s.venue] ? s.venue : "home";
  return {
    team,
    // Straight from the API rather than rebuilt from the number: mislabelling an under as
    // an over costs money in the opposite direction to the reader's intent.
    label,
    line,
    direction,
    subject,
    subjectText: subjectLabel(subject),
    // WHO THE BET IS ON, which on a conceded run is not whose run it is. "Brighton 5+"
    // off a Brighton CONCEDED streak reads as backing Brighton's corners — the opposite
    // side of the exact angle the row exists to find. The verb is what separates them.
    claim: subject === "conceded" ? `${team} concede ${label}` : `${team} ${label}`,
    // The side actually taking those corners next, when the API named them.
    opponent: s.opponent || null,
    venue,
    // The long form for the detail line, and a one-word tag for the badge. The badge is
    // what actually answers "which of these is which" — the detail line is small grey
    // text under the claim, and on a panel with six rows nobody reads it six times.
    venueText: VENUES[venue],
    venueTag: VENUE_TAGS[venue],
    run,
    mark: markFor(run),
    hot: run >= FIRE_RUN,
    // How much history the run sits in. The run is not a rate, and `games` is the only
    // denominator this payload carries — without it "9 in a row" has no sample beside it.
    games: num(s.games),
    since: s.since || null,
    // VENUE IS IN THE KEY. Without it a venue run and an overall run at the same line
    // collide — React renders duplicate keys and the two rows are no longer reliably
    // distinct, which is the same bug as the label one wearing different clothes.
    key: `${s.team}-${s.subject}-${direction}-${line}-${venue}`,
  };
};

/**
 * Both sides' runs, longest first.
 *
 * DESCRIPTIVE ORDER. Longest at the top because that is what a reader looks for, not
 * because a longer run is a better bet — see the note at the top of this file.
 */
export const fixtureStreaks = (streaks = [], minRun = MIN_RUN) =>
  (streaks || [])
    .filter((s) => (num(s?.run) || 0) >= minRun && s?.line_label && s?.team)
    .map(streakRow)
    .sort((a, b) => b.run - a.run);

/** "their own corners at home · 9 in a row of 20 on file" — the sample beside the claim. */
export const streakDetail = (r = {}) => [
  `${r.subjectText} ${r.venueText || "at home"}`,
  // Names the bet on a conceded row. The run is the defence's; the slip is the other
  // side's team corners, and that inversion is the one thing a reader must not have to
  // work out for themselves.
  r.subject === "conceded" && r.opponent ? `${r.opponent} to win them` : null,
  r.games ? `${r.games} games on file` : null,
].filter(Boolean).join("  ·  ");

/** A one-line summary for the panel's header. */
export const streakHeadline = (rows = []) => {
  if (!rows.length) return "";
  const hot = rows.filter((r) => r.hot).length;
  const n = `${rows.length} streak${rows.length === 1 ? "" : "s"} running into this game`;
  return hot ? `${n} · ${hot} on ${FIRE_RUN}+` : n;
};
