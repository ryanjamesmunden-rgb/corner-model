// The morning board: the chase board's best spots for a day, with the reason on every row.
//
// WHY THIS REPLACED THE STREAK SLATE. A streak row says what a team keeps doing and nothing
// else — "Kiel 5+ corners, eight in a row". That is a fact about eight games already played
// and no argument at all about the next one: who they play, whether that opponent concedes
// corners, what the model expects. Five clears can be five coin flips. A reader looking at
// a card of those has nothing to check and nothing to disagree with.
//
// A chase row carries the argument. The team's own corner average AT THIS VENUE, what the
// opponent concedes at theirs, the expected total the two produce, and how often this team
// has actually cleared the line in its last five there. That last number is a success rate
// on the exact thing being claimed, and it is the one a sceptic reaches for first.
//
// AND IT IS THE ONLY SECTION WITH A MEASURED RECORD. Chase spots are auto-logged daily and
// graded — see _snapshot_daily_picks and /api/ledger. Mismatches, value and the projections
// are not logged at all, so nothing anywhere says whether they pick winners. A card claiming
// to show "the section that performs" can only honestly be drawn from the section whose
// performance has been written down.
//
// THE ORDER IS THE BACKEND'S, DELIBERATELY. daily_pick_qualifies then daily_pick_order:
// clear the consistency bar, then rank on the model's own probability. Mirrored here rather
// than improved on, because the daily picks the ledger grades are chosen that way — a card
// ordering them differently would show a "best" game the graded record never bet, and the
// record on its header would then belong to a different set of picks than the rows under it.
//
// The backend is also explicit that its ordering is descriptive rather than predictive:
// measure_chase_board.py replayed four orderings walk-forward and all four scored the same
// as random. So the board is a FILTER — spots that clear the line reliably — and the card
// must not dress its order up as a ranking of confidence it has not earned.

/** The backend's own bar, restated. Kept in step with DAILY_MIN_* in server.py. */
export const MIN_VENUE_GAMES = 4;
export const MIN_CONSISTENCY = 0.8;

/** Fewer than this is not a board, it is a handful of spots. */
export const MIN_SLATE_ROWS = 3;
/** Ten rows is what the story-shaped card holds while staying readable on a phone. */
export const MAX_SLATE_ROWS = 10;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const one = (v) => {
  const n = num(v);
  return n === null ? null : Math.round(n * 10) / 10;
};

/**
 * Does this spot clear the quality bar? Mirrors server.daily_pick_qualifies.
 *
 * A FILTER ON CORROBORATION, NOT A CLAIM ABOUT BEATING A PRICE — the backend's own words.
 * Four games at the venue minimum, because a "5 of 5" off two games is not a rate, and
 * four of the last five clears.
 */
export const qualifies = (c = {}) => {
  const of = num(c.consistency_of) || 0;
  if (of < MIN_VENUE_GAMES) return false;
  return (num(c.consistency) || 0) / of >= MIN_CONSISTENCY;
};

/** Is this a price somebody could actually take, or the model's break-even number? */
export const hasBookPrice = (c = {}) => num(c.book_odds) !== null;

/** Which day a moment falls on, on the clock the card states its times in. */
export const SLATE_TZ = "Europe/London";

export const dayKeyOf = (when, tz = SLATE_TZ) => {
  const d = when ? new Date(when) : new Date();
  if (Number.isNaN(d.getTime())) return "";
  const opts = { year: "numeric", month: "2-digit", day: "2-digit" };
  try {
    return new Intl.DateTimeFormat("en-CA", { ...opts, timeZone: tz }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-CA", opts).format(d);
  }
};

export const slateTime = (iso, tz = SLATE_TZ) => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  const opts = { hour: "2-digit", minute: "2-digit", hour12: false };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: tz }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-GB", opts).format(d);
  }
};

export const zoneLabel = (iso, tz = SLATE_TZ) => {
  const d = iso ? new Date(iso) : new Date();
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: tz, timeZoneName: "short" })
      .formatToParts(d).find((p) => p.type === "timeZoneName")?.value || "";
  } catch {
    return "";
  }
};

/**
 * One row of the board.
 *
 * THE MARKET IS THE TEAM'S OWN CORNERS, NOT THE MATCH TOTAL, and the label has to say so.
 * `line` 5 means "Kiel 5+ corners" — that team, at that venue — and a card that printed a
 * bare "5+ corners" beside a fixture would read as the match total, which is roughly twice
 * the number and a completely different bet.
 */
export const slateRow = (c = {}) => {
  const nf = c.next_fixture || {};
  const isHome = nf.is_home !== false;
  const line = num(c.line);
  const of = num(c.consistency_of) || 0;
  const hit = num(c.consistency) || 0;
  return {
    team: c.name || "",
    home: isHome ? c.name || "" : nf.opponent || "",
    away: isHome ? nf.opponent || "" : c.name || "",
    venue: isHome ? "home" : "away",
    market: line === null ? "" : `${c.name} ${line}+ corners`,
    shortMarket: line === null ? "" : `${line}+ corners`,
    line,
    leagueId: c.league_id || null,
    leagueName: c.league_name || "",
    kickoff: nf.date || null,
    time: slateTime(nf.date),
    fixtureId: nf.fixture_id || null,
    // THE ARGUMENT, which is the whole reason this board replaced the streak one.
    teamFor: one(c.team_for),
    oppConceded: one(c.opp_conceded),
    lambda: one(c.lambda),
    hit,
    of,
    // A success rate on the exact claim being made, which is the number a sceptic wants.
    consistency: of ? Math.round((hit / of) * 100) : null,
    prob: one(c.prob),
    price: hasBookPrice(c) ? num(c.book_odds) : num(c.fair_odds),
    priceKind: hasBookPrice(c) ? "book" : "fair",
    ev: hasBookPrice(c) ? one(c.ev) : null,
  };
};

/**
 * How this row earns its place, in one line.
 *
 * THE VENUE IS NAMED because every number on it is a venue split — the team's average is
 * its average AT HOME, the opponent's is what they concede AWAY. Printed without that word
 * they read as season averages, which are different numbers and a weaker argument.
 */
export const reasonFor = (r = {}) => {
  // ALWAYS ONE DECIMAL. A raw 6.0 prints as "6" beside a "5.7", which reads as a rounder,
  // softer number than the one next to it when both are measured the same way.
  const dp = (v) => (v === null || v === undefined ? null : Number(v).toFixed(1));
  const bits = [];
  const forAvg = dp(r.teamFor);
  const conc = dp(r.oppConceded);
  if (forAvg !== null) bits.push(`${forAvg} for ${r.venue}`);
  if (conc !== null) bits.push(`opp concede ${conc}`);
  if (r.of) bits.push(`cleared ${r.hit} of ${r.of}`);
  return bits.join("  ·  ");
};

/**
 * The section's own graded record, or null when there is not one worth showing.
 *
 * ROI IS REFUSED UNLESS SOMETHING WAS PRICED. server._record answers `roi: 0.0` when no
 * pick carried a price, because zero divided by nothing has to be something — and a card
 * printing "ROI 0%" would be claiming the section broke even when the truth is that nobody
 * wrote the odds down. Same trap as the units figure on the day card, one layer further out.
 */
export const recordFrom = (ledger = null) => {
  const s = ledger?.summary;
  if (!s) return null;
  const settled = num(s.settled) || 0;
  if (settled < 1) return null;
  const staked = num(s.staked) || 0;
  return {
    settled,
    won: num(s.won) || 0,
    rate: one(s.win_rate),
    // Only where a price existed. Both are null together — an ROI with no stake behind it
    // is not a smaller claim, it is a different one.
    staked,
    profit: staked > 0 ? one(s.profit) : null,
    roi: staked > 0 ? one(s.roi) : null,
    unpriced: num(s.unpriced) || 0,
  };
};

/** "won 29 of 47 · 61.7%", plus the units only where they were actually priced. */
export const recordLine = (rec = null) => {
  if (!rec) return "";
  const head = `${rec.won} of ${rec.settled} settled`
    + (rec.rate === null ? "" : `  ·  ${rec.rate}%`);
  if (rec.roi === null) return head;
  const sign = rec.profit > 0 ? "+" : "";
  return `${head}  ·  ${sign}${rec.profit}u from ${rec.staked} priced`;
};

/**
 * The day's board, or null when there is not one.
 *
 * NOT TOPPED UP WITH SPOTS THAT FAILED THE BAR. The backend says this in as many words —
 * "a thin day yields fewer than count, deliberately: the bar is absolute, and topping up
 * with spots that failed it would defeat the whole point." A card that always shows ten
 * rows is a card whose bottom rows mean nothing, and nobody reading it can tell which.
 */
export const slateFrom = ({ rows = [], ledger = null, day = null, max = MAX_SLATE_ROWS,
                            min = MIN_SLATE_ROWS } = {}) => {
  const key = day || dayKeyOf();
  const limit = Math.max(1, Math.min(MAX_SLATE_ROWS, Number(max) || MAX_SLATE_ROWS));
  const picked = (rows || [])
    .filter((c) => qualifies(c) && c?.next_fixture?.opponent
                   && dayKeyOf(c?.next_fixture?.date) === key)
    .map(slateRow)
    .filter((r) => r.market && r.home && r.away)
    // The backend's order: the model's own confidence, nothing cleverer.
    .sort((a, b) => (b.prob || 0) - (a.prob || 0))
    .slice(0, limit);
  // `min` IS A CALLER'S FLOOR, NOT A LOOSENING OF THE BAR. Every row here has already
  // cleared `qualifies`; this only says how many of them make a post worth sending. Three
  // is right for a card that is nothing but this board — one row is not a board. The day
  // card passes 1, because there the chase section sits above mismatches, streaks and
  // prices, and dropping a spot that cleared the bar for want of company would hide it.
  if (picked.length < Math.max(1, Number(min) || MIN_SLATE_ROWS)) return null;

  const priced = picked.filter((r) => r.priceKind === "book").length;
  return {
    day: key,
    rows: picked,
    n: picked.length,
    priced,
    zone: zoneLabel(picked[0]?.kickoff),
    record: recordFrom(ledger),
  };
};

/**
 * The post that carries the card: every row, its reason, and a link to the page it came
 * from. The links are the part that does the work — a graphic is a claim a reader has to
 * take on trust, and the fixture page is the answer to "says who".
 */
export const slatePost = ({ slate = null, site = "", heading = "" } = {}) => {
  if (!slate) return "";
  const head = heading || `TOP ${slate.n} TODAY  ·  chase board`;
  const rec = recordLine(slate.record);
  const lines = slate.rows.map((r, i) => {
    const price = r.price === null ? ""
      : r.priceKind === "book" ? `  @ ${r.price}` : `  fair ${r.price}`;
    const link = site && r.fixtureId ? `\n   ↳ ${site}/fixture/${r.fixtureId}` : "";
    return `${i + 1}. ${r.home} v ${r.away}${r.time ? `  ${r.time}` : ""}\n`
      + `   ${r.market}${price}\n`
      + `   ${reasonFor(r)}${link}`;
  });
  const tail = slate.priced === slate.n ? ""
    : "\n\nPrices marked fair are the model's break-even number, not an offer — shop your own.";
  return `${head}${rec ? `\n${rec}` : ""}\n\n${lines.join("\n\n")}${tail}`;
};
