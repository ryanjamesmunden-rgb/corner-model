// Instagram Story images: the angles, with the actionable half blurred out.
//
// WHAT IS BLURRED, AND WHY IT DIFFERS PER BOARD. The tease only works if what's left is
// still CREDIBLE. Blurring whole rows proves nothing — it could be an empty list. So a
// row is four independent slots and each board decides which of them to hold back:
//
//   STREAKS hide the line and keep everything else — the team, the record, the
//   kick-off. Same policy the text share follows: the team is what makes the post
//   worth reading and the line is what the paid channel is for, so it is the one
//   thing that never goes out in public.
//
//   MISMATCHES do the opposite: the FIXTURE is the tease, so it stays legible, and what
//   is held back is the in-depth stats and the model — the line, the projection and the
//   fair odds. A reader sees which games are worth attention and has to join to learn
//   what the model says about them.
//
// Either way the top row is left whole, as proof the blurred ones are real rows and not
// an empty list with a filter over it.
//
// FLAGS. A text share is read on the reader's own device, so a flag that fails to render
// is one reader's problem. An image is different: whatever the CREATOR's machine draws
// gets baked into a PNG everyone then sees, and Windows has no flag glyphs at all — the
// story would go out with "NO" and "GB" boxes on it. So the flag is probed once and a
// country-code chip is used instead when it hasn't rendered.
//
// Sizes are in Story pixels (1080x1920) rather than CSS units: this draws to a canvas
// that becomes a file, so there is no viewport to be relative to.

import { flagFor, countryCodeFor } from "./countryFlag.js";
import { kickoffLabel, kickoffTime, kickoffDay } from "./kickoff.js";

export const STORY_W = 1080;
export const STORY_H = 1920;

// Lifted from index.css so the story looks like the site rather than merely near it.
const C = {
  bg: "#0A0A0A",
  card: "#141416",
  border: "#292930",
  text: "#F4F4F5",
  muted: "#9B9BA3",
  primary: "#00E5FF",     // --primary 187 100% 50%
  solid: "#10B981",       // the emerald a solid run wears on the board
};

const FONT_HEAD = "'Outfit', 'Manrope', system-ui, sans-serif";
const FONT_BODY = "'Manrope', system-ui, sans-serif";
const FONT_DATA = "'IBM Plex Mono', ui-monospace, monospace";

/**
 * Has this browser actually got flag glyphs?
 *
 * Measured rather than sniffed by user agent, because what matters is what the font
 * stack draws, not what OS reports. Where flags render, the pair of regional indicators
 * is one wide glyph; where they don't, it falls back to two letter-boxes of ordinary
 * text width. Comparing against a known two-letter string separates the cases.
 */
export const flagsRender = (ctx) => {
  const prev = ctx.font;
  ctx.font = `100px ${FONT_BODY}`;
  const flag = ctx.measureText("\u{1F1F3}\u{1F1F4}").width;
  const letters = ctx.measureText("NO").width;
  ctx.font = prev;
  // A rendered flag is a single square-ish glyph; two letter-boxes are visibly narrower
  // per unit and land close to the plain text width. 15% clear of it is a safe margin.
  return flag > letters * 1.15;
};

/**
 * The largest size at or below `size` at which the text fits `max` px.
 *
 * A story title is generated from a weekday name, so its length is not knowable when the
 * size is chosen: "Today's mismatches" fits at 76px and "Wednesday's mismatches" does
 * not, and canvas does not wrap or clip — it draws straight off the edge and the letters
 * are simply gone from the file.
 */
const fitFont = (ctx, text, { size, max, weight = 700, family }) => {
  let px = size;
  while (px > 28) {
    ctx.font = `${weight} ${px}px ${family}`;
    if (ctx.measureText(text).width <= max) break;
    px -= 2;
  }
  return ctx.font;
};

const roundRect = (ctx, x, y, w, h, r) => {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
};

/** Text drawn behind a blur, for the parts being held back. */
const blurred = (ctx, draw, radius) => {
  ctx.save();
  ctx.filter = `blur(${radius}px)`;
  draw();
  ctx.restore();
};

/**
 * Draw one row: a country marker, two stacked slots on the left, two on the right.
 * `row.tease` names which slots are held back — the row's shape, spacing and colour are
 * identical either way, so a blurred slot reads as something withheld rather than a gap.
 */
const drawRow = (ctx, row, y, { useFlags, blurRadius }) => {
  const x = 72;
  const w = STORY_W - x * 2;
  const h = 150;
  const tease = row.tease || {};

  ctx.fillStyle = C.card;
  roundRect(ctx, x, y, w, h, 20);
  ctx.fill();
  ctx.strokeStyle = row.solid ? `${C.solid}55` : C.border;
  ctx.lineWidth = 2;
  ctx.stroke();

  // The quality stripe the board uses, so a solid row looks solid here too.
  ctx.fillStyle = row.solid ? C.solid : C.border;
  roundRect(ctx, x, y, 8, h, 4);
  ctx.fill();

  const mid = y + h / 2;
  let cx = x + 44;

  // The country is never teased. It is what makes a row believable without giving it away.
  if (useFlags && row.flag) {
    ctx.font = `56px ${FONT_BODY}`;
    ctx.textBaseline = "middle";
    ctx.fillText(row.flag, cx, mid);
    cx += 84;
  } else if (row.code) {
    ctx.font = `600 26px ${FONT_DATA}`;
    ctx.textBaseline = "middle";
    const cw = ctx.measureText(row.code).width + 28;
    ctx.fillStyle = "#1E1E23";
    roundRect(ctx, cx, mid - 22, cw, 44, 10);
    ctx.fill();
    ctx.fillStyle = C.muted;
    ctx.fillText(row.code, cx + 14, mid + 1);
    cx += cw + 24;
  }

  const slot = (text, { font, colour, at, align, hidden }) => {
    if (!text) return;
    const draw = () => {
      ctx.fillStyle = colour;
      ctx.font = font;
      ctx.textAlign = align;
      ctx.textBaseline = "middle";
      ctx.fillText(text, align === "right" ? x + w - 40 : cx, at);
      ctx.textAlign = "left";
    };
    if (hidden) blurred(ctx, draw, blurRadius); else draw();
  };

  slot(row.headline, { font: `600 42px ${FONT_HEAD}`, colour: C.text,
                       at: mid - 20, align: "left", hidden: tease.headline });
  slot(row.sub, { font: `600 32px ${FONT_DATA}`, colour: C.primary,
                  at: mid + 30, align: "left", hidden: tease.sub });
  slot(row.value, { font: `600 40px ${FONT_DATA}`, colour: row.solid ? C.solid : C.muted,
                    at: mid - 20, align: "right", hidden: tease.value });
  slot(row.meta, { font: `500 28px ${FONT_BODY}`, colour: C.muted,
                   at: mid + 28, align: "right", hidden: tease.meta });
};

/**
 * Render a Story to a canvas. The caller supplies the canvas so this works both in the
 * browser and anywhere else one can be made.
 *
 * rows: { name, line, record, when, solid, league_id }
 * showClear: how many rows are left unblurred (the proof), the rest are teased.
 */
export const renderStory = (canvas, {
  title = "Corner streaks",
  subtitle = "",
  rows = [],
  showClear = 0,
  maxRows = 6,
  cta = "Model + odds → paid Telegram",
  brand = "CORNER MODEL",
  // What to claim in the footer. Defaults to the rows drawn; a teased day passes the
  // true total, because "3 angles live" under "the top 3 of 5" is a smaller number than
  // the sentence above it and reads as a contradiction.
  totalCount = null,
  blurRadius = 11,
} = {}) => {
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, STORY_W, STORY_H);

  // A cyan wash behind the header, the same accent the site leads with.
  const glow = ctx.createRadialGradient(STORY_W / 2, 240, 60, STORY_W / 2, 240, 900);
  glow.addColorStop(0, "rgba(0,229,255,0.16)");
  glow.addColorStop(1, "rgba(0,229,255,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, STORY_W, 1100);

  ctx.textBaseline = "middle";
  ctx.fillStyle = C.primary;
  ctx.font = `700 30px ${FONT_HEAD}`;
  ctx.letterSpacing = "6px";
  ctx.fillText(brand, 72, 200);
  ctx.letterSpacing = "0px";

  ctx.fillStyle = C.text;
  ctx.font = fitFont(ctx, title, { size: 76, max: STORY_W - 144, family: FONT_HEAD });
  ctx.fillText(title, 72, 300);

  if (subtitle) {
    ctx.fillStyle = C.muted;
    ctx.font = fitFont(ctx, subtitle, { size: 34, max: STORY_W - 144, weight: 500, family: FONT_BODY });
    ctx.fillText(subtitle, 72, 372);
  }

  const useFlags = flagsRender(ctx);
  const shown = rows.slice(0, maxRows).map((r, i) => ({
    ...r,
    flag: flagFor(r.league_id),
    code: countryCodeFor(r.league_id),
      // The first `showClear` rows are whole. It defaults to NONE: on the mismatch
    // board the fixtures are already legible, so they carry the proof on their own and
    // a free row would just be the product given away. Streaks are the case that
    // needs it — every row there is teased on the team, so a fully blurred list shows
    // nothing identifiable at all.
    tease: i < showClear ? {} : (r.tease || {}),
  }));

  // Rows are CENTRED in the band between the header and the call to action rather than
  // stacked from the top. A weekend top-3 is half the length of a weekday list, and
  // top-aligning it leaves a third of the story visibly empty — which reads as a broken
  // image rather than a short list.
  const bandTop = 440;
  const bandBottom = STORY_H - 420;
  const blockH = shown.length * 172 - 22;
  // Biased above centre: a block sitting on the exact midpoint reads as drifting away
  // from the headline it belongs to.
  let y = Math.max(bandTop, bandTop + (bandBottom - bandTop - blockH) * 0.38);
  shown.forEach((row) => {
    drawRow(ctx, row, y, { useFlags, blurRadius });
    y += 172;
  });

  // The ask. Placed clear of the bottom 250px, which Instagram's own UI covers.
  const ctaY = STORY_H - 340;
  ctx.fillStyle = C.primary;
  roundRect(ctx, 72, ctaY, STORY_W - 144, 108, 54);
  ctx.fill();
  ctx.fillStyle = "#00181C";
  ctx.font = `700 38px ${FONT_HEAD}`;
  ctx.textAlign = "center";
  ctx.fillText(cta, STORY_W / 2, ctaY + 56);

  ctx.fillStyle = C.muted;
  ctx.font = `500 26px ${FONT_BODY}`;
  const total = totalCount ?? rows.length;
  ctx.fillText(`${total} ${total === 1 ? "angle" : "angles"} live · corner-model`, STORY_W / 2, ctaY + 168);
  ctx.textAlign = "left";

  return canvas;
};

/**
 * Streak rows as the story wants them. The team and the line are what's held back: the
 * record and the kick-off stay, so the claim is checkable but not actionable.
 */
export const streakStoryRows = (rows = [], { isUnder = false } = {}) =>
  rows.map((r) => {
    const settled = r.settled ?? r.window;
    return {
      league_id: r.league_id,
      headline: r.name,
      sub: `${isUnder ? "U" : ""}${r.line}${isUnder ? "" : "+"} corners`,
      value: `${r.hits}/${settled}`,
      meta: kickoffLabel(r.next_fixture?.date),
      solid: settled > 0 && r.hits / settled >= 0.8,
      tease: { sub: true },
    };
  });

/**
 * Mismatch rows. The FIXTURE is the tease here, so it stays sharp and the numbers go:
 * the line, the projection and the model's fair odds are the paid product, and a reader
 * who can read them off the picture has no reason to join anything.
 *
 * `real_samples` doubles as the quality mark, the same 6-game bar the Top Mismatch card
 * uses — a mismatch is a lambda comparison with no hit-rate behind it, so sample is what
 * makes one solid.
 */
export const mismatchStoryRows = (rows = [], { timeOnly = false } = {}) =>
  rows.map((r) => {
    const fx = r.next_fixture || {};
    return {
      league_id: r.league_id,
      headline: fx.opponent ? `${r.name} ${fx.is_home ? "v" : "@"} ${fx.opponent}` : r.name,
      // On a per-day story the day is the headline, so the row needs only a clock.
      sub: timeOnly ? kickoffTime(fx.date) : kickoffLabel(fx.date),
      value: `${r.line}+ @ ${Number(r.fair_odds).toFixed(2)}`,
      meta: `λ ${r.lambda}`,
      solid: (r.real_samples || 0) >= 6,
      tease: { value: true, meta: true },
    };
  });

/**
 * "Today" / "Tomorrow" / "Saturday" — a day as a story headline wants it.
 *
 * Wider than kickoffDay, which gives "Sat 6 Sep" past tomorrow. On a picture posted the
 * same week, the weekday alone is what a reader parses; the date is noise they have to
 * do arithmetic on.
 */
export const storyDayLabel = (iso) => {
  const near = kickoffDay(iso);
  if (near === "Today" || near === "Tomorrow" || !near) return near;
  return new Date(iso).toLocaleDateString(undefined, { weekday: "long" });
};

const isWeekendDay = (iso) => [0, 6].includes(new Date(iso).getDay());

/**
 * One story per matchday, rather than one story for everything.
 *
 * A single image covering three days makes a reader work out which rows are tonight —
 * and the rows they can act on now are the only ones that convert. Split by day, each
 * story has one answer to "when".
 *
 * The weekend gets a SHORTER list on purpose. Saturday has far more football on it, so
 * an honest full list is unreadable at story size and a truncated one is arbitrary; three
 * is a top three, which is a claim worth making rather than a slice of a longer list.
 */
export const mismatchStoryDays = (rows = [], { weekendRows = 3, weekdayRows = 6 } = {}) => {
  const byDay = new Map();
  for (const r of rows) {
    const date = r.next_fixture?.date;
    if (!date) continue;                       // a row with no fixture belongs to no day
    const d = new Date(date);
    if (Number.isNaN(d.getTime())) continue;
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;   // LOCAL day, not UTC
    if (!byDay.has(key)) byDay.set(key, { key, date, rows: [] });
    byDay.get(key).rows.push(r);
  }
  return [...byDay.values()]
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map((day) => {
      const weekend = isWeekendDay(day.date);
      const limit = weekend ? weekendRows : weekdayRows;
      const kept = day.rows.slice(0, limit);
      return {
        key: day.key,
        date: day.date,
        weekend,
        label: storyDayLabel(day.date),
        title: `${storyDayLabel(day.date)}'s mismatches`,
        subtitle: weekend && day.rows.length > limit
          ? `The top ${kept.length} of ${day.rows.length} on the card`
          : "Corner-heavy sides against sides that concede them",
        rows: mismatchStoryRows(kept, { timeOnly: true }),
        totalCount: day.rows.length,
      };
    });
};
