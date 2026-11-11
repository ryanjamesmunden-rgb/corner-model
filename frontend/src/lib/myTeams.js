// My Teams: how the two lists are ranked, and how a row reads.
//
// EXTRACTED SO IT CAN BE TESTED. jest cannot resolve react-router from inside a page, so
// nothing asserted about the screen can live beside it — and the parts worth asserting
// here are judgements rather than layout: when a side counts as in form, when a fixture
// is worth calling soft, and above all when a row may show an edge at all.

// Each sort is named for the question it answers, not the field it reads. The hints are
// shown under the control, because "form" and "average" sound like the same thing and are
// not: one is the change, the other is the level.
export const SORTS = [
  { v: "form", l: "Best form", hint: "biggest lift over their own season average" },
  { v: "run", l: "Longest run", hint: "most games in a row at their usual line" },
  { v: "average", l: "Most corners", hint: "highest average over the last five" },
  { v: "schedule", l: "Softest fixtures", hint: "opponents who concede the most" },
  { v: "next", l: "Kicking off first", hint: "soonest game at the top" },
];

export const SOURCES = [
  { v: "all", l: "All" },
  { v: "favourites", l: "Favourites" },
  { v: "tracking", l: "Tracking" },
];

export const VIEWS = [
  { v: "teams", l: "Teams" },
  { v: "fixtures", l: "Fixtures" },
];

// A LIFT OF ONE CORNER A GAME IS THE BAR, matching _in_form on the server. Below that a
// "trend" is a different opponent rather than a different team, and the whole list would
// read as hot.
export const FORM_BAR = 1.0;

export const formTone = (delta) => {
  if (typeof delta !== "number") return { tone: "unknown", l: "no form yet" };
  if (delta >= FORM_BAR) return { tone: "hot", l: `+${delta.toFixed(1)} on their average` };
  if (delta <= -FORM_BAR) return { tone: "cold", l: `${delta.toFixed(1)} on their average` };
  return { tone: "steady", l: "around their average" };
};

// Mirrors _schedule_label's thresholds (1.10 / 0.90) so the words and the server's own
// classification cannot drift apart.
export const scheduleTone = (label) => {
  if (label === "soft") return { tone: "hot", l: "soft run ahead" };
  if (label === "tough") return { tone: "cold", l: "tough run ahead" };
  if (!label) return { tone: "unknown", l: "fixtures unrated" };
  return { tone: "steady", l: "average run ahead" };
};

// A PRICE THE MODEL EFFECTIVELY WROTE ITSELF IS NOT A PRICE. The seeders generate
// `fair_odds * uniform(0.90, 1.15)`, so an EV measured against one of those is the model
// reading its own noise — and an unstamped document predates the stamp or came from a
// seeder, so "unknown" must not read as "real" either.
const REAL_PRICE_SOURCES = new Set(["manual", "api"]);

/**
 * What a fixture row may say about value, and nothing it may not.
 *
 * Three outcomes, deliberately distinct:
 *   priced   a real stored price, so the edge can be stated
 *   model    the model's own side only — no price stored to measure against
 *   none     no projection at all (no line yet, or the sides cannot be modelled)
 *
 * "No price stored" is NOT "no edge". Collapsing the two is how a blank row starts
 * reading as a negative verdict on a game nobody has priced.
 */
export const betSummary = (game) => {
  const p = game?.projection;
  if (!p || typeof p.prob !== "number") {
    return { kind: "none", note: "not modelled yet" };
  }
  const base = {
    line: p.line, prob: p.prob, fair: p.fair_odds,
    lambda: p.lambda,
  };
  const real = REAL_PRICE_SOURCES.has(p.odds_source);
  if (!real || typeof p.book_odds !== "number" || typeof p.ev !== "number") {
    return { ...base, kind: "model", note: "no price stored" };
  }
  return { ...base, kind: "priced", book: p.book_odds, ev: p.ev, source: p.odds_source };
};

// Matches the EV floor the bot sends on, so a row this screen highlights is a row the
// channel would have mentioned.
export const EV_BAR = 5.0;

export const evTone = (ev) => {
  if (typeof ev !== "number") return "unknown";
  if (ev >= EV_BAR) return "hot";
  if (ev <= -EV_BAR) return "cold";
  return "steady";
};

/** Teams with nothing scheduled, so the screen can say so instead of just being short. */
export const idleTeams = (teams) =>
  (teams || []).filter((t) => !t.missing && (t.next || []).length === 0);

/** Follows pointing at a team that has stopped syncing — a maintenance note, not a rank. */
export const missingTeams = (teams) => (teams || []).filter((t) => t.missing);

/**
 * One line summarising what is applied, for the collapsed control bar on a phone.
 * Only the choices that change what you are looking AT are spelled out.
 */
export const filterSummary = ({ view, source, sort }) => {
  const parts = [
    VIEWS.find((v) => v.v === view)?.l,
    SOURCES.find((s) => s.v === source)?.l,
    SORTS.find((s) => s.v === sort)?.l,
  ];
  return parts.filter(Boolean).join(" · ");
};
