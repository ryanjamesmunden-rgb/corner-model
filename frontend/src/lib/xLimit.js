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

/**
 * The most rows an X share will carry. A CEILING, not a promise: four rows of streaks
 * measure ~313 against the 280 limit once the flags are counted at 2 apiece, so
 * fitToPost drops rows from here until the post actually fits. Four is where it starts
 * because that is roughly what fits on a good day — short club names, a 24-hour clock —
 * and asking for more only ever means throwing more away.
 *
 * Lives here rather than in ShareButtons so the scheduled draft job, which cannot
 * import a React component, uses the same number the buttons do.
 */
export const X_SHARE_ROWS = 4;
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

// A LINK INSIDE THE TEXT COSTS 23, NOT ITS OWN LENGTH, and counting it character by
// character is what made the number shown beside a draft wrong.
//
// X replaces every link with a t.co of fixed length before counting, so
// "thecornermodel.com/streaks" — 26 characters — costs 23. weightedLength does not know
// that: it is a pure character weigher, and it charged 26. Every draft that ends on its own
// link therefore reported a few characters more than X would, and the fitting was
// conservative by a whole URL on top of that, because fitsInAPost ALSO added URL_WEIGHT to a
// text that already contained the address.
//
// Both errors ran the same way — over-counting — so nothing was ever posted too long. But
// the figure printed next to a post is read by a person deciding whether they have room to
// edit it, and "142/280" for a post X counts as 138 is a number that cannot be checked
// against X's own composer. So the two jobs are now separate: weightedLength weighs
// characters, xWeight answers "what will X say this costs".
//
// IT NEVER UNDER-COUNTS. A link the pattern fails to recognise is weighed as ordinary text,
// which for any address long enough to matter is more than 23 — so a miss keeps a post
// inside the limit rather than pushing it over.
const URL_RE = /\bhttps?:\/\/\S+|\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:com|net|org|io|co|uk|ai|app|dev|me|tv|gg)\b(?:\/\S*)?/gi;

/**
 * What X will actually count for a finished post, links included.
 *
 * Use this for anything shown to a person or compared against X_MAX_WEIGHT. Use
 * weightedLength only when you specifically want the character weight of text with no
 * links in it.
 */
export const xWeight = (text) => {
  const s = String(text || "");
  let total = 0;
  let last = 0;
  URL_RE.lastIndex = 0;
  for (let m = URL_RE.exec(s); m; m = URL_RE.exec(s)) {
    total += weightedLength(s.slice(last, m.index));
    // A link the pattern found but which is SHORTER than a t.co still costs 23: X swaps it
    // for one either way, so the max is wrong here and the flat charge is right.
    total += URL_WEIGHT;
    last = m.index + m[0].length;
  }
  return total + weightedLength(s.slice(last));
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

/**
 * Does this fit in one post?
 *
 * `appendUrl` is about whether a link is still to be ADDED — the share buttons and the X
 * draft hand the composer a body and let the intent's `&url=` put the address underneath,
 * so those bodies have to leave room for it. A post that already ends on its own link
 * passes false, and xWeight charges the link it can see. Getting this backwards double-
 * counts an address and drops a sentence that would have fitted.
 */
export const fitsInAPost = (text, { appendUrl = true } = {}) =>
  xWeight(text) + (appendUrl ? URL_WEIGHT + 1 : 0) <= X_MAX_WEIGHT;

/**
 * The longest version of a board that fits in one post: `build(n)` is called with
 * `maxRows` first and then fewer, down to one row.
 *
 * Returns the one-row build when even that is too long rather than "" — a share button
 * that opens an empty composer looks broken, and a single over-long row is still
 * something the user can edit. Being over the limit is visible in X's own composer;
 * silently sharing nothing is not.
 */
export const fitToPost = (build, maxRows, opts = {}) => {
  let last = "";
  for (let n = maxRows; n >= 1; n--) {
    last = build(n) || "";
    if (!last || fitsInAPost(last, opts)) return last;
  }
  return last;
};
