// The stat-pick post: how often a corner line has landed, and what it is paying.
//
// WHY THIS FORMAT AND NOT THE VIP ONE. telegramPick writes a CALL — a line, a price, a
// stake and the reasoning behind it. This writes a LIST, and the thing it leads with is a
// count: "4.5+ Corners @ 2.10 (8/10)". The count is the whole appeal, because it is the
// only number in betting content a reader can verify for themselves — the form table it
// comes from is already on the site, unblurred, for anybody who wants to go and count.
//
// SO THE DENOMINATOR IS NEVER OPTIONAL, AND NEVER ROUNDED INTO A PERCENTAGE. "80%" hides
// whether that was four from five or forty from fifty; "(8/10)" cannot. Every rate in
// this file is printed as hits over games, and `games` comes from the backend rather than
// from a constant here, so a change to the measuring window cannot leave the post
// claiming a denominator the data no longer has.
//
// AND THE VENUE RIDES WITH IT. corner_counts falls back from a venue pool to all games
// when the venue is thin, and reports which it used. "8/10 at home" is a different claim
// from "8/10 overall", so the suffix is part of the count, not decoration.
import { flagFor, countryCodeFor } from "./countryFlag.js";
import { postTime, postDate } from "./shareText.js";

/** Fewer than this is a message, not a card. */
export const MIN_PICK_ROWS = 2;
/** More than this and the post stops being readable on a phone. */
export const MAX_PICK_ROWS = 12;

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * "4.5+ Corners" — the bet in the form this account already posts its props in.
 *
 * `1.5+ Tackles`, `0.5+ SOT`, `2.5+ Shots`: the handicap, then a plus. A corner line of
 * 4.5 is the same shape and the same bet as "5+", and matching the house style matters
 * more than matching the ledger's vocabulary, because this post sits in a feed next to
 * the player-prop ones.
 */
export const pickLine = (p = {}) => {
  const line = num(p.line);
  return line === null ? "" : `${line}+ Corners`;
};

/**
 * "(8/10 A)" — the count, and the pool it was counted over.
 *
 * The letter is the VENUE THE RATE WAS MEASURED AT, which is also the venue the team is
 * playing at: corner_counts is asked for the side's own venue and only widens when that
 * pool is too thin. A bare "(8/10)" therefore means all games, not "venue unknown".
 */
export const pickCount = (p = {}) => {
  const hits = num(p.hits);
  const games = num(p.games);
  if (hits === null || !games) return "";
  const where = p.scope === "home" ? " H" : p.scope === "away" ? " A" : "";
  return `(${hits}/${games}${where})`;
};

/** The hit rate as a fraction, for sorting and for the floor. Null when uncountable. */
export const hitRate = (p = {}) => {
  const hits = num(p.hits);
  const games = num(p.games);
  return hits === null || !games ? null : hits / games;
};

/** "EV +14.3%" — the model's edge on the price, or "" when there isn't one. */
export const pickEv = (p = {}) => {
  const ev = num(p.ev);
  return ev === null ? "" : `EV ${ev > 0 ? "+" : ""}${ev.toFixed(1)}%`;
};

/**
 * One line of the post.
 *
 * "Vila Nova 4.5+ Corners @ 2.10 (8/10 A) EV +14.3%"
 *
 * THE BOOKMAKER IS NOT ON THE LINE and that is deliberate: at twelve rows the name on
 * every one of them doubles the length of the post, and the books are stated once in the
 * footer instead. A row whose book is unknown never reaches here — the backend refuses it
 * — so the footer can name them all truthfully.
 */
export const pickRow = (p = {}) => {
  const price = num(p.price);
  return [p.team, pickLine(p), price === null ? "" : `@ ${price.toFixed(2)}`,
          pickCount(p), pickEv(p)].filter(Boolean).join(" ");
};

/** "🇧🇷 Fortaleza v Vila Nova · 10:30pm" */
export const fixtureHead = (p = {}) => {
  const flag = flagFor(p.league_id) || countryCodeFor(p.league_id) || "";
  const when = postTime(p.kickoff);
  const game = [p.home_name, p.away_name].filter(Boolean).join(" v ");
  return [flag, game].filter(Boolean).join(" ") + (when ? `  ·  ${when}` : "");
};

const ms = (iso) => {
  const t = new Date(iso || "").getTime();
  return Number.isFinite(t) ? t : 0;
};

/**
 * Group the rows into the post, or null when there is not a post here.
 *
 * KICK-OFF ORDER, so the card reads as a day rather than as a leaderboard of my own
 * claims — and so the reader can see at a glance which ones are about to go.
 *
 * THE TRIM TAKES THE WORST RATES OFF, not the latest games, and says how many went: this
 * is explicitly a filtered list ("every line landing 7+ from 10"), so cutting by rate is
 * the same rule the card already announces, while cutting by time would silently turn it
 * into "the next twelve games".
 */
export const picksFrom = (data = {}, { max = MAX_PICK_ROWS } = {}) => {
  const rows = (data?.picks || []).filter((p) => hitRate(p) !== null && num(p.price) !== null);
  if (rows.length < MIN_PICK_ROWS) return null;

  const byRate = [...rows].sort((a, b) => (hitRate(b) - hitRate(a))
                                          || ((num(b.ev) || 0) - (num(a.ev) || 0)));
  const kept = byRate.slice(0, Math.max(MIN_PICK_ROWS, max));
  kept.sort((a, b) => ms(a.kickoff) - ms(b.kickoff) || hitRate(b) - hitRate(a));

  const games = [];
  for (const p of kept) {
    const last = games[games.length - 1];
    if (last && last.fixture_id === p.fixture_id) last.rows.push(p);
    else games.push({ fixture_id: p.fixture_id, head: fixtureHead(p), rows: [p] });
  }

  const books = [...new Set(kept.map((p) => p.book).filter(Boolean))];
  return {
    games,
    n: kept.length,
    more: rows.length - kept.length,
    fixtures: games.length,
    books,
    window: num(data.window),
    minHit: num(data.min_hit),
    minOdds: num(data.min_odds),
    day: postDate(kept[0]?.kickoff),
    // The rule the card is filtered by, written out, because a list headed "stat picks"
    // with no rule under it is a tip sheet; with the rule under it, it is a filter anyone
    // can disagree with.
    rule: statRule(data),
  };
};

/**
 * "landing 70%+ of their last 10 (8 games minimum), at 1.50 or bigger, …"
 *
 * A PERCENTAGE HERE AND A FRACTION ON EVERY ROW, which looks inconsistent and is not.
 * This sentence describes a FILTER, and the filter is a rate; the rows report RESULTS,
 * and a result needs its denominator.
 *
 * The first live run is why this is not "landing 7+ from their last 10". Rows came back
 * at (5/6) and (3/4) — the venue pool is shallower than the window for plenty of sides —
 * so the card stated a rule its own rows could not satisfy. The backend now floors the
 * denominator; this says what that floor is instead of implying every row has ten games
 * behind it.
 */
export const statRule = (data = {}) => {
  const games = num(data.window);
  const minHit = num(data.min_hit);
  const minOdds = num(data.min_odds);
  const minGames = num(data.min_games);
  const bits = [];
  if (minHit && games) {
    const pct = Math.round(minHit * 100);
    bits.push(`landing ${pct}%+ of their last ${games}`
              + (minGames && minGames < games ? ` (${minGames} games minimum)` : ""));
  }
  if (minOdds) bits.push(`at ${minOdds.toFixed(2)} or bigger`);
  const ev = num(data.min_ev);
  if (ev !== null) {
    bits.push(ev > 0 ? `with an edge over ${ev}%` : "with a positive model edge");
  }
  return bits.join(", ");
};

/**
 * The post itself.
 *
 * THE HEADER STATES THE FILTER AND THE WINDOW BEFORE A SINGLE ROW. The format this
 * imitates does the same thing — "every player with over 70% hitrate over last 15 games"
 * — and it is the reason that format reads as research rather than as tipping.
 */
export const picksPost = ({ post = null, site = "", heading = "" } = {}) => {
  if (!post || !post.n) return "";
  const out = [heading || `${post.day ? post.day.toUpperCase() : "TODAY"} — CORNER STAT PICKS`,
               "💾 Save this before kick-off", ""];
  if (post.rule) out.push(`Every team corner line on the card ${post.rule}.`, "");
  post.games.forEach((g) => {
    out.push(g.head);
    g.rows.forEach((p) => out.push(pickRow(p)));
    out.push("");
  });
  if (post.more) out.push(`+${post.more} more cleared the bar and did not fit`);
  // H AND A EXPLAINED ONCE, at the bottom, where it does not interrupt the rows.
  if (post.games.some((g) => g.rows.some((p) => p.scope === "home" || p.scope === "away"))) {
    out.push("H / A = that team's record at this venue; no letter = all games");
  }
  if (post.books.length) out.push(`Prices: ${post.books.join(", ")}`);
  if (site) out.push(site);
  out.push("18+ · begambleaware.org");
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
};
