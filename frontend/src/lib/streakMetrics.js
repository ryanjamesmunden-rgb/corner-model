// What a streak is counting, and on what scale.
//
// EXTRACTED SO IT CAN BE TESTED. jest cannot resolve react-router from inside
// StreakFinder.jsx, so nothing asserted about the component can live beside it — and the
// one thing here that fails silently is a subject with no ladder of its own: the lookup
// falls back to the corner rungs and quietly offers "3+ shots", which every side clears
// every week. The tests in streakMetrics.test.js exist for that.

// TWO CONTROLS, NOT ONE LIST OF SIX. Shots sit on their own drop-down beside the subject
// so that the three questions — for, against, or the whole match — read the same
// whichever stat is chosen, instead of the subject list doubling and every entry having
// to repeat the unit in its wording.
export const METRICS = [
  { v: "corners", l: "Corners" },
  { v: "shots", l: "Shots" },
];

// MEASURED BEFORE IT WAS OFFERED. measure_features, 11 Nov, over 20,664 team-sides: total
// shots are 99.7% covered at a league average of 13.17 a side. Shots on target (69.9%)
// and blocked shots (69.8%) are deliberately absent — a run filter needs the stat in
// EVERY game of its window, and a third of them missing turns "5 of the last 5" into a
// question the data cannot answer rather than one the team failed.
export const SUBJECTS = [
  { v: "team", l: "Team" },
  { v: "conceded", l: "Conceded / faced" },
  { v: "match", l: "Match total" },
];

// The subject the API is actually asked for. The backend keys its ladders, its over floor
// and its under cap on ONE string, so the two controls are composed into it here rather
// than the endpoint growing a second parameter that every snapshot and settlement path
// would also have to learn.
export const WIRE_SUBJECT = {
  corners: { team: "team", conceded: "conceded", match: "match" },
  shots: { team: "shots", conceded: "shots_conceded", match: "shots_match" },
};

export const wireSubject = (metric, subject) =>
  (WIRE_SUBJECT[metric] || WIRE_SUBJECT.corners)[subject] || subject;

export const SUBJECT_LABEL = {
  team: "Team corners",
  conceded: "Corners conceded",
  match: "Match total",
  shots: "Team shots",
  shots_conceded: "Shots faced",
  shots_match: "Match shots",
};

// Laddered lines per direction and wire subject — team corners run far lower than match
// totals, and shots run about three times either.
export const LADDERS = {
  "over-team": [3, 4, 5, 6, 7],
  "over-match": [8, 9, 10, 11, 12, 13],
  "under-team": [3, 4, 5, 6, 7, 8],
  "under-match": [8, 9, 10, 11, 12],
  // Same scale as a team's own corners: it is the same count, from the other end of the
  // same match.
  "over-conceded": [3, 4, 5, 6, 7],
  "under-conceded": [3, 4, 5, 6, 7, 8],
  // 13.17 shots a side measured, so roughly 26 in a match.
  "over-shots": [10, 11, 12, 13, 14, 15, 16],
  "under-shots": [9, 10, 11, 12, 13, 14, 15, 16],
  "over-shots_conceded": [10, 11, 12, 13, 14, 15, 16],
  "under-shots_conceded": [9, 10, 11, 12, 13, 14, 15, 16],
  "over-shots_match": [21, 23, 25, 27, 29, 31],
  "under-shots_match": [20, 22, 24, 26, 28, 30],
};

// Mirrors the server's OVER_LINE_FLOOR. Sent as `min_line` on overs so the board does not
// come back full of lines that describe the sport rather than the team.
export const MIN_LINE = {
  team: 3,
  match: 7,
  conceded: 3,
  shots: 9,
  shots_conceded: 9,
  shots_match: 20,
};

// THE CHIP HAS TO CARRY WHAT IT IS MEASURING. "5+" beside a team's name reads as that
// team's own corners everywhere else on this site, so an unmarked chip on a conceded run
// is the same two characters meaning the opposite bet — and an unmarked chip on a shots
// run is the same characters meaning a different stat entirely, since 13 is also an
// ordinary corner line for a match total.
export const lineLabel = (line, direction, subject) => {
  const base = direction === "under" ? `U ${line}` : `${line}+`;
  if (subject === "shots" || subject === "shots_match") return `${base} sh`;
  if (subject === "shots_conceded") return `${base} sh faced`;
  return subject === "conceded" ? `conc ${base}` : base;
};
