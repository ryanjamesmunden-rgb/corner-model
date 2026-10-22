/**
 * The daily facts as a picture: one number big enough to stop a scroll, and the sentence
 * that makes it mean something.
 *
 * WHY A SEPARATE MODULE FROM oddityPosts. That file writes PROSE — sentences that have to
 * read correctly in a row, inside a character budget, with a link on the end. A card is
 * the opposite shape: one hero figure, a unit under it, and two short lines of support.
 * Trying to derive the first from the second means parsing English back into numbers, and
 * the numbers were right there in `facts` the whole time. So both read the same findings
 * and neither reads the other.
 *
 * THE HERO IS THE NUMBER THE FACT IS ABOUT, which is not always the biggest one present.
 * `venue` is a gap between two averages and the gap is the point, not the home figure;
 * `futility` is a pair and neither half means anything alone. Each key says what its own
 * claim is rather than a rule guessing from the shape of the data.
 *
 * EVERY CARD CARRIES ITS DENOMINATOR where one exists. "Nobody has a higher floor" is a
 * claim about a population, and a card that drops the population is a bigger claim than
 * the post it came from — the one failure mode that would make these worse than the text
 * they replace.
 */

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const dec = (v) => {
  const n = num(v);
  return n === null ? null : n.toFixed(1);
};

const int = (v) => {
  const n = num(v);
  return n === null ? null : Math.round(n);
};

const group = (v) => {
  const n = num(v);
  return n === null ? null : n.toLocaleString("en-GB");
};

/** "Barnsley" — the subject, however the finding spells it. */
const team = (f = {}) => f.team || f.name || "";

const vs = (f = {}) => (f.opponent ? `v ${f.opponent}` : "");

const onDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
};

/**
 * key -> card. Returns null when the finding cannot support the claim, exactly as the
 * post builders do: a card with a blank hero is worse than no card.
 */
const SPECS = {
  rout: (f, pool) => {
    const margin = int(f.margin);
    if (margin === null) return null;
    return {
      hero: `+${margin}`,
      unit: "corner margin",
      headline: "The most one-sided count on record",
      detail: `${team(f)} ${f.corners_for}, ${f.opponent} ${f.corners_against}`,
      meta: [onDate(f.date), group(pool?.games) ? `${group(pool.games)} games on record` : ""],
      tone: "primary",
    };
  },

  haul: (f, pool) => {
    const n = int(f.corners_for);
    if (n === null) return null;
    const goals = int(f.goals_for);
    return {
      hero: String(n),
      unit: "corners, one game",
      headline: "The biggest haul here",
      detail: `${team(f)} ${vs(f)}${goals === null ? "" : ` — and ${goals} goal${goals === 1 ? "" : "s"}`}`,
      meta: [onDate(f.date), group(pool?.games) ? `${group(pool.games)} games on record` : ""],
      tone: "primary",
    };
  },

  wildest: (f, pool) => {
    const n = int(f.total);
    if (n === null) return null;
    return {
      hero: String(n),
      unit: "corners in one match",
      headline: "The busiest 90 minutes on the site",
      detail: `${team(f)} ${f.corners_for}, ${f.opponent} ${f.corners_against}`,
      meta: [onDate(f.date), group(pool?.games) ? `busiest of ${group(pool.games)}` : ""],
      tone: "primary",
    };
  },

  floor: (f, pool) => {
    const n = int(f.floor);
    if (n === null) return null;
    return {
      hero: String(n),
      unit: "their WORST return",
      headline: "The highest floor on the site",
      detail: `${team(f)} — ${f.games} games, never fewer`,
      meta: [pool?.teams ? `of ${group(pool.teams)} teams` : "", "not an average"],
      tone: "solid",
    };
  },

  ceiling: (f) => {
    const n = int(f.ceiling);
    if (n === null) return null;
    return {
      hero: String(n),
      unit: "their BEST night",
      headline: "The lowest ceiling on the site",
      detail: `${team(f)} have never won more, in ${f.games} games`,
      meta: ["most sides clear it by half-time"],
      tone: "dim",
    };
  },

  venue: (f, pool) => {
    const gap = dec(f.gap);
    if (gap === null) return null;
    return {
      hero: gap,
      unit: "corner home/away gap",
      headline: f.stronger === "away" ? "Better away than at home" : "A different side on the road",
      detail: `${team(f)} — ${dec(f.home_avg)} at home, ${dec(f.away_avg)} away`,
      meta: [pool?.teams ? `widest of ${group(pool.teams)} teams` : "", "same eleven players"],
      tone: "primary",
    };
  },

  perfect: (f) => {
    const g = int(f.games);
    if (g === null) return null;
    return {
      hero: `${g}/${g}`,
      unit: "games out-cornering them",
      headline: "Never once out-cornered",
      detail: `${team(f)} — ${dec(f.for_avg)} a game against ${dec(f.against_avg)}`,
      meta: ["not one drawn count"],
      tone: "solid",
    };
  },

  futility: (f) => {
    const corners = dec(f.for_avg);
    const goals = dec(f.goals_avg);
    if (corners === null || goals === null) return null;
    return {
      // A PAIR, NOT A FIGURE. The claim is the ratio between them; either number alone
      // is unremarkable, and picking one would print the dull half.
      hero: `${corners} : ${goals}`,
      unit: "corners to goals, per game",
      headline: "All that territory, nothing to show",
      detail: `${team(f)}${f.games ? ` — over ${f.games} games` : ""}`,
      meta: ["among the biggest corner-winners here"],
      tone: "dim",
    };
  },

  leaky: (f, pool) => {
    const n = dec(f.against_avg);
    if (n === null) return null;
    return {
      hero: n,
      unit: "corners conceded a game",
      headline: "The leakiest defence on the site",
      detail: `${team(f)}${f.games ? ` — ${int(num(f.against_avg) * f.games)} in ${f.games} games` : ""}`,
      meta: [pool?.teams ? `most of ${group(pool.teams)} teams` : "",
             dec(f.for_avg) ? `they win ${dec(f.for_avg)} themselves` : ""],
      tone: "dim",
    };
  },

  leagues: (f) => {
    const gap = dec(f.gap);
    if (gap === null || !f.top || !f.bottom) return null;
    return {
      hero: gap,
      unit: "corners between two leagues",
      headline: "Same sport, different game",
      detail: `${f.top.league} ${dec(f.top.per_match)} — ${f.bottom.league} ${dec(f.bottom.per_match)}`,
      meta: [f.leagues ? `across ${f.leagues} competitions` : ""],
      tone: "primary",
    };
  },

  punching: (f) => {
    const t = f.team || {};
    const b = f.beats || {};
    const mine = dec(t.for_avg);
    if (mine === null || dec(b.for_avg) === null) return null;
    return {
      hero: mine,
      unit: "corners a game",
      headline: `More than anyone in ${b.league}`,
      detail: `${team(t)}${t.league ? ` (${t.league})` : ""} — ${b.league}'s best, ${b.team}, make ${dec(b.for_avg)}`,
      meta: [f.beaten_leagues > 1 && f.of_top_flights
        ? `would top ${f.beaten_leagues} of ${f.of_top_flights} top flights here` : ""],
      tone: "solid",
    };
  },
};

/**
 * One post -> one card, or null.
 *
 * Takes the POST rather than the raw finding so the card and the tweet can never disagree
 * about which fact was chosen on a given day: oddityPosts already did the selecting,
 * rotating and one-club-each, and this follows it rather than repeating it.
 */
export const oddityCard = (post, { survey = {} } = {}) => {
  if (!post?.key) return null;
  const spec = SPECS[post.key];
  if (!spec) return null;
  const card = spec(post.facts || {}, survey?.pool || {});
  if (!card || !card.hero) return null;
  return {
    key: post.key,
    ...card,
    meta: (card.meta || []).filter(Boolean),
    // Kept so a caller can post the picture and the words together without rebuilding
    // the sentence from the card and getting a different one.
    text: post.text || "",
  };
};

/** The day's posts as cards, dropping any the findings cannot support. */
export const oddityCards = (posts = [], opts = {}) =>
  posts.map((p) => oddityCard(p, opts)).filter(Boolean);

export const CARD_KEYS = Object.keys(SPECS);
