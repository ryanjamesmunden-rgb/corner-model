// The streak finder post: one line per team, sorted by line then by run.
//
// THIS IS THE FORMAT THE CHANNEL ACTUALLY GETS, given as a worked example rather than
// described, so it is reproduced exactly rather than improved on:
//
//   🔥 Corner streak finder (highest stats overall)
//   🚩 Line & team / Streak / Model price / Date
//
//   🏴󠁧󠁢󠁥󠁮󠁧󠁿 7+ Grimsby 6/6 3.79 📅 Sat 15:00
//   🇳🇱 5+ Den Bosch 7/7 2.47 📅 Sun 13:30
//   ...
//
// WHY ONE LINE PER ROW, where dailyCard.js gives each row three. Twenty rows is the point
// of this post — it is a scan, and the reader picks off it. Three lines each would be sixty
// lines and nobody reads to the bottom. The trade is deliberate: no fixture, no opponent,
// no per-row link, and the reasoning lives on the site behind the one link at the end.
//
// THE PRICE IS THE MODEL'S, AND THE HEADER SAYS SO. `projection.fair_odds` is the break-even
// number this site computes, not an offer from anyone — and the column being labelled "Model
// price" is what stops it being read as a quoted price a reader can go and take. A book
// price would also make the post depend on odds having been entered, which would make a
// Monday post impossible; this one does not.
//
// SORTED BY LINE DESCENDING, THEN BY RUN. It reads as a leaderboard and is not one: nothing
// here has been measured as a ranking (measure_chase_board.py replayed four orderings
// walk-forward and all four scored the same as a shuffled control). A 7+ leads a 5+ because
// it is the bolder claim, and a 12/12 leads a 5/5 because it has more behind it. Both are
// descriptive, and the header says "highest stats" rather than "best bets" for that reason.
//
// N/N IS THE RUN STATING ITS OWN SAMPLE SIZE. "6/6" carries what "100%" does not, which is
// how many games it is out of — and a lone percentage on a run of three reads identically
// to one on a run of thirty.
import { flagBullet } from "./countryFlag.js";
import { TELEGRAM_MAX } from "./shareText.js";

export const FINDER_TZ = "Europe/London";
/** A run of one or two is not a streak, and "2 in a row" reads as a mistake even when true. */
export const FINDER_MIN_RUN = 3;
export const FINDER_MAX_ROWS = 20;
export const FINDER_HEAD = "🔥 Corner streak finder (highest stats overall)";
export const FINDER_KEY = "🚩 Line & team / Streak / Model price / Date";

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

const runOf = (r) => num(r?.streak?.length) || 0;

/**
 * "Sat 15:00" — day, then a 24-hour clock, in London.
 *
 * TWENTY-FOUR HOUR ON PURPOSE. Half these kick-offs are overseas and land after midnight
 * UK time: "Sun 03:30" is unambiguous where "3:30am" beside "Sat 15:00" makes the reader
 * do the conversion, and the ones they get wrong are the Brazilian and MLS games that make
 * up a third of the board.
 */
export const finderTime = (iso, tz = FINDER_TZ) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(d);
    const get = (t) => (parts.find((p) => p.type === t) || {}).value || "";
    const day = get("weekday");
    const hh = get("hour");
    const mm = get("minute");
    // Intl renders midnight as "24" in some ICU versions under hour12:false.
    return day && hh && mm ? `${day} ${hh === "24" ? "00" : hh}:${mm}` : "";
  } catch {
    return "";
  }
};

/** "7+" from a line of 7. Over lines only — see `eligible`. */
const plus = (line) => `${Math.ceil(Number(line))}+`;

/**
 * Which rows may appear.
 *
 * UNDERS ARE EXCLUDED, not rendered with a different label. The whole post is "N+" rows and
 * a "under 9" line dropped into that column reads as an over at a glance — the one mistake
 * on this card that costs money in the opposite direction to the one the reader intended.
 * The streaks screen carries both; this post is the over half of it and says so by showing
 * nothing else.
 *
 * A KICK-OFF IS REQUIRED because the date column is half the post's usefulness, and a row
 * with a blank there is a team the reader cannot act on.
 */
export const eligible = (r = {}, minRun = FINDER_MIN_RUN) =>
  (r.direction || "over") === "over"
  && num(r.line) !== null
  && runOf(r) >= minRun
  && !!r.next_fixture?.date;

/**
 * Rows in the order they are printed: boldest line first, longest run within it.
 *
 * TIES KEEP THE ORDER THEY ARRIVED IN, and that is a decision rather than an oversight.
 * Array.prototype.sort is stable, so equal (line, run) pairs come out in the backend's own
 * order — the one /streaks already shows. Adding a tiebreak here would make the post
 * disagree with the screen it links to, and the worked example this format came from proves
 * the point: Den Bosch at 2.47 is printed above Hercules at 1.21 on the same line and the
 * same run, so the order within a tie is demonstrably not the price. There is no measured
 * ranking to appeal to either — measure_chase_board.py scored four orderings against a
 * shuffled control and could not separate them — so inventing one here would be dressing
 * the backend's arbitrary order up as a judgement.
 */
export const finderOrder = (rows = [], minRun = FINDER_MIN_RUN) =>
  rows.filter((r) => eligible(r, minRun))
    .sort((a, b) => (num(b.line) - num(a.line)) || (runOf(b) - runOf(a)));

/** One row: flag, line, team, run, model price, kick-off. */
export const finderRow = (r = {}, tz = FINDER_TZ) => {
  const run = runOf(r);
  const fair = num(r.projection?.fair_odds);
  const when = finderTime(r.next_fixture?.date, tz);
  return [
    flagBullet(r.league_id, ""),
    plus(r.line),
    r.name || "",
    `${run}/${run}`,
    // A run with no priced projection still earns its place — the run is the claim and
    // the price is the extra. Printing "null" or dropping the row would lose both.
    fair !== null && fair > 0 ? fair.toFixed(2) : "",
    when ? `📅 ${when}` : "",
  ].filter(Boolean).join(" ");
};

/**
 * The post, at a given size. `streakFinder` wraps this and shrinks until Telegram accepts it.
 *
 * Returns `{ text, n }` so a caller can log how many rows actually went out — a quiet board
 * and a broken one are the same empty post otherwise.
 */
export const buildFinder = ({ rows = [], site = "", max = FINDER_MAX_ROWS,
                              minRun = FINDER_MIN_RUN, tz = FINDER_TZ } = {}) => {
  const picked = finderOrder(rows, minRun).slice(0, Math.max(1, Number(max) || FINDER_MAX_ROWS));
  if (!picked.length) return { text: "", n: 0 };
  const where = String(site || "").replace(/\/$/, "");
  const body = picked.map((r) => finderRow(r, tz)).join("\n");
  const tail = where ? `\n\n${where}/streaks` : "";
  return { text: `${FINDER_HEAD}\n${FINDER_KEY}\n\n${body}${tail}`, n: picked.length };
};

/**
 * The finder, at the largest size Telegram will deliver.
 *
 * REBUILT SMALLER, NOT TRIMMED — the scar angleMenu and dailyCard both carry: the weekend
 * card measured 4,544 characters on a board of long names and Telegram answered HTTP 400,
 * twice, both reported as success because the failure was in delivery. Cutting at the end
 * of a finished post would leave a half-row above the link.
 */
export const streakFinder = (opts = {}) => {
  const max = Number(opts.max ?? FINDER_MAX_ROWS);
  for (let n = max; n >= 1; n -= 1) {
    const built = buildFinder({ ...opts, max: n });
    if (!built.text || built.text.length <= TELEGRAM_MAX) return built;
  }
  return { text: "", n: 0 };
};
