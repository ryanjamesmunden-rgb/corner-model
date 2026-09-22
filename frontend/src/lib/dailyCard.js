// The day's card for the channel: one post, four sections, one reason each.
//
// WHY THIS IS NOT angleMenu. That builds a numbered MENU — every angle the site found, for
// somebody to pick from and send one of. This is the thing that goes out: no numbering to
// choose by, the chase board leading because that is what the channel actually gets posted,
// and every section carrying the argument for its rows rather than a headline to select on.
// Same rows, opposite jobs, and rendering a menu into a channel is how a reader ends up
// looking at twenty options instead of a card.
//
// THE ORDER IS THE CLAIM'S STRENGTH, and it is stated rather than measured:
//
//   1. CHASE    the board this card exists for. A venue-split projection with a
//               corroboration filter behind it, and the only section with a graded record.
//   2. MISMATCH the opponent half — the part a run cannot see. Strong on its own.
//   3. STREAK   the weakest reading alone: five clears can be five coin flips. It is here
//               because it is the most readable, and it is placed where it cannot be
//               mistaken for the headline.
//   4. VALUE    the only section about money, and the only one that can be checked.
//
// Nothing here ranks. measure_chase_board.py replayed four orderings walk-forward and all
// four scored the same as a shuffled control — so the boards are FILTERS, and this card
// presents them as such. A row's place in the list is not a confidence.
//
// DE-DUPLICATED ACROSS THE FIRST THREE SECTIONS, by team and fixture. The same team under
// three headings turns a card of twelve rows into a card of four, and the reader has to
// work out which one to act on. The first appearance keeps the row and the corroboration
// becomes a marker on it — which is the more useful fact anyway: a run the matchup also
// likes is a better post than either on its own.
//
// VALUE IS DELIBERATELY NOT DE-DUPLICATED against them. "This team keeps clearing the line"
// and "this price is longer than fair" are different claims about the same game, and the
// second is the one worth money. It is marked on the row above so the repeat reads as
// corroboration rather than as the card stuttering.
import { recordLine, reasonFor, slateFrom, slateRow } from "./chaseSlate.js";
import { flagBullet } from "./countryFlag.js";
import { plusLine, postDayTime, TELEGRAM_MAX } from "./shareText.js";

export const CARD_PER_SECTION = 5;
export const CARD_CHASE_ROWS = 5;
/** A run shorter than this is not a streak, it is two games. */
export const CARD_MIN_RUN = 3;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const runOf = (r) => Number(r?.streak?.length) || 0;

const keyOf = (name, fid) => `${fid || ""}|${String(name || "").toLowerCase()}`;

const pct = (p) => {
  const n = num(p);
  return n !== null && n > 0 ? `${Math.round(n)}%` : "";
};

/** "79% (1.26)" — the model's two ways of saying the same thing, or nothing at all. */
const modelBit = (prob, fair) => {
  const p = pct(prob);
  if (!p) return "";
  const f = num(fair);
  return ` · ${p}${f !== null && f > 0 ? ` (${f.toFixed(2)})` : ""}`;
};

const fixtureOf = (r = {}) => {
  const nf = r.next_fixture || {};
  if (!nf.date || !nf.fixture_id) return null;
  return {
    id: nf.fixture_id,
    home: nf.is_home ? r.name : nf.opponent,
    away: nf.is_home ? nf.opponent : r.name,
    when: postDayTime(nf.date),
  };
};

const host = (site) => String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");

/**
 * Which fixtures carry a price worth taking.
 *
 * A SEEDED PRICE IS REFUSED. seed_team_odds writes `fair_odds * uniform(0.90, 1.15)`, so an
 * EV computed against one is the model finding value in its own jitter. On screen that is
 * indistinguishable from a real edge, which is exactly why it is dropped here rather than
 * shown with a caveat — a caveat on a fabricated number still puts the number on the card.
 */
export const pricedFixtures = (value = []) => new Set(
  value.filter((v) => v.odds_source === "manual" && Number(v.best?.ev) > 0)
       .map((v) => v.fixture_id));

/**
 * One post, built at a given section size. `dailyCard` wraps this and shrinks until it fits.
 *
 * Returns `{ text, counts }` — `counts` so a caller can log what actually went out per
 * section, which is what distinguishes a quiet day from a broken board.
 */
export const buildCard = ({ chase = [], mismatches = [], streaks = [], value = [],
                            ledger = null, site = "", label = "", day = null,
                            per = CARD_PER_SECTION, chaseRows = CARD_CHASE_ROWS } = {}) => {
  const where = host(site);
  const seen = new Set();
  const priced = pricedFixtures(value);
  const matchup = new Set(mismatches.map((m) => keyOf(m.name, m.next_fixture?.fixture_id)));
  const counts = { chase: 0, mismatch: 0, streak: 0, value: 0 };

  const link = (fid) => (where && fid ? `\n   ↳ ${where}/fixture/${fid}` : "");
  const gameLine = (fx) => `${fx.home} v ${fx.away}${fx.when ? ` · ${fx.when}` : ""}`;

  const markers = (name, fid) =>
    (matchup.has(keyOf(name, fid)) ? "  ⚔️ matchup agrees" : "")
    + (priced.has(fid) ? "  💰 priced below" : "");

  // ---- 1. CHASE, through the slate the site and the channel already share -------------
  // slateFrom applies the quality bar and slateRow carries the venue-split argument, so
  // this section is the same rows, in the same order, with the same reasoning as the
  // chase slate on the site. A second rendering here is how the two drift apart.
  // min: 1 — see the note on slateFrom. Three rows is the floor for a post that is ONLY
  // this board; here it is one section of four, and a spot that cleared the bar should not
  // be dropped for want of two others beside it.
  const slate = slateFrom({ rows: chase, ledger, day, max: chaseRows, min: 1 });
  const chaseLines = [];
  for (const c of (slate?.rows || [])) {
    if (!c.fixtureId) continue;
    seen.add(keyOf(c.team, c.fixtureId));
    // ALWAYS TWO DECIMALS. A raw 1.4 beside a 1.35 reads as a rounder, less precise
    // number than the one under it when both were computed the same way — and on a card
    // about prices, "1.4" invites the question of whether it means 1.40 or 1.45.
    const money = (v) => Number(v).toFixed(2);
    const price = c.price === null ? ""
      : c.priceKind === "book" ? `  @ ${money(c.price)}` : `  fair ${money(c.price)}`;
    chaseLines.push(
      `${chaseLines.length + 1}. ${c.home} v ${c.away}${c.time ? `  ${c.time}` : ""}`
      + `${priced.has(c.fixtureId) ? "  💰" : ""}\n`
      + `   ${c.market}${price}\n   ${reasonFor(c)}${link(c.fixtureId)}`);
  }
  counts.chase = chaseLines.length;

  // ---- 2 and 3. MISMATCH then STREAK, de-duplicated against chase and each other -------
  const take = (rows, render) => {
    const out = [];
    for (const r of rows) {
      if (out.length >= per) break;
      const fx = fixtureOf(r);
      if (!fx) continue;
      const k = keyOf(r.name, fx.id);
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(`${flagBullet(r.league_id, "•")} ${render(r, fx)}\n   ${gameLine(fx)}`
               + link(fx.id));
    }
    return out;
  };

  const mismatchLines = take(mismatches, (r) =>
    `${r.name} ${plusLine(r.line)} — wins ${r.team_for}, they concede ${r.opp_conceded}`
    + `${modelBit(r.prob, r.fair_odds)}${priced.has(r.next_fixture?.fixture_id) ? "  💰" : ""}`);
  counts.mismatch = mismatchLines.length;

  // Longest runs lead, and among equal runs the ones the matchup also likes. Both are
  // descriptive orderings — see the note at the top: neither has been measured.
  const streakLines = take(
    [...streaks].filter((r) => runOf(r) >= CARD_MIN_RUN)
      .sort((a, b) => (runOf(b) - runOf(a))
        || (num(b.projection?.prob) || 0) - (num(a.projection?.prob) || 0)),
    (r, fx) => `${r.name} ${r.line_label || ""} — ${runOf(r)} in a row`
      + `${modelBit(r.projection?.prob, r.projection?.fair_odds)}`
      + `${runOf(r) >= 8 ? " 🔥" : ""}${markers(r.name, fx.id)}`);
  counts.streak = streakLines.length;

  // ---- 4. VALUE, which says WHICH KIND of empty it is ---------------------------------
  // "Nothing priced" and "priced, and nothing beats its price" are opposite facts: the
  // first is a job to do this evening, the second is a reason not to bet tonight. A blank
  // section reads as neither, and a reader fills the gap with the more flattering one.
  const realPriced = value.filter((v) => v.odds_source === "manual" && v.best
                                         && Number(v.best.ev) > 0)
    .sort((a, b) => Number(b.best.ev) - Number(a.best.ev));
  const valueLines = realPriced.slice(0, per).map((v) => {
    const b = v.best || {};
    const when = postDayTime(v.date);
    return `${flagBullet(v.league_id, "•")} ${v.home} v ${v.away}${when ? ` · ${when}` : ""}\n`
      + `   ${b.label || ""} @ ${Number(b.book_odds).toFixed(2)}`
      + `  (fair ${Number(b.fair_odds).toFixed(2)}, +${Number(b.ev).toFixed(1)}%)`
      + link(v.fixture_id);
  });
  counts.value = valueLines.length;
  const anyPrices = value.some((v) => v.odds_source === "manual");
  const valueBody = valueLines.length ? valueLines.join("\n\n")
    : anyPrices ? "Priced up, and nothing beats its price today. No bet."
                : "No prices entered yet — nothing to check a number against.";

  // ---- assemble -----------------------------------------------------------------------
  const head = `📋 CORNER CARD${label ? ` — ${label}` : ""}`;
  const rec = recordLine(slate?.record);
  const sections = [];
  if (chaseLines.length) {
    sections.push(`🎯 THE CHASE BOARD${rec ? `\n${rec}` : ""}\n\n${chaseLines.join("\n\n")}`);
  }
  if (mismatchLines.length) {
    sections.push(`⚔️ TOP MISMATCHES\n\n${mismatchLines.join("\n\n")}`);
  }
  if (streakLines.length) {
    sections.push(`🔥 RUNNING STREAKS\n\n${streakLines.join("\n\n")}`);
  }
  sections.push(`💰 PRICED UP\n\n${valueBody}`);

  if (!chaseLines.length && !mismatchLines.length && !streakLines.length) {
    // AN HONEST NOTHING, rather than a card carrying only its own footer. A post that
    // looks like a card and contains no angle trains the reader to skim the next one.
    return { text: "", counts };
  }

  const fairShown = (slate?.rows || []).some((r) => r.priceKind === "fair");
  const tail = [
    fairShown && "Prices marked fair are the model's break-even number, not an offer — shop your own.",
    where && `Full boards: ${where}`,
  ].filter(Boolean).join("\n");

  return { text: `${head}\n\n${sections.join("\n\n———\n\n")}${tail ? `\n\n${tail}` : ""}`,
           counts };
};

/**
 * The card, at the largest size Telegram will actually deliver.
 *
 * REBUILT SMALLER, NOT TRIMMED. Same rule angleMenu follows and for the same scar: the
 * weekend card was written without a cap, measured 4,544 characters on a board of long
 * names, and Telegram answered HTTP 400 — twice, both times reported as success, because
 * the failure was in delivery and the draft behind it was fine. Cutting at the end would
 * sever a link mid-URL; the chase section is shrunk last because it is the one the card
 * exists for.
 */
export const dailyCard = (opts = {}) => {
  const per = Number(opts.per ?? CARD_PER_SECTION);
  const chaseRows = Number(opts.chaseRows ?? CARD_CHASE_ROWS);
  for (let n = per; n >= 1; n -= 1) {
    const built = buildCard({ ...opts, per: n, chaseRows });
    if (!built.text || built.text.length <= TELEGRAM_MAX) return built;
  }
  for (let c = chaseRows - 1; c >= 1; c -= 1) {
    const built = buildCard({ ...opts, per: 1, chaseRows: c });
    if (!built.text || built.text.length <= TELEGRAM_MAX) return built;
  }
  // One row per section and still over. Not reachable with real rows, and an oversized
  // post is a silent 400 — so return nothing and let the caller report a quiet day.
  return { text: "", counts: { chase: 0, mismatch: 0, streak: 0, value: 0 } };
};
