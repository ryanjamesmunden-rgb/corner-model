/**
 * The failure this file exists to prevent is silent and total: a share that opens X's
 * composer with the Post button greyed out. It looks like the feature works right up to
 * the moment someone tries to use it, so what's pinned here is the counting X actually
 * does — flags at 2, not at 1 and not at 14 — and that fitToPost never hands back
 * something over the limit while a shorter build was available.
 */
import { weightedLength, fitsInAPost, fitToPost, URL_WEIGHT, X_MAX_WEIGHT } from "./xLimit";

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

  test("without a link there is room for the whole limit", () => {
    expect(fitsInAPost("x".repeat(X_MAX_WEIGHT), { url: false })).toBe(true);
    expect(fitsInAPost("x".repeat(X_MAX_WEIGHT + 1), { url: false })).toBe(false);
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
