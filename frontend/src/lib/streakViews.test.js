// The Streaks page's landing tab.
//
// WHAT THIS GUARDS. Hot form was the landing tab and read as confusing: it shows a
// DIFFERENCE between a recent average and a season baseline, with no corner line attached,
// so the first thing the page showed was the thing furthest from a bet. Consistency counts
// games clearing a specific line, which names a market a reader can go and price.
//
// It is one word in a useState call. A later edit flips it back, nothing fails, and nobody
// notices until the page is confusing again — which is precisely why it is asserted.
import {
  DEFAULT_STREAK_VIEW, STREAK_VIEWS, streakViewLabel,
} from "./streakViews.js";

describe("what the page opens on", () => {
  test("consistency, not hot form", () => {
    expect(DEFAULT_STREAK_VIEW).toBe("consistency");
  });

  test("consistency is first and hot form second", () => {
    expect(STREAK_VIEWS.map((v) => v.id)).toEqual(["consistency", "form"]);
  });

  test("the default is the first tab rather than a second statement of it", () => {
    // Restating the default separately is how an order and a default come to disagree,
    // which shows up as a page opening on a tab that is not the one highlighted.
    expect(DEFAULT_STREAK_VIEW).toBe(STREAK_VIEWS[0].id);
  });

  test("hot form is still there", () => {
    // Moved, not removed. It is the earlier signal — a run has to start somewhere.
    expect(STREAK_VIEWS.map((v) => v.id)).toContain("form");
  });

  test("every tab has a label", () => {
    for (const v of STREAK_VIEWS) {
      expect(v.label).toBeTruthy();
    }
  });
});

describe("the error boundary knows which view broke", () => {
  test("it names the view rather than the page", () => {
    expect(streakViewLabel("form")).toBe("Hot form");
    expect(streakViewLabel("consistency")).toBe("The streak finder");
  });
});
