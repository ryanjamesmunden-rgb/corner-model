// The weekend's EV+ calls as one clip — and the four rules that decide what is on it.
//
// WHAT THIS IS FOR. resultsReel.js animates what HAPPENED; this animates what is being
// BACKED, which is the harder half to publish honestly. A results reel can only
// cherry-pick by choosing its period, and that file's answer — carry the overall record
// beside the week — covers it. A tips reel has no results to cherry-pick yet, so every
// hazard in it is about SELECTION: which prices get on the card, which rung of a fixture's
// ladder, and whether the price quoted is one the viewer could actually have taken.
//
// THE FOUR RULES, each because breaking it is the normal thing to do:
//
//   1. ONE PICK PER FIXTURE. The ledger is unambiguous about this: fixtures that went out
//      with three or more angles on them returned -4.4% over 112u, while fixtures with one
//      or two returned +13.0% over 512.5u. Three rungs of one ladder is one opinion sold
//      three times, and when the opinion is wrong it loses three times. So a fixture
//      contributes its best band rung and nothing else.
//
//   2. THE BAND IS THE MEASURED ONE, AND IT IS NAMED ON THE CARD. 5+ and 6+ team corner
//      lines are +48.47u over 90 settled bets; 4+ and below are -12.90u over 29; 7+ has
//      12 bets on it, which is not a sample. The band is therefore a FILTER, chosen on
//      that evidence, and a filter that is not stated reads as "these were the best bets
//      on the board" — which is a different and untrue claim. `bandLabel` goes on the
//      card for the same reason resultsReel's `context` does.
//
//   3. A PRICE IS A BOOK PRICE AND IT NAMES ITS BOOK, or the row does not exist. betsCard
//      already refuses a row without a real price (see its rule 3, and priceSource.js for
//      why "manual" stopped being the test). This goes one further and requires the
//      BOOKMAKER, because the feed takes the best of 33 books: a +19% edge at a book the
//      viewer has no account with is not a bet they can place, and quoting it as though it
//      were is the most plausible way this clip could mislead somebody.
//
//   4. THE PRICES HAVE A TIMESTAMP ON THE FACE OF THE CLIP. A video is watched hours after
//      it is made and lives on a feed for weeks. Backend FEED_PRICE_STALE_HOURS is 12, so
//      a price on this card is a price that EXISTED, not one that is available — and the
//      only honest way to publish that is to say when it was read and tell the viewer to
//      check. `pricedNote` is not optional.
//
// ORDER AND TRIM, which are a pair. The SELECTION is by edge — the card is a shortlist and
// says so — but the DISPLAY is kick-off order, because the clip's job is to tell somebody
// what is about to go off, and a list sorted by edge buries the 12:30 game under four
// evening ones. The trim therefore drops the smallest edges and reports the count in
// `more`, rather than dropping the games furthest away and quietly becoming a different
// weekend.
import { postDate, postTime, postHeader, POST_TZ } from "./shareText.js";
import { slipZoneLabel } from "./dailySlip.js";
import { isRealPrice } from "./priceSource.js";
import { headlineOf, periodOf } from "./recordCard.js";

export { POST_TZ };

/**
 * The plus-lines this clip will carry.
 *
 * Expressed as plus-lines (5, 6) rather than as stored lines (4.5, 5.5) because that is
 * how the ledger splits and how the band was measured. `bandLines` converts.
 */
export const BAND = [5, 6];

/** Beyond this the rows go past too fast to read on a phone. */
export const MAX_TIP_ROWS = 8;
/** Fewer than this is a message, not a clip. */
export const MIN_TIP_ROWS = 2;

/** The floor the shortlist is cut at, in EV percent. Matches the bot's own. */
export const MIN_TIP_EV = 5.0;

/** Only a team line can be in the band: a match total of 5 corners is not the same bet. */
export const TEAM_GROUPS = new Set(["home", "away"]);

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const ms = (iso) => {
  const t = new Date(iso || "").getTime();
  return Number.isFinite(t) ? t : 0;
};

/**
 * 4.5 -> 5. The plus-line a stored line is a bet on.
 *
 * `Math.trunc(line) + 1` rather than `Math.ceil`, which is the same answer on 4.5 and the
 * WRONG one on a whole number: ceil(5) is 5, so a line stored as 5 would be read as the
 * 5+ bet when "over 5" is the 6+ bet. The backend settles on `int(line) + 1`
 * (server.build_markets) and this has to agree with it or the band filter selects rungs
 * the ledger measured under a different name.
 */
export const plusOf = (line) => {
  const n = num(line);
  return n === null ? null : Math.trunc(n) + 1;
};

/** The stored lines a band of plus-lines corresponds to: [5, 6] -> [4.5, 5.5]. */
export const bandLines = (band = BAND) => band.map((p) => p - 0.5);

/**
 * "5+ and 6+" / "5+, 6+ and 7+" — the band, said the way the ledger splits it.
 *
 * The CARD gets this and the ROWS get `Over 4.5`, which looks inconsistent and is not: the
 * band is a category and the bet is a line, and the two are written the way each is
 * actually said.
 */
export const bandLabel = (band = BAND) => {
  const plus = [...band].sort((a, b) => a - b).map((p) => `${p}+`);
  if (plus.length <= 1) return plus[0] || "";
  return `${plus.slice(0, -1).join(", ")} and ${plus[plus.length - 1]}`;
};

/**
 * "Over 4.5" — how the line is written on the clip and in the caption.
 *
 * NOT `plusLine` from shareText.js, which renders "5+". Both name the same bet and this
 * one is the form the channel actually posts in, confirmed against a real post:
 * "🚩 Over 9.5 Asian Corner Line". The plus form is kept for the band label above, where
 * it is the ledger's own vocabulary.
 */
export const overLabel = (line) => {
  const n = num(line);
  return n === null ? "" : `Over ${n.toFixed(1)}`;
};

/** "Tondela Over 4.5 corners" — the bet, in one line. */
export const tipLabel = (rung = {}, homeName = "", awayName = "") => {
  const over = overLabel(rung.line);
  if (!over) return "";
  if (!TEAM_GROUPS.has(rung.group)) return `${over} match corners`;
  const team = rung.group === "home" ? homeName : awayName;
  return [team, over, "corners"].filter(Boolean).join(" ");
};

/** Which side of the fixture the bet is on, or "" for a match total. */
export const subjectOf = (rung = {}, homeName = "", awayName = "") =>
  (rung.group === "home" ? homeName : rung.group === "away" ? awayName : "");

/**
 * Is this rung publishable at all? Rule 3, in one place.
 *
 * Returns the REASON it is not, rather than a boolean, so a caller can report what it
 * dropped and why. A shortlist that came back short for an unstated reason is the failure
 * value_board's own docstring is written against — "five ways for a price to vanish, all
 * of them producing the same empty screen".
 */
// NO DEFAULT ON `rung`, deliberately. A default of `{}` only replaces `undefined`, so
// `rungFault(undefined)` would skip the guard below and come back "not_a_team_line" — a
// reason about a rung, reported for the absence of one. The two callers both pass a value
// that can legitimately be missing (`row.best` on a fixture with no priced market), and
// "no_rung" is the fault they need to be able to count.
export const rungFault = (rung, { minEv = MIN_TIP_EV, band = BAND } = {}) => {
  if (!rung || typeof rung !== "object") return "no_rung";
  if (!TEAM_GROUPS.has(rung.group)) return "not_a_team_line";
  const plus = plusOf(rung.line);
  if (plus === null || !band.includes(plus)) return "outside_band";
  if (!isRealPrice(rung.price_source)) return "no_real_price";
  const price = num(rung.book_odds);
  if (price === null || price <= 1) return "no_price";
  // THE BOOK, REQUIRED. A hand-typed price carries no book name and never will — the
  // person typing it did not record where they saw it — so this drops those too, and that
  // is deliberate: on a clip going out to people who will try to place the bet, "a price
  // existed somewhere" is not enough to publish.
  if (!rung.book) return "no_book";
  const ev = num(rung.ev);
  if (ev === null) return "no_ev";
  if (ev < minEv) return "below_floor";
  return "";
};

/**
 * Every band rung a value-board row offers, best edge first.
 *
 * `best` and `alternatives` rather than `ladder`, because /share/rows does not ask for the
 * ladder and this must not need it: value_board sorts a fixture's markets by EV and hands
 * over the top four, so a band rung worth putting on a clip is in that four or is not the
 * fixture's story.
 */
export const bandRungs = (row = {}, opts = {}) =>
  [row.best, ...(row.alternatives || [])]
    .filter((r) => r && !rungFault(r, opts))
    .sort((a, b) => (num(b.ev) || 0) - (num(a.ev) || 0));

/** One pick, reduced to what a frame shows. */
export const tipRow = (row = {}, rung = {}) => {
  const home = row.home_name || "";
  const away = row.away_name || "";
  return {
    fixture: home && away ? `${home} v ${away}` : home || away,
    home,
    away,
    team: subjectOf(rung, home, away),
    bet: tipLabel(rung, home, away),
    line: num(rung.line),
    plus: plusOf(rung.line),
    group: rung.group,
    over: overLabel(rung.line),
    league: row.league_name || "",
    leagueId: row.league_id || "",
    kickoff: row.date || null,
    day: postDate(row.date),
    time: postTime(row.date),
    price: num(rung.book_odds),
    book: rung.book || "",
    source: rung.price_source || "",
    fair: num(rung.fair_odds),
    prob: num(rung.prob),
    ev: num(rung.ev),
    lambdaTotal: num(row.lambda_total),
    // WHEN THIS PRICE WENT INTO THE DATABASE, carried per row because the clip's stamp is
    // computed from the worst of them. Unstamped documents predate the stamp and come back
    // null, which is unknown rather than recent.
    pricedAt: row.priced_at || null,
    key: `${row.fixture_id}:${rung.key}`,
  };
};

/**
 * The OLDEST price on the card, or null when any row cannot say.
 *
 * THE OLDEST AND NOT THE NEWEST, which is the whole point. Backend
 * FEED_PRICE_STALE_HOURS is 12, so what a viewer needs from a timestamp is the worst case
 * on the card — "nothing here is newer than this" is reassurance, "nothing here is older
 * than this" is the claim that matters. Stamping the clip with the freshest price would
 * describe one row and imply it of eight.
 *
 * ONE UNSTAMPED ROW DROPS THE STAMP ENTIRELY. A minimum taken over the rows that happen to
 * have a timestamp is not a minimum over the card, and a precise-looking time that quietly
 * excluded the unknown row would be worse than the generic warning it replaces.
 */
export const oldestPricedAt = (rows = []) => {
  const stamps = (rows || []).map((r) => r?.pricedAt);
  if (!stamps.length || stamps.some((s) => !s || !ms(s))) return null;
  return stamps.reduce((a, b) => (ms(b) < ms(a) ? b : a));
};

/**
 * The clip, from one /share/rows?boards=value payload — or null, when there is not one.
 *
 * `record` is the site's own settled record, passed in rather than derived here: it is the
 * honesty mechanism resultsReel.js argues for at length, and it comes off /api/results,
 * which this file has no business fetching. It is OPTIONAL and the clip still builds
 * without it, because a clip that refused to exist because a second endpoint was slow
 * would be the wrong trade — but `context` is then empty and the card draws no record,
 * rather than drawing one it does not have.
 */
export const tipsFrom = (rows = [], {
  minEv = MIN_TIP_EV, band = BAND, max = MAX_TIP_ROWS,
  now = Date.now(), join = "", record = null, pricedAt = null,
} = {}) => {
  const faults = {};
  const picks = [];
  (rows || []).forEach((row) => {
    if (!row || row.status !== "ok") {
      faults[row?.status || "no_status"] = (faults[row?.status || "no_status"] || 0) + 1;
      return;
    }
    // KICKED OFF IS CHECKED HERE TOO. value_board marks it, and the clip is built minutes
    // before it is posted and watched minutes after — a row that was live when the board
    // was read can be in play by the time this runs.
    if (ms(row.date) <= now) {
      faults.kicked_off = (faults.kicked_off || 0) + 1;
      return;
    }
    const rungs = bandRungs(row, { minEv, band });
    if (!rungs.length) {
      // WHY THIS FIXTURE IS NOT ON THE CLIP, from the best rung it had. Counting it as one
      // undifferentiated "dropped" would hide the difference between a weekend with no
      // band prices and one where every band price was below the floor.
      const why = rungFault(row.best, { minEv, band }) || "outside_band";
      faults[why] = (faults[why] || 0) + 1;
      return;
    }
    // RULE 1, HERE AND NOWHERE ELSE. One fixture, one pick, its biggest band edge.
    picks.push(tipRow(row, rungs[0]));
  });

  if (picks.length < MIN_TIP_ROWS) return { reel: null, faults, eligible: picks.length };

  // Selected by edge, shown in kick-off order — see the note at the top of this file.
  const byEv = [...picks].sort((a, b) => (b.ev || 0) - (a.ev || 0));
  const kept = byEv.slice(0, Math.max(MIN_TIP_ROWS, max));
  const reelRows = kept.sort((a, b) => ms(a.kickoff) - ms(b.kickoff));
  const overall = headlineOf(record || {});
  const stamp = pricedAt || oldestPricedAt(reelRows);

  return {
    reel: {
      rows: reelRows,
      n: reelRows.length,
      more: Math.max(0, picks.length - reelRows.length),
      band: [...band].sort((a, b) => a - b),
      bandLabel: bandLabel(band),
      minEv,
      bestEv: Math.max(...reelRows.map((r) => r.ev || 0)),
      leagues: new Set(reelRows.map((r) => r.league).filter(Boolean)).size,
      period: periodOf(reelRows.map((r) => ({ kickoff: r.kickoff }))),
      zone: slipZoneLabel(reelRows[0]?.kickoff),
      // RULE 4. The worst-case age of the prices, and the instruction that follows from it.
      pricedAt: stamp || null,
      pricedNote: stamp
        ? `Oldest price here read ${postTime(stamp)} ${slipZoneLabel(stamp)}`
          + " — check before backing"
        : "Prices move — check before backing",
      // RULE 2 and RULE 3, on the face of the card.
      basis: `${bandLabel(band)} team corner lines, best book price, edge over ${minEv}%`,
      context: overall ? `${overall.big} overall` : "",
      legal: "18+ · begambleaware.org · Not advice · Past results do not predict future ones",
      join: join || "",
    },
    faults,
    eligible: picks.length,
  };
};

/**
 * How much of the clip is on screen at `progress` (0..1).
 *
 * NO TALLY BEAT, which is the one structural difference from resultsReel: there is nothing
 * settled to count, and a number on this card would have to be a projection dressed as a
 * result. The beats are the rows arriving and then the end card.
 */
export const END_SHARE = 0.24;

export const tipsAt = (reel = null, progress = 0) => {
  if (!reel || !reel.n) return { shown: 0, end: 0, growth: 1 };
  const p = Math.max(0, Math.min(1, Number(progress) || 0));
  const hasEnd = Boolean(reel.join || reel.context);
  const endShare = hasEnd ? END_SHARE : 0;
  const rowsEnd = 1 - endShare;
  if (p >= rowsEnd) {
    // Pinned at the top, for the reason reelAt spells out: (1 - 0.76) / 0.24 lands a hair
    // under 1 in binary floating point, on the one frame that matters most — the held
    // final frame, which is also the still.
    return { shown: reel.n, growth: 1,
             end: endShare ? (p >= 1 ? 1 : Math.min(1, (p - rowsEnd) / endShare)) : 0 };
  }
  const slot = (p / rowsEnd) * reel.n;
  return {
    shown: Math.min(reel.n, Math.floor(slot) + 1),
    end: 0,
    // The newest row's edge bar runs out as it lands; everything behind it sits at 1,
    // because a list where every line is still moving is a list nobody can read mid-clip.
    growth: Math.max(0, Math.min(1, (slot - Math.floor(slot)) * 2)),
  };
};

/**
 * The caption, in the channel's own hand.
 *
 * THE FORMAT IS THE ONE THE CHANNEL ACTUALLY POSTS, pasted by its owner:
 *
 *   📅 Monday 9th November
 *   🇵🇹 Segunda Liga @ 8:15pm
 *   🏟️ Torreense v União de Leiria
 *   🚩 Over 9.5 Asian Corner Line
 *   📈 [1.95] via Bet365
 *   📊 Model price: 1.76 (57%) | EV: +11.0%
 *
 * AND THERE IS NO STAKE LINE. telegramPick renders one because a VIP call is a call; this
 * is the best prices on the board published ahead of the weekend, which the owner is
 * explicit is not a tip: "no stake as it's not a tip". A unit size on it would make it one.
 *
 * `postHeader` is reused rather than rewritten so the day, the flag and the clock agree
 * with every other post the app sends — see its own note on why two copies of three lines
 * is a bug waiting to happen.
 */
export const tipsPost = ({ reel = null, site = "", heading = "" } = {}) => {
  if (!reel || !reel.n) return "";
  const out = [heading || `Best EV+ corner prices — ${reel.period}`, ""];
  reel.rows.forEach((r) => {
    out.push(...postHeader({
      fixture: { date: r.kickoff, league_id: r.leagueId, league_name: r.league,
                 home_name: r.home, away_name: r.away },
    }));
    out.push(`🚩 ${r.bet}`);
    out.push(`📈 [${r.price.toFixed(2)}]${r.book ? ` via ${r.book}` : ""}`);
    const pct = r.prob != null ? ` (${Math.round(r.prob)}%)` : "";
    const ev = r.ev != null ? ` | EV: ${r.ev > 0 ? "+" : ""}${r.ev.toFixed(1)}%` : "";
    if (r.fair != null) out.push(`📊 Model price: ${r.fair.toFixed(2)}${pct}${ev}`);
    out.push("");
  });
  if (reel.more) out.push(`+${reel.more} more cleared the bar and are on the board`);
  out.push(reel.basis);
  out.push(`⏱️ ${reel.pricedNote}`);
  if (reel.context) out.push(reel.context);
  if (reel.join) out.push(reel.join);
  if (site) out.push(site);
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
};
