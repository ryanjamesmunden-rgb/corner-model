// How much ROOM a streak had, as opposed to how often it landed.
//
// The streak screen treats 5/5 as 5/5. It isn't. A team that won 4+ corners with
// exactly 4 in every one of those games is one corner from a broken run in all five;
// a team that won 4, 7, 8, 6, 9 cleared the same line with a different sport's worth of
// margin. Both print "5/5" and the second is a far better bet — that difference is the
// whole of this file.
//
// It is also the honest version of "it flew in last week, back it again". Backing a
// repeat because the last one won is the hot-hand fallacy; the site's own streak code
// already refuses to call one game a streak. What actually carries information is the
// MARGIN — a line cleared by four corners was priced wrong, a line cleared by nothing
// got lucky — and margin is a property of every leg, not just the newest one.
//
// The margin sign convention follows the backend's settlement in settle_streak_leg:
//   over  — WIN when value >= line, so the margin is value - line, and 0 is a scrape
//            that still won (exactly on the line clears an over)
//   under — WIN when value <  line, so the margin is line - value, and the smallest
//            possible win is 1 (landing exactly ON the line voids, it does not win)
// Get this backwards and the screen recommends the flimsiest runs it can find.

/** Margin for one settled leg. Positive means it cleared with that much to spare. */
export const legMargin = (value, line, direction) =>
  (direction === "under" ? line - value : value - line);

/** Margins of the WINNING legs only. A miss is not a small cushion, it is a miss —
 *  folding it in as a negative number would let one bad game masquerade as a tight one. */
export const winMargins = (row = {}) => (row.recent || [])
  .filter((l) => l.result === "win")
  .map((l) => legMargin(l.value, row.line, row.direction));

/** The worst any winning leg cleared by — the number that says how close this run came
 *  to not existing. null when nothing in the window won. */
export const tightestWin = (row) => {
  const m = winMargins(row);
  return m.length ? Math.min(...m) : null;
};

/** The most recent game in the window. `recent` arrives newest-first. */
export const lastLeg = (row = {}) => (row.recent || [])[0] || null;

/** How comfortably the LAST game landed — null if it didn't win. */
export const lastMargin = (row = {}) => {
  const l = lastLeg(row);
  return l && l.result === "win" ? legMargin(l.value, row.line, row.direction) : null;
};

// The filters offered on screen. `test` returns true to KEEP a row.
//
// "Landed big last time" is the one that answers "back it again if it flew in" — and it
// is deliberately not the default, and deliberately not alone. The two beneath it ask
// the better question, which is whether the run has ever been close, and they are the
// ones worth building a bet on.
export const COMFORT = [
  { v: "any", l: "Any margin", hint: "Every qualifying run", test: () => true },
  {
    v: "last-big", l: "Landed big last time",
    hint: "The most recent game cleared by 2 or more",
    test: (r) => (lastMargin(r) ?? -1) >= 2,
  },
  {
    v: "never-close", l: "Never close",
    hint: "Every winning game cleared by 2 or more",
    test: (r) => (tightestWin(r) ?? -1) >= 2,
  },
  {
    v: "bulletproof", l: "Never close by 3+",
    hint: "Every winning game cleared by 3 or more",
    test: (r) => (tightestWin(r) ?? -1) >= 3,
  },
];

export const comfortFilter = (key) =>
  (COMFORT.find((c) => c.v === key) || COMFORT[0]).test;
