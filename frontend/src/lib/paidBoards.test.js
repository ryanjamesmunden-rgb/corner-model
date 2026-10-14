import { PAID_BOARDS, isPaidBoard, showsLock } from "./paidBoards";

// THE REGRESSION THIS FILE EXISTS FOR. The padlock list lived in Scanner.jsx and went
// four entries out of date for a week: the server stopped trimming the non-member boards
// on 7 Oct and the locks stayed on, so the site advertised a paywall it no longer had.
// Nothing failed, because the API was the half that was right.

describe("only genuinely gated boards carry a padlock", () => {
  it("the value board does — it is the one route with require_member", () => {
    expect(isPaidBoard("value")).toBe(true);
  });

  it("and the four that are served in full do NOT", () => {
    // Each of these returns every row, unblurred, to a signed-out visitor. A lock on
    // them is the site telling a stranger not to bother with something it is giving away.
    ["form", "streaks", "perfect", "chase"].forEach((tab) => {
      expect(isPaidBoard(tab)).toBe(false);
    });
  });

  it("nor does the tab the page opens on", () => {
    expect(isPaidBoard("best")).toBe(false);
  });

  it("exactly one board is paid", () => {
    // Pinned as a COUNT as well as by name: adding a lock is then a deliberate act that
    // breaks a test and makes someone state which server gate they are reflecting.
    expect(Object.keys(PAID_BOARDS)).toEqual(["value"]);
  });

  it("an unknown tab is not silently treated as paid", () => {
    expect(isPaidBoard("something-new")).toBe(false);
    expect(isPaidBoard(undefined)).toBe(false);
  });
});


describe("who sees the lock", () => {
  it("a signed-out visitor, on the paid board only", () => {
    expect(showsLock("value", false)).toBe(true);
    expect(showsLock("streaks", false)).toBe(false);
  });

  it("a free account is not a member, so it still sees it", () => {
    // Signing in with a different Google account does not change this, which is exactly
    // what it looked like when the stale list was still in place.
    expect(showsLock("value", undefined)).toBe(true);
  });

  it("a member sees no lock anywhere, including on what they paid for", () => {
    // A padlock on something you own reads as the site failing to recognise you.
    ["value", "streaks", "best"].forEach((tab) => {
      expect(showsLock(tab, true)).toBe(false);
    });
  });
});
