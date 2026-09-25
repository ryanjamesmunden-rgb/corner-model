// Which view the Streaks page opens on, and in what order the tabs sit.
//
// IN A LIB BECAUSE THE PAGE CANNOT BE TESTED. Streaks.jsx pulls in react-router, which
// jest here cannot resolve, so anything asserted about it has to live in a module the tests
// can import — the same reason every other decision in this folder is here rather than in
// the component.
//
// AND IT IS WORTH ASSERTING. Which tab a page opens on is exactly the kind of thing a later
// edit flips back by accident: it is one word, it changes nothing visible in a diff, and
// nothing fails.
//
// CONSISTENCY LEADS. The two views answer different questions and only one of them is a
// bet. Consistency is a COUNT of games clearing a line — "5+ corners in each of the last
// nine" — which names a market a reader can go and price. Hot form is a DIFFERENCE between
// a recent average and a season baseline with no line attached, so arriving on it means
// doing a translation the page never asked for. That is what made it confusing as the
// landing tab: the first thing shown was the thing furthest from a bet.
//
// HOT FORM STAYS, SECOND. It is real, and it is the earlier signal — a run has to start
// somewhere — it is just no longer what the page opens on.
//
// NEITHER ORDER IS A CLAIM ABOUT PROFIT. measure_chase_board replayed four orderings
// walk-forward against a shuffled control and separated none of them, so "consistency
// first" means more READABLE, not better.

/** The tabs, in the order they are shown. First is the default. */
export const STREAK_VIEWS = [
  { id: "consistency", label: "Consistency" },
  { id: "form", label: "Hot Form" },
];

/** What the page opens on. Read from the order rather than restated, so the two cannot drift. */
export const DEFAULT_STREAK_VIEW = STREAK_VIEWS[0].id;

/** The error boundary's label for a view — it names what failed, not "something went wrong". */
export const streakViewLabel = (id) =>
  (id === "form" ? "Hot form" : "The streak finder");
