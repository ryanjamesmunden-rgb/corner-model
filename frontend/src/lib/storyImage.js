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
// These are the REBRAND values — the previous set (#0A0A0A on #00E5FF) was the pre-rebrand
// theme and a story drawn with it now reads as a different product to the page it links to.
const C = {
  bg: "#0B0F14",          // --background 215 30% 6%
  card: "#11161D",        // --card
  secondary: "#1A2028",
  border: "#282F39",
  text: "#F3F5F7",
  muted: "#98A4B3",
  primary: "#14DBF5",     // --primary 187 92% 52%
  solid: "#39D0A3",       // --tone-strong-fg, the green a solid run wears on the board
  dim: "#3B4654",         // counts that lose the bet, in the chart
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

// ANIMATION TIMING. A story is drawn as one function of `progress` (0..1) rather than as
// a sequence of steps, so the still image is simply the frame at 1 and there is no second
// implementation to drift. Every element below reads its own window out of that number.
const clamp01 = (t) => (t < 0 ? 0 : t > 1 ? 1 : t);
/** easeOutCubic — fast then settling, which is what makes a bar look like it lands. */
const ease = (t) => 1 - Math.pow(1 - clamp01(t), 3);
/** How far through its own window [from, to] the animation is. */
const seg = (t, from, to) => ease((t - from) / (to - from));

/** Draw with a temporary alpha, restoring whatever was set before. */
const faded = (ctx, alpha, draw) => {
  if (alpha <= 0) return;
  const prev = ctx.globalAlpha;
  ctx.globalAlpha = alpha;
  draw();
  ctx.globalAlpha = prev;
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

// ----------------------------- One fixture, as a picture -----------------------------
//
// The board stories tease a LIST. This teases a SINGLE GAME, and the split is different
// again: here the PROBABILITY is the whole point of posting — "59% chance of 10+ corners"
// is a claim a reader can weigh, argue with and remember — while the model's price is the
// thing worth clicking for. So the percentage goes out sharp and the price goes out
// blurred, in the slot where a price obviously belongs.
//
// Blurred rather than absent, deliberately. An omitted price reads as a site that does not
// have one; a blurred price reads as a number being withheld, which is the difference
// between looking incomplete and looking like there is something behind the door.

/** The line this market is really about: the one nearest the projection. */
const featureLine = (rows, lam) => {
  if (!rows.length) return null;
  const target = Math.max(1, Math.round(lam || 0));
  return rows.reduce((best, r) => {
    const k = Math.ceil(r.line ?? parseFloat(String(r.key).split("_").pop()));
    const bk = Math.ceil(best.line ?? parseFloat(String(best.key).split("_").pop()));
    return Math.abs(k - target) < Math.abs(bk - target) ? r : best;
  });
};

/**
 * The three markets a fixture story shows, each at its headline line.
 *
 * Returns [] rather than half a story when the model has no markets, so a caller can
 * disable the button instead of producing a picture with empty rows on it.
 */
export const fixtureStoryMarkets = (markets = [], lambdas = {}, { homeName, awayName } = {}) =>
  [["total", "Match total"], ["home", homeName], ["away", awayName]]
    .map(([group, label]) => {
      const row = featureLine((markets || []).filter((m) => m.group === group), lambdas[group]);
      if (!row || row.prob == null) return null;
      const k = Math.ceil(row.line ?? parseFloat(String(row.key).split("_").pop()));
      return {
        group,
        label: label || group,
        line: k,
        prob: row.prob,
        // Carried so the blurred slot has real text under it — a blur over a placeholder
        // is a lie about what is being withheld, and the shape of a real number is part
        // of what makes the tease read as one.
        price: row.fair_odds != null ? Number(row.fair_odds).toFixed(2) : null,
      };
    })
    .filter(Boolean);

/**
 * The curve, drawn as bars. Counts that win the bet are lit; the rest recede.
 *
 * `progress` grows them from the baseline, staggered left to right so the shape draws
 * itself rather than appearing whole — which is the bit that makes a reader watch.
 */
const drawCurve = (ctx, dist, line, { x, y, w, h, progress = 1,
                                      mark = null, markTone = null, markAt = 1 }) => {
  if (!dist?.length) return;
  const peak = Math.max(...dist.map((d) => d.p)) || 1;
  const gap = 6;
  const bw = (w - gap * (dist.length - 1)) / dist.length;
  // The last bar starts at 0.55 of the curve's own window, so the stagger is always
  // finished by the end however many bars there are.
  const stagger = 0.55 / Math.max(1, dist.length - 1);
  dist.forEach((d, i) => {
    const grow = progress >= 1 ? 1 : seg(progress, i * stagger, i * stagger + 0.45);
    if (grow <= 0) return;
    const bh = Math.max(4, (d.p / peak) * h) * grow;
    const bx = x + i * (bw + gap);
    ctx.fillStyle = d.k >= line ? C.primary : C.dim;
    // Radius clamped by HEIGHT as well as width: the tails of a corner distribution are
    // a few pixels tall, and an 8px corner on a 4px bar draws as a curved tick rather
    // than a bar — which is what the first render of this actually did.
    roundRect(ctx, bx, y + h - bh, bw, bh, Math.min(8, bw / 2, bh / 2));
    ctx.fill();
  });
  // Only the ends and the line itself are labelled. A number under all twenty bars is
  // unreadable at story size and adds nothing a reader is going to act on.
  ctx.globalAlpha = progress >= 1 ? 1 : seg(progress, 0.55, 0.9);
  ctx.fillStyle = C.muted;
  ctx.font = `500 24px ${FONT_DATA}`;
  ctx.textAlign = "center";
  [dist[0].k, line, dist[dist.length - 1].k].forEach((k) => {
    const i = dist.findIndex((d) => d.k === k);
    if (i < 0) return;
    ctx.fillStyle = k === line ? C.primary : C.muted;
    ctx.fillText(String(k), x + i * (bw + gap) + bw / 2, y + h + 30);
  });
  ctx.globalAlpha = 1;

  // WHERE IT ACTUALLY LANDED, pinned on the shape that was published. The bar is
  // repainted in the verdict's colour and flagged above, so the argument — this is the
  // curve we showed you, and this is where the game finished on it — needs no caption.
  if (mark != null && markAt > 0) {
    const i = dist.findIndex((d) => d.k === mark);
    if (i >= 0) {
      const tone = markTone || C.primary;
      const cx = x + i * (bw + gap) + bw / 2;
      const bh = Math.max(4, (dist[i].p / peak) * h);
      ctx.globalAlpha = markAt;
      ctx.fillStyle = tone;
      roundRect(ctx, x + i * (bw + gap), y + h - bh, bw, bh, Math.min(8, bw / 2, bh / 2));
      ctx.fill();
      // A stem up to a chip, so the pin reads even where the bar is a few pixels tall —
      // which it will be, because a result that clears the line comfortably sits out in
      // the thin end of the distribution.
      ctx.strokeStyle = tone;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(cx, y + h - bh - 8);
      ctx.lineTo(cx, y - 26);
      ctx.stroke();
      ctx.font = `700 30px ${FONT_DATA}`;
      const cw = ctx.measureText(String(mark)).width + 32;
      ctx.fillStyle = tone;
      roundRect(ctx, cx - cw / 2, y - 66, cw, 44, 22);
      ctx.fill();
      ctx.fillStyle = C.bg;
      ctx.textAlign = "center";
      ctx.fillText(String(mark), cx, y - 43);
      ctx.globalAlpha = 1;
    }
  }
  ctx.textAlign = "left";
};

/**
 * One fixture as a Story: the curve, the headline probability, and the three markets with
 * their prices held back.
 *
 * `dist` is the distribution for `group` — the same rows the site's chart draws, which
 * come from the backend's pmf. Drawing a curve here from some other maths would put a
 * different shape on the internet to the one the page shows.
 */
export const renderFixtureStory = (canvas, {
  homeName = "", awayName = "", leagueId = "", kickoff = "",
  dist = [], group = "total", markets = [],
  cta = "Model price on the site", brand = "CORNER MODEL", blurRadius = 14,
  // 1 is the finished frame, which is exactly what the still image wants — so the PNG and
  // the video are the same drawing code and cannot drift apart.
  progress = 1,
} = {}) => {
  const P = clamp01(progress);
  const done = P >= 1;
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, STORY_W, STORY_H);
  const glow = ctx.createRadialGradient(STORY_W / 2, 240, 60, STORY_W / 2, 240, 900);
  glow.addColorStop(0, "rgba(20,219,245,0.16)");
  glow.addColorStop(1, "rgba(20,219,245,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, STORY_W, 1100);

  ctx.textBaseline = "middle";
  const useFlags = flagsRender(ctx);   // probed before any alpha is in play
  faded(ctx, done ? 1 : seg(P, 0, 0.07), () => {
    ctx.fillStyle = C.primary;
    ctx.font = `700 30px ${FONT_HEAD}`;
    ctx.letterSpacing = "6px";
    ctx.fillText(brand, 72, 180);
    ctx.letterSpacing = "0px";

    // The fixture, on two lines. Team names are long and unpredictable, and one line of
    // "Borussia Monchengladbach v Eintracht Frankfurt" shrinks to unreadable.
    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, homeName, { size: 68, max: STORY_W - 144, family: FONT_HEAD });
    ctx.fillText(homeName, 72, 272);
    ctx.fillStyle = C.muted;
    ctx.font = `500 34px ${FONT_BODY}`;
    ctx.fillText("v", 72, 336);
    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, awayName, { size: 68, max: STORY_W - 200, family: FONT_HEAD });
    ctx.fillText(awayName, 118, 336);

    const flag = useFlags ? flagFor(leagueId) : null;
    const where = [flag || countryCodeFor(leagueId), kickoff].filter(Boolean).join("  ·  ");
    if (where) {
      ctx.fillStyle = C.muted;
      ctx.font = `500 30px ${FONT_BODY}`;
      ctx.fillText(where, 72, 404);
    }
  });

  const head = markets.find((m) => m.group === group) || markets[0];

  // THE NUMBER. This is what the post is for, so it is the biggest thing on the image, and
  // it COUNTS UP: a number climbing to 59 is watched, a number that is already 59 is read
  // in a glance and scrolled past.
  if (head) {
    const count = done ? 1 : seg(P, 0.06, 0.55);
    faded(ctx, done ? 1 : seg(P, 0.04, 0.13), () => {
      ctx.fillStyle = C.primary;
      ctx.font = `700 150px ${FONT_DATA}`;
      ctx.fillText(`${Math.round(head.prob * count)}%`, 72, 560);
      ctx.fillStyle = C.text;
      ctx.font = `600 40px ${FONT_HEAD}`;
      ctx.fillText(`chance of ${head.line}+ ${head.group === "total" ? "match corners" : "corners"}`, 72, 654);
      if (head.group !== "total") {
        ctx.fillStyle = C.muted;
        ctx.font = `500 32px ${FONT_BODY}`;
        ctx.fillText(head.label, 72, 706);
      }
    });
  }

  // The curve runs alongside the count rather than after it, so the bars and the number
  // arrive together — the shape IS the explanation of the number.
  drawCurve(ctx, dist, head?.line ?? 0,
            { x: 72, y: 780, w: STORY_W - 144, h: 300,
              progress: done ? 1 : clamp01((P - 0.07) / 0.52) });

  // The three markets. Probability sharp, price blurred.
  //
  // Sized to END ABOVE the call to action rather than at a fixed offset: three rows at the
  // old spacing ran under the pill and cut the away team's row in half. The band is what is
  // actually available, so a fourth market would tighten rather than overflow.
  const rowsTop = 1130;
  const rowsBottom = STORY_H - 380;
  const gap = 16;
  const rowH = Math.min(132, Math.floor((rowsBottom - rowsTop - gap * (markets.length - 1))
                                        / Math.max(1, markets.length)));
  let y = rowsTop;
  markets.forEach((m, i) => {
    const h = rowH;
    // Each row arrives on its own beat and slides up as it fades, which reads as a list
    // being dealt out rather than three boxes appearing at once.
    const at = done ? 1 : seg(P, 0.52 + i * 0.09, 0.52 + i * 0.09 + 0.22);
    if (at <= 0) { y += h + gap; return; }
    const lift = (1 - at) * 28;
    ctx.save();
    ctx.globalAlpha = at;
    ctx.translate(0, lift);
    ctx.fillStyle = C.card;
    roundRect(ctx, 72, y, STORY_W - 144, h, 20);
    ctx.fill();
    ctx.strokeStyle = m.group === group ? `${C.primary}55` : C.border;
    ctx.lineWidth = 2;
    ctx.stroke();

    const mid = y + h / 2;
    ctx.fillStyle = C.text;
    ctx.font = `600 34px ${FONT_HEAD}`;
    ctx.textBaseline = "middle";
    ctx.fillText(m.label, 116, mid - 20);
    ctx.fillStyle = C.muted;
    ctx.font = `500 28px ${FONT_BODY}`;
    ctx.fillText(`${m.line}+ corners`, 116, mid + 22);

    // Probability — the half that goes out in public.
    ctx.fillStyle = C.primary;
    ctx.font = `700 46px ${FONT_DATA}`;
    ctx.textAlign = "right";
    ctx.fillText(`${Math.round(m.prob)}%`, STORY_W - 260, mid);

    // Price — the half that does not. Real text under the blur.
    blurred(ctx, () => {
      ctx.fillStyle = C.solid;
      ctx.font = `700 44px ${FONT_DATA}`;
      ctx.fillText(m.price || "0.00", STORY_W - 116, mid - 14);
      ctx.fillStyle = C.muted;
      ctx.font = `500 22px ${FONT_BODY}`;
      ctx.fillText("model price", STORY_W - 116, mid + 28);
    }, blurRadius);
    ctx.textAlign = "left";
    ctx.restore();
    y += h + gap;
  });

  // The ask lands LAST. It is the thing to remember after the number has been read, and
  // arriving first would make the whole story look like an advert.
  faded(ctx, done ? 1 : seg(P, 0.84, 1), () => {
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
    ctx.fillText("corner-model", STORY_W / 2, ctaY + 168);
    ctx.textAlign = "left";
  });

  return canvas;
};

// ----------------------------- One angle, and why it is one -----------------------------
//
// The daily mismatch story is a LIST — six fixtures, scanned. This is one angle argued in
// full: the two numbers that make it, said in words, with the sample behind them.
//
// THE REASONING IS BUILT FROM THE NUMBERS, NOT FROM THE EXPLAINER. The "Why this angle?"
// prose on the card is written by a model that is handed the line, the probability AND the
// fair odds, and told to reference the concrete numbers — so it routinely contains the
// price. Putting that on a public image would give away precisely what every other story
// here blurs. This says the same thing from the same data, deterministically, and cannot
// leak a price because it is never given one.

/** Break `text` into lines that fit `max` px at the CURRENT font. Canvas will not wrap. */
export const wrapText = (ctx, text, max) => {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const lines = [];
  let line = words[0];
  for (const w of words.slice(1)) {
    const next = `${line} ${w}`;
    if (ctx.measureText(next).width <= max) {
      line = next;
    } else {
      lines.push(line);
      line = w;
    }
  }
  lines.push(line);
  return lines;
};

/**
 * Why this angle is an angle, in plain words, from the row's own numbers.
 *
 * Deliberately says NOTHING about the line, the projection or the price — those are the
 * paid half and are blurred on the image. What is left is the claim a reader can weigh:
 * a side that wins corners playing a side that gives them away.
 */
export const angleWhy = (r = {}, nf = {}) => {
  // Checked for absence BEFORE coercing: Number(null) is 0, not NaN, so a null average
  // would otherwise sail through isFinite and be published as "0.0 corners a game" —
  // a fabricated number on a public image, which is the worst failure this file has.
  if (r.team_for == null || r.opp_conceded == null) return [];
  const won = Number(r.team_for);
  const conceded = Number(r.opp_conceded);
  if (!Number.isFinite(won) || !Number.isFinite(conceded)) return [];
  const where = nf.is_home ? "at home" : "away";
  const out = [
    `${r.name} win ${won.toFixed(1)} corners a game ${where}. `
    + `${nf.opponent || "Their opponent"} concede ${conceded.toFixed(1)}.`,
  ];
  // The second line is about how lopsided it is, which is the part worth arguing about.
  const gap = Math.min(won, conceded);
  out.push(gap >= 7
    ? "Both ends of that are extreme. The corners have to come from somewhere."
    : gap >= 6
      ? "A side that wins corners against a side that gives them away — that is the whole angle."
      : "Both numbers sit above par, which is what puts this game on the board at all.");
  const games = Number(r.real_samples) || 0;
  if (games) out.push(`Measured over ${games} games, not a hunch.`);
  return out;
};

/**
 * How to describe a run of recent games WITHOUT overclaiming the venue.
 *
 * `_real_avg_detail` falls back to every venue when the home/away pool is thinner than
 * three games. On the card that fallback is spelled out in an amber warning; on an image
 * there is no room for a warning, so the label itself has to be true — "last 6 at home"
 * over a mixed run would be a lie printed on something public.
 */
export const gamesLabel = (d = {}, n = 0) => {
  const asked = d.venue_asked === "home" ? "at home" : d.venue_asked === "away" ? "away" : "";
  const mixed = d.venue_used === "all" && asked;
  return `LAST ${n}${mixed ? ", ALL VENUES" : asked ? ` ${asked.toUpperCase()}` : ""}`;
};

/** A run of games as bars, oldest to newest — the shape of the form behind the average. */
const drawGames = (ctx, values, { x, y, w, h, tone }) => {
  const vals = (values || []).slice().reverse();     // stored newest-first; read left to right
  if (!vals.length) return;
  const peak = Math.max(...vals, 1);
  const gap = 10;
  const bw = (w - gap * (vals.length - 1)) / vals.length;
  vals.forEach((v, i) => {
    const bh = Math.max(6, (v / peak) * h);
    const bx = x + i * (bw + gap);
    ctx.fillStyle = tone;
    roundRect(ctx, bx, y + h - bh, bw, bh, Math.min(8, bw / 2, bh / 2));
    ctx.fill();
    ctx.fillStyle = C.muted;
    ctx.font = `500 22px ${FONT_DATA}`;
    ctx.textAlign = "center";
    ctx.fillText(String(v), bx + bw / 2, y + h + 26);
    ctx.textAlign = "left";
  });
};

/** One mismatch argued in full. Numbers and reasoning public; line, price and λ held back. */
/**
 * One mismatch, built to be TAPPED.
 *
 * The first version of this was honest and dull: three paragraphs of body copy on a dark
 * field, with the withheld price in a small grey strip nobody's eye went to. On a feed
 * that loses. So the composition now leads with the fixture, proves it with the two
 * numbers and their recent form, and lands on a BETSLIP — a light card against the dark,
 * which is the one shape a punter recognises instantly and wants to read the odds off.
 *
 * WHAT GOES PUBLIC CHANGED, DELIBERATELY. The earlier version blurred the line as well as
 * the price, which left "62%" floating with nothing to be 62% OF — incoherent, and it
 * disagreed with the fixture story, which prints its line ("chance of 10+ match corners")
 * and blurs only the price. So the line and the probability are now public here too, and
 * the price alone is held back. That is the rule the whole site follows.
 */
export const renderAngleStory = (canvas, {
  row = {}, fixture = {}, kickoff = "",
  // 13, tuned by rendering it. This blur sits on a LIGHT card, so it behaves differently
  // to the 14-16 the dark stories use: at 16 it stopped reading as a hidden number and
  // became an empty grey box, which kills the curiosity the slip exists to create; at 11
  // the digits were starting to be legible, which defeats the point entirely.
  cta = "See the price on the site", brand = "CORNER MODEL", blurRadius = 13,
} = {}) => {
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext("2d");
  const M = 72;                       // page margin
  const W = STORY_W - M * 2;

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, STORY_W, STORY_H);
  // Two washes rather than one: a cyan bloom behind the header and a warm one low down
  // behind the slip, so the eye is pulled down the page instead of sitting at the top.
  const top = ctx.createRadialGradient(220, 180, 40, 220, 180, 1000);
  top.addColorStop(0, "rgba(20,219,245,0.20)");
  top.addColorStop(1, "rgba(20,219,245,0)");
  ctx.fillStyle = top;
  ctx.fillRect(0, 0, STORY_W, 1200);
  const low = ctx.createRadialGradient(880, 1520, 40, 880, 1520, 820);
  low.addColorStop(0, "rgba(11,168,121,0.18)");
  low.addColorStop(1, "rgba(11,168,121,0)");
  ctx.fillStyle = low;
  ctx.fillRect(0, 1000, STORY_W, STORY_H - 1000);

  ctx.textBaseline = "middle";
  const useFlags = flagsRender(ctx);

  // --- header: brand, section, then the FIXTURE as the hero ---
  ctx.fillStyle = C.primary;
  ctx.font = `700 26px ${FONT_HEAD}`;
  ctx.letterSpacing = "6px";
  ctx.fillText(brand, M, 132);
  ctx.letterSpacing = "0px";

  ctx.fillStyle = C.muted;
  ctx.font = `600 28px ${FONT_HEAD}`;
  ctx.letterSpacing = "4px";
  ctx.fillText("CORNER MISMATCHES", M, 186);
  ctx.letterSpacing = "0px";

  const home = fixture.is_home ? row.name : fixture.opponent;
  const away = fixture.is_home ? fixture.opponent : row.name;
  ctx.fillStyle = C.text;
  ctx.font = fitFont(ctx, home || "", { size: 66, max: W, family: FONT_HEAD });
  ctx.fillText(home || "", M, 268);
  ctx.fillStyle = C.muted;
  ctx.font = `500 32px ${FONT_BODY}`;
  ctx.fillText("v", M, 332);
  ctx.fillStyle = C.text;
  ctx.font = fitFont(ctx, away || "", { size: 66, max: W - 46, family: FONT_HEAD });
  ctx.fillText(away || "", M + 46, 332);

  const where = [
    (useFlags ? flagFor(row.league_id) : null) || countryCodeFor(row.league_id), kickoff,
  ].filter(Boolean).join("  ·  ");
  if (where) {
    ctx.fillStyle = C.muted;
    ctx.font = `500 28px ${FONT_BODY}`;
    ctx.fillText(where, M, 396);
  }

  // --- the two numbers that are the angle, each over its own recent form ---
  const ev = row.evidence || {};
  const panelY = 456;
  const hasBars = !!(ev.team?.recent?.length || ev.opponent?.recent?.length);
  const panelH = hasBars ? 452 : 320;
  const halfW = (W - 24) / 2;
  const half = (x, kicker, name, value, tone, detail) => {
    ctx.fillStyle = C.card;
    roundRect(ctx, x, panelY, halfW, panelH, 26);
    ctx.fill();
    ctx.strokeStyle = `${tone}44`;
    ctx.lineWidth = 2;
    ctx.stroke();
    // A colour stripe down the edge, so the two sides read as opposed at a glance.
    ctx.fillStyle = tone;
    roundRect(ctx, x, panelY, 8, panelH, 4);
    ctx.fill();

    ctx.fillStyle = tone;
    ctx.font = `700 24px ${FONT_HEAD}`;
    ctx.letterSpacing = "3px";
    ctx.fillText(kicker, x + 34, panelY + 50);
    ctx.letterSpacing = "0px";
    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, name || "", { size: 36, max: halfW - 66, weight: 600, family: FONT_HEAD });
    ctx.fillText(name || "", x + 34, panelY + 104);
    ctx.fillStyle = tone;
    ctx.font = `700 104px ${FONT_DATA}`;
    ctx.fillText(value, x + 34, panelY + 196);
    ctx.fillStyle = C.muted;
    ctx.font = `500 25px ${FONT_BODY}`;
    ctx.fillText("corners a game", x + 34, panelY + 262);

    const runs = detail?.recent || [];
    if (!runs.length) return;
    ctx.strokeStyle = C.border;
    ctx.beginPath();
    ctx.moveTo(x + 34, panelY + 296);
    ctx.lineTo(x + halfW - 34, panelY + 296);
    ctx.stroke();
    ctx.fillStyle = C.muted;
    ctx.font = `600 19px ${FONT_DATA}`;
    ctx.letterSpacing = "2px";
    ctx.fillText(gamesLabel(detail, runs.length), x + 34, panelY + 332);
    ctx.letterSpacing = "0px";
    drawGames(ctx, runs, { x: x + 34, y: panelY + 356, w: halfW - 68, h: 60, tone });
  };
  half(M, "WINS", row.name, Number(row.team_for || 0).toFixed(1), C.solid, ev.team);
  half(M + halfW + 24, "CONCEDES", fixture.opponent,
       Number(row.opp_conceded || 0).toFixed(1), "#F99B2F", ev.opponent);

  // THE BOTTOM OF THE PAGE IS FIXED, and everything else fits around it. Instagram draws
  // its own controls over roughly the last 250px, so the call to action sits where the
  // other stories put it and the slip is placed UP from there — the first cut of this
  // grew downward from the copy instead and pushed the button under Instagram's UI.
  const slipH = 300;
  const ctaY = STORY_H - 340;
  const slipY = ctaY - 46 - slipH;

  // --- the hook: ONE line, big, CENTRED in whatever band is left. Three paragraphs was a
  // page, not a post — and a fixed offset left a visible hole above the slip. ---
  const hook = angleWhy(row, fixture)[1];
  if (hook) {
    ctx.font = `600 40px ${FONT_HEAD}`;
    const lns = wrapText(ctx, hook, W);
    const bandTop = panelY + panelH;
    const blockH = lns.length * 52;
    let hy = bandTop + Math.max(56, (slipY - bandTop - blockH) / 2);
    lns.forEach((ln) => {
      ctx.fillStyle = C.text;
      ctx.font = `600 40px ${FONT_HEAD}`;
      ctx.fillText(ln, M, hy);
      hy += 52;
    });
  }

  // --- THE BETSLIP. Light card on a dark field: the one shape a punter reads instantly. ---
  ctx.fillStyle = C.text;                      // near-white, so it lifts off the page
  roundRect(ctx, M, slipY, W, slipH, 28);
  ctx.fill();

  ctx.fillStyle = "#6B7683";
  ctx.font = `700 22px ${FONT_HEAD}`;
  ctx.letterSpacing = "4px";
  ctx.fillText("MODEL BETSLIP", M + 40, slipY + 52);
  ctx.letterSpacing = "0px";

  // Selection and line — PUBLIC, because a probability with no line is 62% of nothing.
  ctx.fillStyle = "#0B0F14";
  ctx.font = fitFont(ctx, row.name || "", { size: 40, max: W - 320, weight: 700, family: FONT_HEAD });
  ctx.fillText(row.name || "", M + 40, slipY + 116);
  ctx.fillStyle = "#0BA879";
  ctx.font = `700 46px ${FONT_DATA}`;
  ctx.fillText(`${row.line ?? ""}+ corners`, M + 40, slipY + 178);

  if (row.prob != null) {
    ctx.fillStyle = "#6B7683";
    ctx.font = `500 26px ${FONT_BODY}`;
    ctx.fillText(`Model gives it ${Math.round(row.prob)}%`, M + 40, slipY + 236);
  }

  // The price. The only thing held back, in the box a price belongs in.
  const boxW = 210;
  const boxX = M + W - boxW - 40;
  ctx.fillStyle = "#E4E8EC";
  roundRect(ctx, boxX, slipY + 84, boxW, 128, 18);
  ctx.fill();
  blurred(ctx, () => {
    ctx.fillStyle = "#0B0F14";
    ctx.font = `700 62px ${FONT_DATA}`;
    ctx.textAlign = "center";
    ctx.fillText(Number(row.fair_odds || 0).toFixed(2), boxX + boxW / 2, slipY + 148);
    ctx.textAlign = "left";
  }, blurRadius);
  ctx.fillStyle = "#6B7683";
  ctx.font = `600 20px ${FONT_BODY}`;
  ctx.textAlign = "center";
  ctx.fillText("MODEL PRICE", boxX + boxW / 2, slipY + 236);
  ctx.textAlign = "left";

  // --- the ask ---
  ctx.fillStyle = C.primary;
  roundRect(ctx, M, ctaY, W, 104, 52);
  ctx.fill();
  ctx.fillStyle = "#00181C";
  ctx.font = fitFont(ctx, cta, { size: 38, max: W - 140, family: FONT_HEAD });
  ctx.textAlign = "center";
  ctx.fillText(cta, STORY_W / 2, ctaY + 54);
  ctx.fillStyle = C.muted;
  ctx.font = `500 25px ${FONT_BODY}`;
  ctx.fillText("corner-model", STORY_W / 2, ctaY + 158);
  ctx.textAlign = "left";

  return canvas;
};

// ----------------------------- How it landed -----------------------------
//
// The preview story asks people to believe a percentage. This one shows what happened,
// and it is the more persuasive of the two by a distance: "we said 63% chance of 5+" is a
// claim, "it finished on 11" is a fact anyone can check.
//
// THE COUNT IS THE ANIMATION. A number climbing 0 → 11 is watched to the end; the same
// number sitting still is read and scrolled past. Everything else on the image exists to
// say what that number was measured against.
//
// NO PRICE HERE EITHER. Same rule as every other public image: the line and the outcome
// go out, the model's price stays on the site.

/** Won, lost or pushed — in the words and colours the site already uses for each. */
export const resultVerdict = (result) => {
  if (result === "win") return { word: "LANDED", tone: "#39D0A3", sub: "as called" };
  if (result === "loss") return { word: "MISSED", tone: "#F2557E", sub: "it happens" };
  if (result === "void") return { word: "PUSH", tone: "#98A4B3", sub: "exact line — stake back" };
  return null;      // pending has no story to tell yet
};

/**
 * What the result did relative to the line, in one phrase.
 *
 * Says the MARGIN rather than repeating the two numbers already on the image. "Six clear"
 * is the part a reader would have to work out themselves, and it is the part that makes a
 * 63% call look like the right call rather than a lucky one.
 */
export const resultMargin = (value, line, direction = "over") => {
  if (value == null || line == null) return "";
  const by = direction === "under" ? line - value : value - line;
  if (by === 0) return "bang on the line";
  if (by < 0) return `${Math.abs(by)} short`;
  return by === 1 ? "1 clear" : `${by} clear`;
};


/**
 * A plain number line, for results that have no stored distribution behind them.
 *
 * Without this the image had a hole: the curve is the only thing between the headline and
 * the call to action, and an angle logged by hand carries no distribution, so a third of
 * the picture came out empty. This says the same thing the curve's pin says — here is the
 * line, here is where the game finished — using only the two numbers every result has.
 */
const drawNumberLine = (ctx, { line, value, direction, tone, x, y, w, progress = 1 }) => {
  const top = Math.max(line, value) + Math.max(2, Math.round(Math.max(line, value) * 0.35));
  const at = (n) => x + (clamp01(n / top)) * w;
  const h = 22;

  ctx.fillStyle = C.secondary;
  roundRect(ctx, x, y, w, h, h / 2);
  ctx.fill();

  // The winning side of the line, so "over" and "under" do not look identical.
  const from = direction === "under" ? x : at(line);
  const to = direction === "under" ? at(line) : x + w;
  ctx.fillStyle = `${C.primary}33`;
  roundRect(ctx, from, y, Math.max(2, to - from), h, h / 2);
  ctx.fill();

  // Where it finished, growing to its mark.
  const reach = at(value * clamp01(progress));
  ctx.fillStyle = tone;
  roundRect(ctx, x, y, Math.max(h, reach - x), h, h / 2);
  ctx.fill();

  // The line itself, as a hard tick — it is a threshold, not a quantity.
  ctx.strokeStyle = C.text;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(at(line), y - 14);
  ctx.lineTo(at(line), y + h + 14);
  ctx.stroke();

  ctx.textAlign = "center";
  ctx.fillStyle = C.muted;
  ctx.font = `500 26px ${FONT_BODY}`;
  ctx.fillText(direction === "under" ? `under ${line}` : `${line}+`, at(line), y + h + 46);

  ctx.font = `700 30px ${FONT_DATA}`;
  const cw = ctx.measureText(String(value)).width + 32;
  const cx = Math.min(Math.max(reach, x + cw / 2), x + w - cw / 2);
  ctx.globalAlpha = clamp01(progress);
  ctx.fillStyle = tone;
  roundRect(ctx, cx - cw / 2, y - 66, cw, 44, 22);
  ctx.fill();
  ctx.fillStyle = C.bg;
  ctx.fillText(String(value), cx, y - 43);
  ctx.globalAlpha = 1;
  ctx.textAlign = "left";
};


/**
 * When the corners came, across the ninety minutes.
 *
 * THE PROVIDER DOES NOT GIVE THIS. Corners arrive from /fixtures/statistics as one count
 * per team — "corner kicks: 11" — and /fixtures/events, which is where goal and card
 * minutes come from, carries goals, cards, subs and VAR only. So these minutes can only
 * be supplied by hand, and where they are absent the strip is simply not drawn rather
 * than invented.
 *
 * WHY IT IS WORTH DRAWING ANYWAY. "It finished on 11" says the bet won. This says WHEN it
 * won and what happened afterwards — the run continuing past the line is the part that
 * makes a 5+ call look like a read on the game rather than a coin that landed right.
 */
const drawCornerTimeline = (ctx, { minutes = [], line, tone, x, y, w, progress = 1 }) => {
  const mins = [...minutes].sort((a, b) => a - b);
  if (!mins.length) return;
  const full = Math.max(90, Math.ceil(Math.max(...mins) / 5) * 5);
  const at = (m) => x + clamp01(m / full) * w;

  ctx.strokeStyle = C.border;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + w, y);
  ctx.stroke();

  // Half-time, because "four before the break" is how anyone actually describes a game.
  ctx.strokeStyle = `${C.muted}66`;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 8]);
  ctx.beginPath();
  ctx.moveTo(at(45), y - 34);
  ctx.lineTo(at(45), y + 34);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.font = `500 24px ${FONT_DATA}`;
  ctx.fillStyle = C.muted;
  ctx.textAlign = "center";
  ctx.fillText("HT", at(45), y + 58);
  ctx.textAlign = "left";
  ctx.fillText("0'", x, y + 58);
  ctx.textAlign = "right";
  ctx.fillText(`${full}'`, x + w, y + 58);
  ctx.textAlign = "left";

  mins.forEach((m, i) => {
    // Each corner appears on its own beat, left to right, so the strip plays as the game
    // rather than arriving as a finished row of dots.
    const on = clamp01((progress - (i / mins.length) * 0.75) * 4);
    if (on <= 0) return;
    const won = i + 1 === line;          // the one that settled it
    const after = i + 1 > line;          // everything the run kept adding
    const r = won ? 17 : 11;
    ctx.globalAlpha = on;
    ctx.fillStyle = won ? tone : after ? `${tone}AA` : C.primary;
    ctx.beginPath();
    ctx.arc(at(m), y, r * on, 0, Math.PI * 2);
    ctx.fill();
    if (won) {
      ctx.strokeStyle = tone;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(at(m), y - 26);
      ctx.lineTo(at(m), y - 58);
      ctx.stroke();
      ctx.font = `700 26px ${FONT_DATA}`;
      ctx.fillStyle = tone;
      ctx.textAlign = "center";
      ctx.fillText(`${m}'`, at(m), y - 78);
      ctx.font = `600 22px ${FONT_BODY}`;
      ctx.fillText("bet won", at(m), y - 112);
      ctx.textAlign = "left";
    }
    ctx.globalAlpha = 1;
  });
};


/**
 * The bet slip, as a compact strip.
 *
 * WHY IT IS WORTH PUTTING ON: everything else on the image is the site's own account of
 * itself. The slip is the bookmaker's, and it is the one element a reader has no reason to
 * doubt — it carries the price that was actually available and what it actually returned.
 *
 * THE MODEL'S PRICE IS STILL NOT HERE. What this shows is the BOOK's odds, the number
 * anyone could have got by walking into the same market. The model's fair price is the
 * paid half and stays blurred wherever it appears.
 */
const drawSlip = (ctx, { selection, market, odds, stake, returns, currency = "£", tone,
                         x, y, w, progress = 1 }) => {
  const h = 132;
  faded(ctx, clamp01(progress), () => {
    ctx.fillStyle = C.card;
    roundRect(ctx, x, y, w, h, 20);
    ctx.fill();
    ctx.strokeStyle = `${tone}55`;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = tone;
    roundRect(ctx, x, y, 8, h, 4);
    ctx.fill();

    ctx.fillStyle = C.muted;
    ctx.font = `500 22px ${FONT_BODY}`;
    ctx.letterSpacing = "2px";
    ctx.fillText("BET SLIP", x + 36, y + 32);
    ctx.letterSpacing = "0px";

    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, selection, { size: 34, max: w - 260, weight: 600, family: FONT_HEAD });
    ctx.fillText(selection, x + 36, y + 74);
    if (market) {
      ctx.fillStyle = C.muted;
      ctx.font = `500 24px ${FONT_BODY}`;
      ctx.fillText(market, x + 36, y + 108);
    }

    // The money, right-aligned so the returned figure is the last thing read.
    ctx.textAlign = "right";
    if (odds != null) {
      ctx.fillStyle = C.text;
      ctx.font = `700 34px ${FONT_DATA}`;
      ctx.fillText(`@ ${Number(odds).toFixed(2)}`, x + w - 36, y + 42);
    }
    if (stake != null && returns != null) {
      ctx.fillStyle = tone;
      ctx.font = `700 40px ${FONT_DATA}`;
      ctx.fillText(`${currency}${Number(returns).toFixed(2)}`, x + w - 36, y + 92);
      ctx.fillStyle = C.muted;
      ctx.font = `500 22px ${FONT_BODY}`;
      ctx.fillText(`from ${currency}${Number(stake).toFixed(2)}`, x + w - 36, y + 122);
    }
    ctx.textAlign = "left";
  });
  return h;
};

export const renderResultStory = (canvas, {
  homeName = "", awayName = "", leagueId = "", kickoff = "",
  team = "", line = 0, direction = "over", subject = "team",
  value = 0, result = "win", prob = null,
  dist = [],
  // FULL CONTEXT, all optional. Scores are in the synced data; corner minutes are not
  // available from the provider at all and can only be passed in by hand.
  homeGoals = null, awayGoals = null,
  homeCorners = null, awayCorners = null,
  cornerMinutes = [],
  slip = null,
  cta = "The full record on the site", brand = "CORNER MODEL",
  progress = 1,
} = {}) => {
  const P = clamp01(progress);
  const done = P >= 1;
  canvas.width = STORY_W;
  canvas.height = STORY_H;
  const ctx = canvas.getContext("2d");
  const v = resultVerdict(result) || resultVerdict("win");

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, STORY_W, STORY_H);
  // The glow takes the verdict's colour rather than the brand's, so a miss does not
  // arrive dressed in the same triumphant cyan as a win.
  const glow = ctx.createRadialGradient(STORY_W / 2, 240, 60, STORY_W / 2, 240, 900);
  glow.addColorStop(0, `${v.tone}2A`);
  glow.addColorStop(1, `${v.tone}00`);
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, STORY_W, 1100);

  ctx.textBaseline = "middle";
  const useFlags = flagsRender(ctx);
  faded(ctx, done ? 1 : seg(P, 0, 0.07), () => {
    ctx.fillStyle = C.primary;
    ctx.font = `700 30px ${FONT_HEAD}`;
    ctx.letterSpacing = "6px";
    ctx.fillText(brand, 72, 180);
    ctx.letterSpacing = "0px";

    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, homeName, { size: 62, max: STORY_W - 144, family: FONT_HEAD });
    ctx.fillText(homeName, 72, 268);
    ctx.fillStyle = C.muted;
    ctx.font = `500 32px ${FONT_BODY}`;
    ctx.fillText("v", 72, 328);
    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, awayName, { size: 62, max: STORY_W - 200, family: FONT_HEAD });
    ctx.fillText(awayName, 112, 328);

    const flag = useFlags ? flagFor(leagueId) : null;
    const where = [flag || countryCodeFor(leagueId), kickoff].filter(Boolean).join("  ·  ");
    if (where) {
      ctx.fillStyle = C.muted;
      ctx.font = `500 28px ${FONT_BODY}`;
      ctx.fillText(where, 72, 392);
    }
  });

  // THE VERDICT, stamped before the number so the reader knows which way to feel about
  // the count while it is still climbing.
  faded(ctx, done ? 1 : seg(P, 0.05, 0.14), () => {
    ctx.font = `700 34px ${FONT_HEAD}`;
    ctx.letterSpacing = "3px";
    const w = ctx.measureText(v.word).width + 56;
    ctx.fillStyle = `${v.tone}22`;
    roundRect(ctx, 72, 452, w, 66, 33);
    ctx.fill();
    ctx.strokeStyle = `${v.tone}88`;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = v.tone;
    ctx.fillText(v.word, 100, 487);
    ctx.letterSpacing = "0px";
  });

  // THE COUNT. Counts up from zero to what the game actually produced.
  const climb = done ? 1 : seg(P, 0.10, 0.62);
  faded(ctx, done ? 1 : seg(P, 0.08, 0.16), () => {
    ctx.fillStyle = v.tone;
    ctx.font = `700 230px ${FONT_DATA}`;
    ctx.fillText(String(Math.round(value * climb)), 72, 690);

    ctx.fillStyle = C.text;
    ctx.font = `600 42px ${FONT_HEAD}`;
    ctx.fillText(subject === "match" ? "corners in the match" : `corners for ${team}`, 72, 828);
  });

  // WHAT IT WAS MEASURED AGAINST — the call, and how far clear it finished.
  faded(ctx, done ? 1 : seg(P, 0.62, 0.74), () => {
    const called = direction === "under" ? `under ${line}` : `${line}+`;
    ctx.fillStyle = C.muted;
    ctx.font = `500 34px ${FONT_BODY}`;
    const said = prob != null
      ? `We called ${called} at ${Math.round(prob)}%`
      : `We called ${called}`;
    ctx.fillText(said, 72, 900);
    const margin = resultMargin(value, line, direction);
    if (margin) {
      ctx.fillStyle = v.tone;
      ctx.font = `700 40px ${FONT_HEAD}`;
      ctx.fillText(margin, 72, 958);
    }
  });

  // THE SCORELINE. Both scores, because a corner count without the game around it is a
  // statistic rather than a story: eleven corners while winning 2-0 and eleven while
  // chasing a goal are different games, and the reader can tell which.
  const hasScore = homeGoals != null && awayGoals != null;
  const hasCorners = homeCorners != null && awayCorners != null;
  if (hasScore || hasCorners) {
    faded(ctx, done ? 1 : seg(P, 0.70, 0.82), () => {
      let sy = 1030;
      const pair = (label, a, b) => {
        ctx.fillStyle = C.muted;
        ctx.font = `500 26px ${FONT_BODY}`;
        ctx.fillText(label, 72, sy);
        ctx.fillStyle = C.text;
        ctx.font = `700 44px ${FONT_DATA}`;
        ctx.fillText(`${a} - ${b}`, 260, sy);
        sy += 62;
      };
      if (hasScore) pair("Final score", homeGoals, awayGoals);
      if (hasCorners) pair("Corners", homeCorners, awayCorners);
    });
  }
  const below = (hasScore || hasCorners) ? 1180 : 1100;

  // ONE PANEL, chosen by how much it actually says. The timeline wins outright — when the
  // bet was won and that the run carried on past it is the richest thing available. The
  // SLIP comes next: it is the bookmaker's account rather than the site's own, which makes
  // it the one element on the image a reader has no reason to doubt. Then the published
  // curve, then a bare number line.
  //
  // Only one, because with a scoreline above them there is not room for two — drawn
  // together, the slip card landed straight over the bars.
  if (cornerMinutes?.length) {
    faded(ctx, done ? 1 : seg(P, 0.30, 0.42), () => {
      drawCornerTimeline(ctx, {
        minutes: cornerMinutes, line, tone: v.tone,
        x: 72, y: below + 190, w: STORY_W - 144,
        progress: done ? 1 : seg(P, 0.32, 0.86),
      });
    });
  } else if (slip) {
    drawSlip(ctx, { ...slip, tone: v.tone, x: 72, y: below + 130, w: STORY_W - 144,
                    progress: done ? 1 : seg(P, 0.62, 0.80) });
  } else if (dist?.length) {
    drawCurve(ctx, dist, line, {
      // Sits lower and taller than the preview story's curve: there is no market list
      // under it here, and at the preview's position it left a third of the image empty.
      x: 72, y: below + 100, w: STORY_W - 144,
      h: Math.max(180, 1460 - (below + 100)),
      progress: done ? 1 : clamp01((P - 0.16) / 0.5),
      mark: value, markTone: v.tone,
      markAt: done ? 1 : seg(P, 0.66, 0.82),
    });
  } else {
    // No curve stored — an angle logged by hand rather than snapshotted. The number line
    // carries the same argument from the two numbers every result has.
    faded(ctx, done ? 1 : seg(P, 0.62, 0.78), () => {
      drawNumberLine(ctx, { line, value, direction, tone: v.tone,
                            x: 72, y: below + 160, w: STORY_W - 144,
                            progress: done ? 1 : seg(P, 0.64, 0.9) });
    });
  }

  faded(ctx, done ? 1 : seg(P, 0.86, 1), () => {
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
    ctx.fillText("corner-model", STORY_W / 2, ctaY + 168);
    ctx.textAlign = "left";
  });

  return canvas;
};

// ----------------------------- The same result, landscape -----------------------------
//
// WHY A SECOND LAYOUT RATHER THAN A CROP. A Story is 9:16 and X's timeline is 16:9. Posting
// the portrait file to X pillarboxes it: the video plays as a narrow strip down the middle
// with two black columns either side, and the number that is the entire point ends up about
// a third of the height it was designed for. Cropping is worse — the count and the curve are
// at opposite ends of a tall image, so any 16:9 window loses one of them.
//
// So the elements are re-composed rather than re-scaled: the argument goes down the left,
// the evidence sits on the right, and both are full size.
export const WIDE_W = 1920;
export const WIDE_H = 1080;

export const renderResultWide = (canvas, {
  homeName = "", awayName = "", leagueId = "", kickoff = "",
  team = "", line = 0, direction = "over", subject = "team",
  value = 0, result = "win", prob = null, dist = [],
  homeGoals = null, awayGoals = null, homeCorners = null, awayCorners = null,
  cornerMinutes = [],
  slip = null,
  cta = "The full record on the site", brand = "CORNER MODEL",
  progress = 1,
} = {}) => {
  const P = clamp01(progress);
  const done = P >= 1;
  canvas.width = WIDE_W;
  canvas.height = WIDE_H;
  const ctx = canvas.getContext("2d");
  const v = resultVerdict(result) || resultVerdict("win");

  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, WIDE_W, WIDE_H);
  const glow = ctx.createRadialGradient(340, 400, 60, 340, 400, 900);
  glow.addColorStop(0, `${v.tone}26`);
  glow.addColorStop(1, `${v.tone}00`);
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, WIDE_W, WIDE_H);

  ctx.textBaseline = "middle";
  const useFlags = flagsRender(ctx);
  const L = 90;                  // left column
  const R = 900;                 // right column starts here

  faded(ctx, done ? 1 : seg(P, 0, 0.07), () => {
    ctx.fillStyle = C.primary;
    ctx.font = `700 26px ${FONT_HEAD}`;
    ctx.letterSpacing = "6px";
    ctx.fillText(brand, L, 110);
    ctx.letterSpacing = "0px";

    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, homeName, { size: 56, max: R - L - 80, family: FONT_HEAD });
    ctx.fillText(homeName, L, 186);
    ctx.fillStyle = C.muted;
    ctx.font = `500 28px ${FONT_BODY}`;
    ctx.fillText("v", L, 242);
    ctx.fillStyle = C.text;
    ctx.font = fitFont(ctx, awayName, { size: 56, max: R - L - 120, family: FONT_HEAD });
    ctx.fillText(awayName, L + 40, 242);

    const flag = useFlags ? flagFor(leagueId) : null;
    const where = [flag || countryCodeFor(leagueId), kickoff].filter(Boolean).join("  ·  ");
    if (where) {
      ctx.fillStyle = C.muted;
      ctx.font = `500 26px ${FONT_BODY}`;
      ctx.fillText(where, L, 300);
    }
  });

  faded(ctx, done ? 1 : seg(P, 0.05, 0.14), () => {
    ctx.font = `700 30px ${FONT_HEAD}`;
    ctx.letterSpacing = "3px";
    const w = ctx.measureText(v.word).width + 52;
    ctx.fillStyle = `${v.tone}22`;
    roundRect(ctx, L, 348, w, 60, 30);
    ctx.fill();
    ctx.strokeStyle = `${v.tone}88`;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = v.tone;
    ctx.fillText(v.word, L + 26, 380);
    ctx.letterSpacing = "0px";
  });

  const climb = done ? 1 : seg(P, 0.10, 0.62);
  faded(ctx, done ? 1 : seg(P, 0.08, 0.16), () => {
    ctx.fillStyle = v.tone;
    ctx.font = `700 200px ${FONT_DATA}`;
    ctx.fillText(String(Math.round(value * climb)), L, 550);
    ctx.fillStyle = C.text;
    ctx.font = `600 38px ${FONT_HEAD}`;
    ctx.fillText(subject === "match" ? "corners in the match" : `corners for ${team}`, L, 672);
  });

  faded(ctx, done ? 1 : seg(P, 0.62, 0.74), () => {
    const called = direction === "under" ? `under ${line}` : `${line}+`;
    ctx.fillStyle = C.muted;
    ctx.font = `500 30px ${FONT_BODY}`;
    ctx.fillText(prob != null ? `We called ${called} at ${Math.round(prob)}%` : `We called ${called}`,
                 L, 730);
    const margin = resultMargin(value, line, direction);
    if (margin) {
      ctx.fillStyle = v.tone;
      ctx.font = `700 36px ${FONT_HEAD}`;
      ctx.fillText(margin, L, 782);
    }
    let sy = 848;
    const pair = (label, a, b) => {
      ctx.fillStyle = C.muted;
      ctx.font = `500 24px ${FONT_BODY}`;
      ctx.fillText(label, L, sy);
      ctx.fillStyle = C.text;
      ctx.font = `700 36px ${FONT_DATA}`;
      ctx.fillText(`${a} - ${b}`, L + 180, sy);
      sy += 54;
    };
    if (homeGoals != null && awayGoals != null) pair("Final score", homeGoals, awayGoals);
    if (homeCorners != null && awayCorners != null) pair("Corners", homeCorners, awayCorners);
  });

  // The evidence column. Same order of preference as the portrait story.
  const rw = WIDE_W - R - 90;
  if (cornerMinutes?.length) {
    faded(ctx, done ? 1 : seg(P, 0.30, 0.42), () => {
      drawCornerTimeline(ctx, { minutes: cornerMinutes, line, tone: v.tone,
                                x: R, y: 540, w: rw,
                                progress: done ? 1 : seg(P, 0.32, 0.86) });
    });
  } else if (dist?.length) {
    drawCurve(ctx, dist, line, {
      x: R, y: 300, w: rw, h: slip ? 380 : 460,
      progress: done ? 1 : clamp01((P - 0.16) / 0.5),
      mark: value, markTone: v.tone,
      markAt: done ? 1 : seg(P, 0.66, 0.82),
    });
  } else {
    faded(ctx, done ? 1 : seg(P, 0.62, 0.78), () => {
      drawNumberLine(ctx, { line, value, direction, tone: v.tone, x: R, y: 540, w: rw,
                            progress: done ? 1 : seg(P, 0.64, 0.9) });
    });
  }

  if (slip) {
    drawSlip(ctx, { ...slip, tone: v.tone, x: R, y: 780, w: rw,
                    progress: done ? 1 : seg(P, 0.78, 0.92) });
  }

  faded(ctx, done ? 1 : seg(P, 0.86, 1), () => {
    const w = 560;
    const x = WIDE_W - 90 - w;
    ctx.fillStyle = C.primary;
    roundRect(ctx, x, WIDE_H - 160, w, 92, 46);
    ctx.fill();
    ctx.fillStyle = "#00181C";
    ctx.font = `700 32px ${FONT_HEAD}`;
    ctx.textAlign = "center";
    ctx.fillText(cta, x + w / 2, WIDE_H - 114);
    ctx.textAlign = "left";
  });

  return canvas;
};
