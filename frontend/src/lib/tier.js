// What LEVEL a team plays at, for the screens that rank teams across leagues.
//
// The board sorts every side in the database by corners won, which puts a National
// League team directly above a Premier League one with nothing to tell them apart. Six
// corners a game in the fifth tier is not the same achievement as six in the first, and
// until now the row could not say which it was.
//
// WHAT THIS IS NOT: a cross-country strength rating. England's Championship is stronger
// than several of the top flights in this database, so "T2" does not mean weaker than
// any "T1" elsewhere. It answers "what level is this, in its own country?" — and the
// label deliberately reads as a division marker rather than a rating, because a number
// that looked like strength would get used as one.
//
// Building a real cross-border strength number needs data this app does not hold —
// coefficients, squad values, cross-competition results. Deriving one from corner counts
// would be a confident-looking figure with nothing behind it, so there isn't one.

const LABELS = {
  1: { short: "T1", name: "Top flight" },
  2: { short: "T2", name: "2nd tier" },
  3: { short: "T3", name: "3rd tier" },
  4: { short: "T4", name: "4th tier" },
  5: { short: "T5", name: "5th tier" },
};

// One coercion, used by the labels AND the filters. Object keys are strings in JS, so
// LABELS["1"] resolves happily — which without this would render a badge for a string
// tier while the strict-equality filters below rejected the same row. A field that shows
// up on screen but cannot be filtered for is worse than one that does neither.
const norm = (tier) => {
  const n = typeof tier === "number" ? tier : parseInt(tier, 10);
  return Number.isInteger(n) && LABELS[n] ? n : null;
};

export const tierLabel = (tier) => LABELS[norm(tier)]?.short || "";
export const tierName = (tier) => LABELS[norm(tier)]?.name || "";

/** Tooltip text. Names the country because the whole point is that the level is local. */
export const tierTitle = (tier, country = "") => {
  const n = tierName(tier);
  if (!n) return "";
  return country
    ? `${n} in ${country}. Level within its own country — not a strength rating comparable across borders.`
    : `${n} in its own country — not a strength rating comparable across borders.`;
};

// Muted for the top flight and progressively dimmer below it. Deliberately NOT a
// red/green scale: colour that reads as good-versus-bad would turn a division marker
// into the strength verdict this file refuses to make.
export const tierClass = (tier) => (
  tier === 1 ? "border-border/60 text-muted-foreground"
    : tier === 2 ? "border-border/60 text-muted-foreground/80"
    : "border-border/50 text-muted-foreground/60"
);

export const TIER_FILTERS = [
  { v: "any", l: "Any level", test: () => true },
  { v: "1", l: "Top flight only", test: (r) => norm(r?.tier) === 1 },
  { v: "1-2", l: "Top two tiers", test: (r) => [1, 2].includes(norm(r?.tier)) },
  // A row whose tier is unknown is EXCLUDED here rather than swept into the bottom
  // bucket: "third tier and below" is a claim, and it should not be made about a team
  // whose level nobody recorded.
  { v: "3+", l: "Third tier and below", test: (r) => (norm(r?.tier) ?? 0) >= 3 },
];

export const tierFilter = (key) =>
  (TIER_FILTERS.find((t) => t.v === key) || TIER_FILTERS[0]).test;
