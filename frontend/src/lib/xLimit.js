// Whether a share actually fits in one X post.
//
// A row cap alone doesn't settle it, which is the whole reason this file exists. X does
// not count characters the way JavaScript does: it uses twitter-text's WEIGHTED length,
// where ordinary Latin text and punctuation cost 1 per grapheme but everything else —
// every flag on every row — costs 2. A `🏴󠁧󠁢󠁥󠁮󠁧󠁿` is `.length` 14 in JS, 1 grapheme on screen,
// and 2 to X. Counting any of those three as the others gets the answer wrong.
//
// So four rows of streaks measured ~313 against the 280 limit: over, and X disables the
// Post button rather than truncating, which means a "capped" share that still has to be
// hand-edited before it can go out — the exact thing the cap was meant to remove.
//
// The fix is to treat the row cap as a CEILING and drop rows until the post fits, rather
// than to pick a number and hope. Row counts are rebuilt, never truncated, so the
// "+N more on the site" tail stays true to the list above it at whatever size survives.

// twitter-text v3 weights every grapheme 2 except these code point ranges, which are 1.
const LIGHT_RANGES = [[0, 4351], [8192, 8205], [8208, 8223], [8242, 8247]];

/** X replaces every link with a t.co of fixed length, so a URL is a flat cost. */
export const URL_WEIGHT = 23;
export const X_MAX_WEIGHT = 280;

const segmenter = typeof Intl !== "undefined" && Intl.Segmenter
  ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
  : null;

const graphemes = (text) => {
  if (segmenter) return [...segmenter.segment(text)].map((s) => s.segment);
  // Older browsers have no Segmenter. Array spread splits on code points rather than
  // graphemes, which OVER-counts a multi-codepoint flag — it errs toward posting one
  // row fewer, never toward a post X refuses.
  return [...text];
};

/** What X will say this text costs, before any link is added. */
export const weightedLength = (text) => {
  let total = 0;
  for (const g of graphemes(text || "")) {
    const points = [...g];
    const cp = points[0] ? points[0].codePointAt(0) : 0;
    const light = points.length === 1 && LIGHT_RANGES.some(([lo, hi]) => cp >= lo && cp <= hi);
    total += light ? 1 : 2;
  }
  return total;
};

/** Does this body still fit once X appends the link (and the space before it)? */
export const fitsInAPost = (text, { url = true } = {}) =>
  weightedLength(text) + (url ? URL_WEIGHT + 1 : 0) <= X_MAX_WEIGHT;

/**
 * The longest version of a board that fits in one post: `build(n)` is called with
 * `maxRows` first and then fewer, down to one row.
 *
 * Returns the one-row build when even that is too long rather than "" — a share button
 * that opens an empty composer looks broken, and a single over-long row is still
 * something the user can edit. Being over the limit is visible in X's own composer;
 * silently sharing nothing is not.
 */
export const fitToPost = (build, maxRows) => {
  let last = "";
  for (let n = maxRows; n >= 1; n--) {
    last = build(n) || "";
    if (!last || fitsInAPost(last)) return last;
  }
  return last;
};
