// The morning slate: today's games, as one card and one post.
//
// WHAT THIS IS. Every other board here answers "what is interesting this week". This one
// answers "what is on today", which is the only question a morning post can usefully ask —
// and the one a reader can act on before the games kick off.
//
// THE PRICE COLUMN IS THE WHOLE PROBLEM, and it is worth being explicit about why, because
// the obvious implementation is wrong in a way that is invisible on the finished graphic.
//
// A card like this puts a big number in a box on the right of every row. On a tipster slip
// that number is a BOOK price — what you can actually get on. This model produces a FAIR
// price, which is what the odds would have to be for the bet to break even. They look
// identical in a box. Drawing the fair price in the book price's slot publishes a number
// nobody can bet, to an audience who will read it as one they can, and the first person to
// check a bookmaker finds the card was wrong about the only figure on it they cared about.
//
// So the two are separated at the source, here, rather than left to the renderer's styling:
// `priceKind` is "book" only when a real price was typed in (odds_source === "manual"), and
// "fair" otherwise. The card draws them differently and labels the difference. Everything
// downstream can be dumb about it because this is not.
//
// WHY NOT JUST SHOW BOOK PRICES. Because there usually are not any. A price gets into the
// record when someone types it — on the site, or by replying "3 @ 1.80" to the angle menu.
// A slate built only from priced rows would be empty most mornings. The model's number is
// worth publishing; it just has to be published as what it is.

/**
 * The zone the card's kick-off times are stated in.
 *
 * FIXED, AND NOT THE MACHINE'S. Everywhere else here formats a time in the reader's own
 * zone, which is right for a page rendered in their browser. This card is a PNG drawn once
 * on a CI runner and then shown to everyone, so "local" means the runner's locale — which
 * is UTC, and which rendered "01:30 PM" where the layout had budgeted for "13:30". A column
 * whose width depends on where the job happened to run is a column that overlaps its
 * neighbour on someone else's machine and not on mine.
 *
 * London because that is where the audience is. Stated on the card, because a bare "13:30"
 * against a game somebody knows kicks off at 14:30 their time reads as a wrong card.
 */
export const SLIP_TZ = "Europe/London";

/** "13:30" in SLIP_TZ, whatever the machine drawing it thinks the time is. */
export const slipTime = (iso, tz = SLIP_TZ) => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz,
    }).format(d);
  } catch {
    // An environment without that zone in its ICU data would otherwise throw and take the
    // whole card down over a time label.
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
  }
};

/** "BST" / "GMT" for SLIP_TZ on the given day, to say which clock the card means. */
export const slipZoneLabel = (iso, tz = SLIP_TZ) => {
  const d = iso ? new Date(iso) : new Date();
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: tz, timeZoneName: "short" })
      .formatToParts(d).find((p) => p.type === "timeZoneName")?.value || "";
  } catch {
    return "";
  }
};

/** Fewer than this is not a slate, it is a single pick with decoration around it. */
export const MIN_SLIP_ROWS = 2;
/** More than this and the rows are too short to read on a phone at 1080x1350. */
export const MAX_SLIP_ROWS = 5;

// NULL AND "" ARE NOT ZERO, however much Number disagrees — `Number(null)` is 0 and so is
// `Number("")`. Left to the default, an absent stake became a stake of 0 and the card drew
// "0u" against a row nobody had staked, which reads as a pick deliberately sized to nothing.
// The same trap applies to every optional figure here: a missing price would become evens.
const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/**
 * Is this a price somebody could actually take?
 *
 * `odds_source === "manual"` is the backend's mark for a price a person typed in. Anything
 * else on `projection` is derived from the model, including `fair_odds` — which is a
 * break-even number, not an offer.
 */
export const isBookPrice = (r = {}) =>
  r?.projection?.odds_source === "manual" && num(r?.projection?.book_odds) !== null;

/**
 * Which day a moment falls on, ON THE SAME CLOCK THE CARD STATES ITS TIMES IN.
 *
 * THE TWO HAVE TO AGREE, and the obvious implementation has them disagree. Fixture dates
 * arrive as UTC, so slicing the first ten characters off the ISO string answers "which UTC
 * day" — while every time printed beside it is converted to London. A 00:30 London kick-off
 * is 23:30 UTC the day before: sliced, it lands on yesterday's card, printed, it reads
 * 00:30. The card would then claim Monday, show a time that is Tuesday, and be internally
 * inconsistent about a fixture that is itself perfectly correct.
 *
 * en-CA because its short date format IS YYYY-MM-DD, which is the shape everything else
 * here compares on.
 */
export const dayKeyOf = (when, tz = SLIP_TZ) => {
  const d = when ? new Date(when) : new Date();
  if (Number.isNaN(d.getTime())) return "";
  const opts = { year: "numeric", month: "2-digit", day: "2-digit" };
  try {
    return new Intl.DateTimeFormat("en-CA", { ...opts, timeZone: tz }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-CA", opts).format(d);
  }
};

/** Today, in London — the day the morning post is about. */
export const dayKey = (d = new Date()) => dayKeyOf(d);

/** Does this row's fixture kick off on the given day, on that same clock? */
const onDay = (r, key) => dayKeyOf(r?.next_fixture?.date) === key;

/**
 * One row of the slate.
 *
 * `home` and `away` are resolved from the streak row's point of view: the row names ONE
 * team and says whether it was at home, so the opponent goes on the other line. Getting
 * this backwards puts the fixture the wrong way round on a public graphic, which is the
 * kind of error that makes everything else on the card look unreliable.
 */
export const slipRow = (r = {}) => {
  const nf = r.next_fixture || {};
  const home = nf.is_home === false ? nf.opponent : r.name;
  const away = nf.is_home === false ? r.name : nf.opponent;
  const book = isBookPrice(r);
  return {
    team: r.name || "",
    home: home || "",
    away: away || "",
    // The market as the backend labels it, never rebuilt here — an under rendered as an
    // over is a public, wrong claim about what was actually backed, and the label is the
    // one place that distinction survives.
    market: r.line_label || "",
    subject: r.subject || "team",
    leagueId: r.league_id || null,
    kickoff: nf.date || null,
    time: slipTime(nf.date),
    fixtureId: nf.fixture_id || null,
    run: num(r?.streak?.length),
    prob: num(r?.projection?.prob),
    price: book ? num(r.projection.book_odds) : num(r?.projection?.fair_odds),
    priceKind: book ? "book" : "fair",
    ev: book ? num(r?.projection?.ev) : null,
    stake: num(r?.stake),
  };
};

/**
 * Rank the day's angles the way the rest of the site ranks them.
 *
 * DELIBERATELY THE SAME ORDER AS pickGameDetailed: a real positive edge first, then the
 * longest run, then the model's confidence. If the slate ordered games differently, the
 * game at the top of the morning card and the one the daily best-game post picks could
 * disagree — and two posts an hour apart naming different "best" games reads as a model
 * that cannot make its mind up.
 */
const rank = (a, b) => {
  const edge = (r) => (r.priceKind === "book" && r.ev !== null ? r.ev : -Infinity);
  return (edge(b) - edge(a))
    || ((b.run || 0) - (a.run || 0))
    || ((b.prob || 0) - (a.prob || 0));
};

/**
 * The day's slate, or null when there is not one.
 *
 * NULL RATHER THAN A THIN CARD. A "1 ANGLE TODAY" graphic with four fifths of the table
 * empty is worse than posting nothing: it is the same card the good days use, advertising
 * that today is not one of them. A quiet morning should be quiet.
 */
export const slipFrom = ({ rows = [], day = null, max = 3 } = {}) => {
  const key = day || dayKey();
  const limit = Math.max(MIN_SLIP_ROWS, Math.min(MAX_SLIP_ROWS, Number(max) || 3));
  const picked = (rows || [])
    .filter((r) => onDay(r, key) && r?.next_fixture?.opponent)
    .map(slipRow)
    .filter((r) => r.market && r.home && r.away)
    .sort(rank)
    .slice(0, limit);
  if (picked.length < MIN_SLIP_ROWS) return null;

  const priced = picked.filter((r) => r.priceKind === "book").length;
  return {
    day: key,
    rows: picked,
    n: picked.length,
    priced,
    zone: slipZoneLabel(picked[0]?.kickoff),
    // BETS ONLY WHEN THEY ARE BETS. A "bet" is a staked position at a price you can get;
    // without a real price these are angles the model likes, and calling them bets is a
    // claim about money that nothing here has made. Derived rather than passed in, so the
    // wording cannot drift from what the rows actually carry.
    label: priced ? "BETS" : "ANGLES",
    // A column of dashes is worse than no column — see the card.
    hasStakes: picked.some((r) => r.stake !== null),
  };
};

/**
 * The post that carries the card, with a link per game.
 *
 * THE LINKS ARE THE POINT, and they are why this is not just an image. A graphic is a claim
 * you have to take on trust; the link under each row is the page showing the distribution,
 * the run, and every number the row was built from. It is also the only part of a Telegram
 * post that can bring somebody back to the site.
 */
export const slipPost = ({ slip = null, site = "", heading = "" } = {}) => {
  if (!slip) return "";
  const head = heading || `${slip.n} ${slip.label} TODAY`;
  const lines = slip.rows.map((r, i) => {
    const price = r.price === null ? ""
      : r.priceKind === "book" ? `  @ ${r.price}` : `  fair ${r.price}`;
    const link = site && r.fixtureId ? `\n   ↳ ${site}/fixture/${r.fixtureId}` : "";
    return `${i + 1}. ${r.home} v ${r.away}${r.time ? `  ${r.time}` : ""}\n`
      + `   ${r.market}${price}${link}`;
  });
  // SAID ONCE, AT THE BOTTOM, where a reader who scrolled the rows will meet it. Repeating
  // "fair" against every row would crowd the part that is worth reading, and leaving it off
  // entirely would let the model's break-even number pass as a price somebody is offering.
  const tail = slip.priced === slip.n ? ""
    : "\n\nPrices marked fair are the model's break-even number, not an offer — "
      + "shop your own.";
  return `${head}\n\n${lines.join("\n\n")}${tail}`;
};
