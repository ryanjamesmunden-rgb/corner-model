// Narrowing the fixture board to the shape of game you are actually looking for.
//
// The board answers "what is worth opening tonight" and hands back every kind of angle at
// once — a chase spot, a mismatch, a run on either side. That is the right default and the
// wrong thing to scan when you have a specific idea in mind: "which of these has the HOME
// side on a run", or "where are both teams corner teams". Those questions are answerable
// from the rows already on screen, and were being answered by eye.
//
// PURE, AND ITS OWN MODULE, because the part that can quietly go wrong is not the toggling
// — it is deciding which SIDE an angle belongs to. That is a name comparison between two
// collections (an angle carries a team name from db.teams, a fixture carries home_name and
// away_name from db.fixtures), and a comparison that silently fails returns "no games"
// rather than an error. A filter that hides everything looks identical to a quiet night.

/** A run on a team's OWN corners, in the over direction.
 *
 * `under_team` is deliberately excluded. It is also a streak, and including it would mean
 * "Home streak" returning games where the home side keeps going UNDER — the opposite of
 * what anyone picking that filter is looking for. */
export const STREAK_KINDS = new Set(["over_team"]);

const norm = (s) => String(s || "").toLowerCase()
  .normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[øØ]/g, "o").replace(/[æÆ]/g, "ae").replace(/[åÅ]/g, "a")
  .replace(/[^a-z0-9]+/g, " ").trim();

/**
 * Which side of this fixture does the angle belong to — "home", "away", or null?
 *
 * LOOSE BOTH WAYS, on purpose. The two names come from different collections and are not
 * guaranteed to be byte-identical: a fixture may carry "Bodø/Glimt" where the team row
 * says "Bodo Glimt", and an exact comparison would file that angle under neither side.
 * Containment in either direction covers the ways the same club gets written down.
 *
 * Returns null rather than guessing when a name matches BOTH sides or neither. A guess
 * here puts a real angle on the wrong team, which is worse than leaving it unattributed:
 * the row would then pass a filter it should have failed.
 */
export const sideOf = (angle, fixture) => {
  const t = norm(angle?.team);
  if (!t) return null;
  const h = norm(fixture?.home);
  const a = norm(fixture?.away);
  const hit = (x) => x && (x === t || x.includes(t) || t.includes(x));
  const isHome = hit(h);
  const isAway = hit(a);
  if (isHome === isAway) return null;         // both or neither — do not guess
  return isHome ? "home" : "away";
};

/** The strong angles on one side of a fixture, optionally narrowed to certain kinds. */
export const anglesOn = (fixture, side, kinds = null) =>
  (fixture?.angles || []).filter((a) =>
    a?.strong && sideOf(a, fixture) === side && (!kinds || kinds.has(a.kind)));

/**
 * The filters offered, in the order they appear.
 *
 * Every one of these tests STRONG angles only. The board already treats "strong" as the
 * bar a fixture has to clear to be listed at all, so a filter that counted weak angles
 * would be a looser test than the thing it is filtering — it would let a game through on
 * evidence the board itself had already dismissed.
 */
export const FILTERS = [
  {
    key: "all",
    label: "All",
    hint: "Every fixture that cleared the board's bar.",
    test: () => true,
  },
  {
    key: "home_streak",
    label: "Home streak",
    hint: "The home side is on a live run of winning corners.",
    test: (f) => anglesOn(f, "home", STREAK_KINDS).length > 0,
  },
  {
    key: "away_streak",
    label: "Away streak",
    hint: "The away side is on a live run of winning corners.",
    test: (f) => anglesOn(f, "away", STREAK_KINDS).length > 0,
  },
  {
    key: "both_sides",
    label: "Both teams",
    hint: "Both sides are on a run — two corner teams in one game.",
    test: (f) => anglesOn(f, "home", STREAK_KINDS).length > 0
              && anglesOn(f, "away", STREAK_KINDS).length > 0,
  },
  {
    key: "mismatch",
    label: "Mismatch",
    hint: "One side wins corners at pace against a defence that concedes them.",
    test: (f) => (f?.angles || []).some((a) => a?.strong && a.kind === "mismatch"),
  },
  {
    key: "chase",
    label: "Chase spot",
    hint: "A side that reliably clears its line, in a game state that suits it.",
    test: (f) => (f?.angles || []).some((a) => a?.strong && a.kind === "chase"),
  },
];

export const filterByKey = (key) =>
  FILTERS.find((f) => f.key === key) || FILTERS[0];

/**
 * Apply a filter across the board's day groups, keeping the shape intact.
 *
 * DAYS ARE KEPT EVEN WHEN THEY EMPTY OUT, because the board's own rule is that an absent
 * day reads as missing data while "nothing here" is an answer. `matched` rides along per
 * day and in total so the UI can say what was hidden rather than just showing less.
 */
export const applyFilter = (board, key) => {
  const f = filterByKey(key);
  const days = (board?.days || []).map((d) => {
    const kept = (d.fixtures || []).filter((fx) => f.test(fx));
    return { ...d, fixtures: kept, before_filter: (d.fixtures || []).length };
  });
  const total = days.reduce((n, d) => n + d.fixtures.length, 0);
  const before = days.reduce((n, d) => n + d.before_filter, 0);
  return { ...board, days, matched: total, before_filter: before, filter: f.key };
};
