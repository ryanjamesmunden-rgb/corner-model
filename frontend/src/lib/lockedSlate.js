// What the site has LOCKED IN before kick-off, sent to the channel.
//
// WHY THIS EXISTS. The snapshot has always been taken — Monday freezes the midweek card,
// Wednesday the weekend one — and the Results page grades it afterwards. Nothing ever SENT
// it. So the record on the site said "18 of 18" with no message anywhere proving the list
// was written down first, which is the one thing that makes a record worth anything.
//
// IT IS BUILT FROM THE SNAPSHOT'S OWN BYTES, and that is the whole design. Not from a fresh
// scan of the board, not from the card that went out alongside it — from the entries the
// freeze wrote to the database, read straight back out. A post assembled from a second scan
// could disagree with what gets graded, and the disagreement would be invisible until
// somebody checked a losing week by hand.
//
// A run is alive only until it breaks, so a board rescanned an hour later is a different
// board. That is the same survivorship argument the snapshot exists for, applied one step
// further along.
//
// ONLY THE QUALIFIED ENTRIES. The freeze stores up to 25 rows so the record can later ask
// what the near-misses did; the CARD is the ones that cleared a route and fell inside the
// window. A post listing all 25 would claim credit for rows nobody was shown.
//
// THIS IS THE PAID CHANNEL, SO IT CARRIES THE LINE AND THE PRICE. Everything public about
// this site now withholds those — see _blur_model — and the reason members pay is to be
// told them before the game rather than after. A locked list with the lines removed would
// be the record without the product.
//
// THE FREEZE TIME IS STATED, not implied. "Frozen Sun 28 Sep" is the claim being made, and
// a reader who wants to check it can compare the message timestamp with the kick-offs.
import { flagBullet } from "./countryFlag.js";
import { postDayTime, POST_TZ } from "./shareText.js";

/** Telegram refuses a message over this. The card note in shareText has the scar. */
export const TELEGRAM_MAX = 4096;
/** Above this run the run is the evidence on its own — angle_of_day.STRONG_RUN. */
export const STRONG_RUN = 10;

const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** "Weekend" / "Midweek" — the card's own label, or nothing when it had none. */
export const cardLabel = (card) =>
  ({ weekend: "Weekend", midweek: "Midweek" })[String(card || "").toLowerCase()] || "";

/**
 * The entries this post is allowed to name.
 *
 * `qualified` is read, never recomputed. It was decided at freeze time against data that
 * has since moved, and re-deciding it here would be the bar applied to a different board.
 */
export const lockedEntries = (entries = []) =>
  (entries || []).filter((e) => e && e.qualified && e.fixture_id && e.name);

/** "4+ corners" / "under 9 in the match" — what was actually called. */
export const callOf = (e = {}) => {
  const line = num(e.line);
  if (line === null) return "";
  const what = e.subject === "match" ? "in the match" : "corners";
  return e.direction === "under" ? `under ${line} ${what}` : `${line}+ ${what}`;
};

/** "v Wycombe (H)" — the fixture from this team's side of it. */
export const versus = (e = {}) => {
  const opp = String(e.opponent || "").trim();
  if (!opp) return "";
  return `${e.is_home ? "v" : "at"} ${opp}`;
};

/**
 * The one line of evidence under each call.
 *
 * THE ROUTE IS NAMED because it is the difference between two claims the record used to
 * present identically: a twelve-game run standing on its own, and a six-game run leaning on
 * a leaky opponent. Frozen with the entry for that reason, so it is printed.
 */
export const evidence = (e = {}) => {
  const run = num(e.streak_len) || 0;
  const games = num(e.games);
  const prob = num(e.prob);
  const bits = [];
  if (run) bits.push(`${run} in a row`);
  if (games) bits.push(`${games} games on file`);
  if (prob !== null) bits.push(`model ${Math.round(prob)}%`);
  if (e.route === "long_run" && run >= STRONG_RUN) {
    bits.push("the run alone");
  } else if (e.route === "corroborated") {
    const conc = num((e.support || {}).opp_conceded);
    bits.push(conc !== null ? `opponent ships ${conc.toFixed(1)}/g` : "leaky opponent");
  }
  return bits.join(" · ");
};

/** "Mon 28 Sep" — the day the list was written down. */
export const frozenLabel = (tag, tz = POST_TZ) => {
  if (!tag) return "";
  // Noon UTC: adding no offset in Europe can move the calendar day from there, so the
  // label always names the day the tag names.
  const d = new Date(`${tag}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return "";
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, weekday: "short", day: "numeric", month: "short",
    }).formatToParts(d);
    const get = (t) => (parts.find((p) => p.type === t) || {}).value || "";
    // THE MONTH IS CUT TO THREE LETTERS, and that is not cosmetic. ICU spells September
    // "Sep" on some builds and "Sept" on others, so the same tag would produce two
    // different posts depending on which machine composed it — the same class of drift as
    // reading a kick-off in the machine's own timezone. Three letters everywhere.
    return `${get("weekday")} ${get("day")} ${get("month").slice(0, 3)}`.trim();
  } catch {
    return "";
  }
};

/** One entry, three lines. */
export const lockedRow = (e = {}, tz = POST_TZ) => {
  const when = postDayTime(e.kickoff, tz);
  const head = `${flagBullet(e.league_id)} ${e.name} ${callOf(e)}`.trim();
  const mid = [versus(e), when].filter(Boolean).join(" · ");
  const why = evidence(e);
  return [head, mid && `   ${mid}`, why && `   ${why}`].filter(Boolean).join("\n");
};

/**
 * The post.
 *
 * Returns "" on an empty snapshot rather than a cheerful message about nothing: a freeze
 * that qualified nobody is a quiet week, and the caller says so in a log.
 *
 * TRIMMED FROM THE END IF IT HAS TO BE, and it says how many it dropped — a list that
 * silently ends early is a list a reader cannot check against the Results page, which is
 * the one thing this post is for.
 */
export const lockedSlate = ({ tag = "", card = "", entries = [], site = "",
                             max = TELEGRAM_MAX, tz = POST_TZ } = {}) => {
  const picked = lockedEntries(entries);
  if (!picked.length) return "";

  const label = cardLabel(card);
  // "Mon 28 Sep" rather than the weekday next to an ISO date, which read as two dates.
  // Noon UTC so the calendar day cannot slip either side of it in any European offset.
  const frozen = frozenLabel(tag, tz);
  const where = String(site || "").replace(/^https?:\/\//, "").replace(/\/$/, "");

  const head = `🔒 LOCKED IN${label ? ` — ${label} card` : ""}`;
  const sub = `Frozen ${frozen || tag}, before a ball was kicked. `
    + `${picked.length} call${picked.length === 1 ? "" : "s"}, graded on the site whatever `
    + `happens to them.`;
  const foot = "Nothing is added or removed after this message — that is the point of it."
    + (where ? `\n${where}/results` : "");

  // BUILT DOWNWARDS FROM ALL OF THEM. The rows are in the snapshot's own order, which is
  // the order the record will show, so dropping from the END keeps the two aligned.
  for (let n = picked.length; n >= 1; n -= 1) {
    const cut = picked.length - n;
    const body = picked.slice(0, n).map((e) => lockedRow(e, tz)).join("\n\n");
    const tail = cut ? `\n\n+ ${cut} more on the site, all of them graded.` : "";
    const text = `${head}\n${sub}\n\n${body}${tail}\n\n${foot}`;
    if (text.length <= max) return text;
  }
  return "";
};
