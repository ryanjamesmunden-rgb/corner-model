/**
 * The failure this file exists to prevent is silent and total: a share that opens X's
 * composer with the Post button greyed out. It looks like the feature works right up to
 * the moment someone tries to use it, so what's pinned here is the counting X actually
 * does — flags at 2, not at 1 and not at 14 — and that fitToPost never hands back
 * something over the limit while a shorter build was available.
 */
import { weightedLength, xWeight, fitsInAPost, fitToPost, URL_WEIGHT, X_MAX_WEIGHT } from "./xLimit";

const NORWAY = "\u{1F1F3}\u{1F1F4}";
const ENGLAND = "\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}";

describe("counting the way X counts", () => {
  test("plain latin text is one per character", () => {
    expect(weightedLength("Liverpool")).toBe(9);
    expect(weightedLength("")).toBe(0);
  });

  test("a flag costs 2 — not 1, and not its JS length", () => {
    expect(weightedLength(NORWAY)).toBe(2);
    expect(NORWAY.length).toBe(4);
  });

  test("a tag-sequence flag also costs 2, though it is 14 UTF-16 units", () => {
    // The home nations are the case that breaks a naive .length check hardest.
    expect(weightedLength(ENGLAND)).toBe(2);
    expect(ENGLAND.length).toBe(14);
  });

  test("the punctuation the boards actually use stays cheap", () => {
    // Kept at 1 by twitter-text's light ranges — an em dash, a middot, a lambda.
    expect(weightedLength("—")).toBe(1);
    expect(weightedLength("·")).toBe(1);
    expect(weightedLength("λ")).toBe(1);
  });
});

describe("whether it fits", () => {
  test("the link is charged at a flat rate however long the URL", () => {
    const body = "x".repeat(X_MAX_WEIGHT - URL_WEIGHT - 1);
    expect(fitsInAPost(body)).toBe(true);
    expect(fitsInAPost(body + "x")).toBe(false);
  });

  test("with nothing still to append there is room for the whole limit", () => {
    // `url` was renamed `appendUrl`: it is about whether a link is STILL TO BE ADDED, not
    // about whether one exists. The old name read as the latter, which is how a post that
    // ends on its own address came to be charged for two of them.
    expect(fitsInAPost("x".repeat(X_MAX_WEIGHT), { appendUrl: false })).toBe(true);
    expect(fitsInAPost("x".repeat(X_MAX_WEIGHT + 1), { appendUrl: false })).toBe(false);
  });

  test("a post that carries its own link is not charged twice for it", () => {
    // THE BUG THIS FIXES. The link is in the text, so it costs 23 once. Charged as
    // characters AND reserved for again, this text cost ~27 more than X says — and the
    // figure shown beside the draft could not be checked against X's own counter.
    const body = "x".repeat(200);
    const post = `${body}\n\nthecornermodel.com/streaks`;
    expect(xWeight(post)).toBe(200 + 2 + URL_WEIGHT);
    expect(fitsInAPost(post, { appendUrl: false })).toBe(true);
  });
});

// WHAT X WILL SAY IT COSTS, which is not the same question as what the characters weigh.
//
// FOUND BY BEING ASKED. The number printed beside a draft — "142/280" — was a few over what
// X counts, because the address at the end was weighed character by character (26) instead of
// charged X's flat t.co rate (23). Both errors ran the safe way, so nothing was posted too
// long, but the figure is read by a person deciding whether they have room to edit, and it
// has to match the counter in X's composer.
describe("what X will actually charge", () => {
  test("a link costs the flat t.co rate, not its length", () => {
    expect(xWeight("https://example.com/a/very/long/path/that/goes/on/and/on")).toBe(URL_WEIGHT);
    expect(xWeight("thecornermodel.com/streaks")).toBe(URL_WEIGHT);
  });

  test("a link SHORTER than a t.co still costs the flat rate", () => {
    // X swaps it either way, so there is no saving to be had and max() would be wrong.
    expect(xWeight("ab.co")).toBe(URL_WEIGHT);
  });

  test("text around a link is weighed normally", () => {
    expect(xWeight("hello thecornermodel.com/streaks")).toBe(
      weightedLength("hello ") + URL_WEIGHT);
  });

  test("two links cost two flat rates", () => {
    expect(xWeight("a.com b.com")).toBe(URL_WEIGHT + 1 + URL_WEIGHT);
  });

  test("no link means it agrees with the character weight", () => {
    for (const s of ["", "plain text", `${NORWAY} a flag`, "4+ corners in 5"]) {
      expect(xWeight(s)).toBe(weightedLength(s));
    }
  });

  test("something that is not a link is not discounted", () => {
    // A miss must never UNDER-count, or a post goes out over the limit. A bare word with a
    // dot in it and no known TLD is text.
    expect(xWeight("e.g")).toBe(weightedLength("e.g"));
    expect(xWeight("4.5")).toBe(weightedLength("4.5"));
    expect(xWeight("Operario-PR")).toBe(weightedLength("Operario-PR"));
  });

  test("a decimal beside a real link does not swallow it", () => {
    expect(xWeight("over 9.5 at thecornermodel.com/streaks"))
      .toBe(weightedLength("over 9.5 at ") + URL_WEIGHT);
  });
});

describe("trimming to fit", () => {
  // Stands in for a board: each row is deliberately too fat to fit many of.
  const build = (n) => Array.from({ length: n }, (_, i) => `${NORWAY} row ${i} ${"x".repeat(50)}`).join("\n");

  test("returns the most rows that fit, not the most asked for", () => {
    const out = fitToPost(build, 8);
    expect(fitsInAPost(out)).toBe(true);
    expect(out.split("\n").length).toBeLessThan(8);
  });

  test("keeps everything when everything fits", () => {
    expect(fitToPost(() => "short", 4)).toBe("short");
  });

  test("hands back one row rather than nothing when even that is too long", () => {
    // An empty composer reads as a broken button; an over-long row is editable, and
    // X shows the overrun in its own counter.
    const huge = () => "y".repeat(400);
    expect(fitToPost(huge, 4)).toBe("y".repeat(400));
  });

  test("an empty board stays empty rather than looping to a row that isn't there", () => {
    expect(fitToPost(() => "", 4)).toBe("");
  });
});
