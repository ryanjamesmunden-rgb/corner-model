// Which four destinations reach the phone's tab bar.
//
// The bar has five slots and the site has up to nine destinations, so something is always
// left out — and what gets left out changes with who is looking: Projected and Results are
// absent signed out, Prices unless you are a member. The failure worth testing for is a bar
// with a hole in it, or one whose contents shuffle as somebody signs in.

import { splitNav } from "./mobileNav.js";

const icon = () => null;
const item = (to, label) => ({ to, label, icon });

const SIGNED_OUT = [
  item("/scanner", "Value Finder"), item("/quick-scan", "Quick Scan"),
  item("/dashboard", "Leagues"), item("/streaks", "Streaks"),
  item("/saved", "Saved"), item("/bets", "Bets"),
];
const SIGNED_IN = [
  item("/scanner", "Value Finder"), item("/quick-scan", "Quick Scan"),
  item("/dashboard", "Leagues"), item("/streaks", "Streaks"),
  item("/projections", "Projected"), item("/saved", "Saved"),
  item("/bets", "Bets"), item("/results", "Results"),
];
const MEMBER = [...SIGNED_IN, item("/prices", "Prices")];

const paths = (rows) => rows.map((r) => r.to);

describe("what reaches the bar", () => {
  test("the four daily screens, for a signed-in reader", () => {
    // Stated rather than taken from list order: the nav is ordered for the desktop row,
    // where everything fits and the ordering means something else.
    expect(paths(splitNav(SIGNED_IN).bar))
      .toEqual(["/scanner", "/quick-scan", "/streaks", "/projections"]);
  });

  test("and the rest go to More, in nav order", () => {
    expect(paths(splitNav(SIGNED_IN).rest))
      .toEqual(["/dashboard", "/saved", "/bets", "/results"]);
  });

  test("a member's extra screen lands in More rather than displacing a daily one", () => {
    const { bar, rest } = splitNav(MEMBER);
    expect(paths(bar)).toEqual(["/scanner", "/quick-scan", "/streaks", "/projections"]);
    expect(paths(rest)).toContain("/prices");
  });
});

describe("when a primary destination is not there at all", () => {
  test("the bar is topped up rather than left with a gap", () => {
    // Signed out there is no /projections. A four-slot bar showing three and a space
    // reads as broken, not as personalised.
    const { bar } = splitNav(SIGNED_OUT);
    expect(bar).toHaveLength(4);
    expect(paths(bar)).toEqual(["/scanner", "/quick-scan", "/streaks", "/dashboard"]);
  });

  test("nothing is lost between the two", () => {
    // Every destination is reachable from one place or the other. A route that appears in
    // neither is unreachable on a phone, and nothing would say so.
    for (const nav of [SIGNED_OUT, SIGNED_IN, MEMBER]) {
      const { bar, rest } = splitNav(nav);
      expect([...paths(bar), ...paths(rest)].sort()).toEqual(paths(nav).sort());
    }
  });

  test("and nothing is in both", () => {
    for (const nav of [SIGNED_OUT, SIGNED_IN, MEMBER]) {
      const { bar, rest } = splitNav(nav);
      expect(paths(bar).filter((p) => paths(rest).includes(p))).toEqual([]);
    }
  });
});

describe("edges", () => {
  test("a nav shorter than the bar does not invent slots", () => {
    const { bar, rest } = splitNav([item("/scanner", "Value Finder")]);
    expect(paths(bar)).toEqual(["/scanner"]);
    expect(rest).toEqual([]);
  });

  test("an empty nav is empty rather than a crash", () => {
    expect(splitNav([])).toEqual({ bar: [], rest: [] });
  });
});
