// Turning a block of bookmaker text into stored prices, across MANY fixtures at once.
//
// WHY THIS IS ITS OWN MODULE. The single-fixture version lives inline in FixtureDetail and
// has worked for a while, but it only ever answers "which market is this line?" — the
// fixture is whichever page you are on. Pricing a weekend that way means opening eight
// pages, and prices that are annoying to enter do not get entered, which is how a value
// board ends up with nothing to measure value against.
//
// So this adds the second question — "which GAME is this line?" — and keeps both pure, so
// the routing can be tested against the kind of mess a bookmaker's page actually produces
// rather than by pasting into a browser and squinting.
//
// NOTHING IS GUESSED. A price line that cannot be matched to a fixture is returned as an
// unmatched row rather than dropped or attached to whatever came last. A silent drop is
// how someone ends up believing a game is priced when it is not, and betting off a board
// that quietly excluded it.

// Letters a bookmaker will not print. NFD strips accents that decompose (é -> e), but the
// Nordic letters do not decompose at all, and those are exactly the leagues this site
// covers most: Bodø/Glimt is listed as "Bodo Glimt" everywhere and would otherwise never
// match its own fixture.
const FOLD = { ø: "o", æ: "ae", å: "a", ð: "d", þ: "th", ß: "ss", đ: "d", ł: "l" };

/** Lowercased, de-accented, folded — the form both sides of a name match get compared in. */
export const fold = (s) => String(s || "").toLowerCase()
  .normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[øæåðþßđł]/g, (c) => FOLD[c] || c);

/** Loose containment match: "Club Brugge KV" in "club brugge 5+ 1.40". */
export const nameHit = (raw, name) => {
  if (!name) return false;
  const low = fold(raw);
  const n = fold(name);
  if (!n) return false;
  if (low.includes(n)) return true;
  // Bookmakers shorten. "Bodø/Glimt" appears as "Bodo Glimt"; "Operario-PR" as "Operario".
  // The first word is the part that survives, so it is what gets matched on — but only if
  // it is long enough to mean something. "FC" or "AC" would match half a league.
  const first = n.split(/[\s/\-–]+/)[0];
  return first.length >= 4 && low.includes(first);
};

/**
 * One line of bookmaker text -> which market and what price, or null.
 *
 * Understands "Over 4.5 1.80", "5+ 1.80", "Total 10.5 1.90". A whole number or a trailing
 * plus means N-or-more, which is stored as Over (N - 0.5) — the same convention the
 * markets use, so "5+" and "Over 4.5" land on the same key rather than two.
 */
export const parsePriceLine = (raw, { homeName, awayName, target = "home",
                                      forceGroup = null } = {}) => {
  const low = fold(raw);
  // forceGroup exists for a HEADING that also carries a price. A heading names both
  // sides, so name-routing on it is meaningless — "Club Brugge v Antwerp 10 1.90" would
  // route to whichever team the matcher happened to test first, and that is a coin flip
  // deciding which market a real price lands on.
  let group = forceGroup || target;
  if (!forceGroup) {
    if (nameHit(raw, homeName)) group = "home";
    else if (nameHit(raw, awayName)) group = "away";
    else if (/\btotal\b|\bmatch\b|\bgame\b/.test(low)) group = "total";
  }

  const nums = raw.match(/\d+\.?\d*/g);
  if (!nums || nums.length < 2) return null;
  let line = parseFloat(nums[0]);
  const price = parseFloat(nums[nums.length - 1]);
  // A price is a price. Below evens it is not one, and 1.0 exactly is how a blank cell
  // scrapes — both would otherwise be stored as a real number to bet into.
  if (!(price > 1)) return null;
  if (/\d+\s*\+/.test(raw) || Number.isInteger(line)) line -= 0.5;
  if (!(line > 0)) return null;
  return { group, line, price, key: `${group}_over_${line}` };
};

/** Does this line NAME a fixture rather than price one? */
export const matchFixture = (raw, fixtures = []) => {
  // Both sides named is a heading — "Club Brugge v Antwerp". One side is ambiguous
  // between a heading and a team-corners price line, so it only counts as a heading when
  // the line carries no price at all.
  const hasPrice = (raw.match(/\d+\.?\d*/g) || []).length >= 2;
  for (const f of fixtures) {
    const h = nameHit(raw, f.home_name);
    const a = nameHit(raw, f.away_name);
    if (h && a) return f;
    if ((h || a) && !hasPrice) return f;
  }
  return null;
};

// The ladders the model actually prices, mirrored from TOTAL_LINES and TEAM_LINES in
// server.py. Without this, any two numbers on a line become a price: pasting a block that
// includes "Shots on target 4.5 2.20" stored a corners total of 4.5 at 2.20 — a market
// that does not exist, on a board that would then show an edge on it. Found by rendering
// the page and pasting a realistic block, not by reading the parser.
const TOTAL_LINES = [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5];
const TEAM_LINES = [2.5, 3.5, 4.5, 5.5, 6.5];
export const STANDARD_KEYS = [
  ...TOTAL_LINES.map((l) => `total_over_${l}`),
  ...TEAM_LINES.flatMap((l) => [`home_over_${l}`, `away_over_${l}`]),
];

/**
 * A whole paste -> the odds to store per fixture, plus what could not be placed.
 *
 * A heading switches which game the following prices belong to. Before any heading there
 * is no current fixture, so those lines are unmatched rather than guessed at — the first
 * thing in a paste is as likely to be a column header as a price.
 *
 * `keysFor` is the set of market keys that may be written, and it DEFAULTS TO THE REAL
 * LADDERS rather than to "anything". That default is the whole guard: a caller who forgets
 * to pass one still cannot store a market the model does not price. Pass `() => null` to
 * turn it off deliberately.
 */
export const parseBulk = (text, fixtures = [], keysFor = () => STANDARD_KEYS) => {
  const lines = String(text || "").split(/\n|;/).map((s) => s.trim()).filter(Boolean);
  const byFixture = new Map();
  const unmatched = [];
  let current = null;

  for (const raw of lines) {
    const fx = matchFixture(raw, fixtures);
    if (fx) {
      current = fx;
      // A heading can also carry a price — "Club Brugge v Antwerp 10.5 1.90" — so it
      // falls through rather than being consumed.
      const parsedOnHeading = parsePriceLine(raw, { forceGroup: "total" });
      if (!parsedOnHeading) continue;
    }
    if (!current) { unmatched.push(raw); continue; }
    const heading = fx === current && matchFixture(raw, fixtures) === current;
    const parsed = parsePriceLine(raw, heading
      ? { forceGroup: "total" }
      : { homeName: current.home_name, awayName: current.away_name, target: "total" });
    if (!parsed) { unmatched.push(raw); continue; }
    const allowed = keysFor(current);
    if (allowed && !allowed.includes(parsed.key)) { unmatched.push(raw); continue; }
    const got = byFixture.get(current.fixture_id)
      || { fixture: current, odds: {}, count: 0 };
    got.odds[parsed.key] = parsed.price;
    got.count += 1;
    byFixture.set(current.fixture_id, got);
  }
  return { entries: [...byFixture.values()], unmatched };
};
