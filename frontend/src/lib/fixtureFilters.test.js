/**
 * The failure these guard against is not a crash — it is a filter that quietly returns
 * nothing, which on a fixture board is indistinguishable from a quiet night. Almost all of
 * that risk lives in one place: deciding which SIDE an angle belongs to, by comparing a
 * team name from one collection against a fixture name from another.
 */
import { sideOf, anglesOn, applyFilter, filterByKey, FILTERS } from "./fixtureFilters";

const angle = (team, kind = "over_team", strong = true) => ({ team, kind, strong });
const fx = (home, away, angles = []) =>
  ({ fixture_id: `${home}-${away}`, home, away, angles });

describe("which side an angle belongs to", () => {
  const game = fx("Club Brugge KV", "Antwerp");

  test("matches the obvious way round", () => {
    expect(sideOf(angle("Club Brugge KV"), game)).toBe("home");
    expect(sideOf(angle("Antwerp"), game)).toBe("away");
  });

  test("survives the two collections spelling a club differently", () => {
    // A fixture may carry "Bodø/Glimt" where the team row says "Bodo Glimt". An exact
    // comparison files that angle under neither side, and the filter then reports no
    // games — which reads as "nothing on tonight", not as a bug.
    const nor = fx("Bodø/Glimt", "Rosenborg");
    expect(sideOf(angle("Bodo Glimt"), nor)).toBe("home");
    expect(sideOf(angle("Rosenborg BK"), nor)).toBe("away");
  });

  test("refuses to guess rather than putting an angle on the wrong team", () => {
    // Unattributed is recoverable; wrong is not. A misfiled angle makes a row PASS a
    // filter it should have failed, which is the one outcome worse than hiding it.
    expect(sideOf(angle("Someone Else"), game)).toBeNull();
    expect(sideOf(angle(""), game)).toBeNull();
    expect(sideOf(angle("United"), fx("Leeds United", "Newcastle United"))).toBeNull();
  });
});

describe("the filters", () => {
  const homeRun = fx("Brugge", "Antwerp", [angle("Brugge")]);
  const awayRun = fx("Genk", "Gent", [angle("Gent")]);
  const bothRun = fx("Viking", "Brann", [angle("Viking"), angle("Brann")]);
  const mismatch = fx("Molde", "Bodo", [angle("Molde", "mismatch")]);
  const chase = fx("Start", "Sarpsborg", [angle("Start", "chase")]);
  const all = [homeRun, awayRun, bothRun, mismatch, chase];

  const keep = (key) => all.filter((f) => filterByKey(key).test(f)).map((f) => f.home);

  test("home and away are told apart", () => {
    expect(keep("home_streak")).toEqual(["Brugge", "Viking"]);
    expect(keep("away_streak")).toEqual(["Genk", "Viking"]);
  });

  test("both teams means both, not either", () => {
    expect(keep("both_sides")).toEqual(["Viking"]);
  });

  test("mismatch and chase are their own kinds, not streaks", () => {
    expect(keep("mismatch")).toEqual(["Molde"]);
    expect(keep("chase")).toEqual(["Start"]);
    // A mismatch is not a run, so it must not answer a streak filter.
    expect(keep("home_streak")).not.toContain("Molde");
  });

  test("an under run is not what anyone means by a streak filter", () => {
    // It IS a streak. Including it would mean "Home streak" returning games where the
    // home side keeps going UNDER — the opposite of what the filter is picked for.
    const under = fx("Defensive", "Team", [angle("Defensive", "under_team")]);
    expect(filterByKey("home_streak").test(under)).toBe(false);
  });

  test("a weak angle does not pass", () => {
    // The board already uses "strong" as the bar for being listed. A filter counting weak
    // angles would be looser than the thing it filters.
    const weak = fx("Nearly", "There", [angle("Nearly", "over_team", false)]);
    expect(filterByKey("home_streak").test(weak)).toBe(false);
  });

  test("All keeps everything, and an unknown key falls back to it", () => {
    expect(keep("all")).toHaveLength(5);
    expect(filterByKey("nonsense").key).toBe("all");
  });

  test("every filter is selectable and has a hint", () => {
    for (const f of FILTERS) {
      expect(typeof f.test).toBe("function");
      expect(f.hint.length).toBeGreaterThan(10);
    }
  });
});

describe("applying it to the board", () => {
  const board = {
    days: [
      { day: "2026-09-12", scanned: 9,
        fixtures: [fx("Brugge", "Antwerp", [angle("Brugge")]), fx("A", "B", [angle("B")])] },
      { day: "2026-09-13", scanned: 4, fixtures: [fx("C", "D", [angle("D")])] },
    ],
  };

  test("a day that empties out is KEPT, not dropped", () => {
    // The board's own rule: an absent day reads as missing data, "nothing here" is an
    // answer. Filtering must not turn one into the other.
    const out = applyFilter(board, "home_streak");
    expect(out.days).toHaveLength(2);
    expect(out.days[1].fixtures).toHaveLength(0);
    expect(out.days[1].day).toBe("2026-09-13");
  });

  test("counts what it hid, so the UI can say so", () => {
    const out = applyFilter(board, "home_streak");
    expect(out.matched).toBe(1);
    expect(out.before_filter).toBe(3);
    expect(out.days[0].before_filter).toBe(2);
  });

  test("All changes nothing about what is shown", () => {
    const out = applyFilter(board, "all");
    expect(out.matched).toBe(3);
    expect(out.matched).toBe(out.before_filter);
  });

  test("an empty or missing board does not throw", () => {
    expect(applyFilter(null, "home_streak").matched).toBe(0);
    expect(applyFilter({ days: [] }, "both_sides").days).toEqual([]);
  });
});
