import { defaultLine, formView, rankTeams } from "./teamForm";

// Oldest first, as /favourites/teams sends it.
const g = (won, home = true, over = {}) => ({
  date: "2026-09-01", opponent: "X", home, won, conceded: 4, total: won + 4, ...over,
});

describe("form graph slicing", () => {
  test("last N keeps the newest games, oldest first", () => {
    const form = [1, 2, 3, 4, 5, 6, 7].map((w) => g(w));
    const v = formView(form, { window: 5 });
    expect(v.games.map((x) => x.won)).toEqual([3, 4, 5, 6, 7]);
    expect(v.avg).toBe(5);
  });

  test("venue filters BEFORE the window: last 5 home is five home games", () => {
    const form = [];
    for (let i = 0; i < 10; i += 1) form.push(g(i, i % 2 === 0));
    const v = formView(form, { venue: "home", window: 5 });
    expect(v.n).toBe(5);
    expect(v.games.every((x) => x.home)).toBe(true);
    expect(formView(form, { venue: "away", window: 3 }).games.map((x) => x.won)).toEqual([5, 7, 9]);
  });

  test("metric switches what is averaged", () => {
    const form = [g(6), g(4)];
    expect(formView(form, { metric: "won" }).avg).toBe(5);
    expect(formView(form, { metric: "conceded" }).avg).toBe(4);
    expect(formView(form, { metric: "total" }).avg).toBe(9);
  });

  test("a missing value is left out, not counted as zero", () => {
    const form = [g(6, true, { conceded: null, total: null }), g(4)];
    const v = formView(form, { metric: "conceded" });
    expect(v.avg).toBe(4);
    expect(v.n).toBe(2);
  });

  test("hits and the live run at a line", () => {
    const form = [7, 6, 3, 6, 5].map((w) => g(w));
    const v = formView(form, { line: 5 });
    expect(v.hits).toBe(4);
    expect(v.run).toBe(2);
  });

  test("a gap ends the run", () => {
    const form = [g(6), g(6, true, { total: null }), g(9)];
    expect(formView(form, { metric: "total", line: 5 }).run).toBe(1);
  });

  test("nothing on file is an empty graph, not a crash", () => {
    const v = formView(undefined, { line: 5 });
    expect(v.n).toBe(0);
    expect(v.avg).toBeNull();
    expect(v.hits).toBeNull();
  });

  test("default line is the average rounded down, at least 1", () => {
    expect(defaultLine(5.8)).toBe(5);
    expect(defaultLine(0.4)).toBe(1);
    expect(defaultLine(null)).toBeNull();
  });
});

describe("ranking followed teams on Saved", () => {
  const team = (id, wons, next = "2026-11-20", homes = null) => ({
    team_id: id,
    form: wons.map((w, i) => g(w, homes ? homes[i] : true)),
    fixtures: next ? [{ date: next }] : [],
  });

  test("kick-off sort puts the soonest game first and no fixture last", () => {
    const out = rankTeams([team("a", [5], "2026-11-22"), team("b", [5], null), team("c", [5], "2026-11-15")]);
    expect(out.map((t) => t.team_id)).toEqual(["c", "a", "b"]);
  });

  test("last 5 ranks on the newest five only", () => {
    // a: old games huge, recent five poor. b: steady 6s.
    const a = team("a", [12, 12, 12, 2, 2, 2, 2, 2]);
    const b = team("b", [6, 6, 6, 6, 6, 6, 6, 6]);
    expect(rankTeams([a, b], { sort: 5 }).map((t) => t.team_id)).toEqual(["b", "a"]);
    expect(rankTeams([a, b], { sort: 20 }).map((t) => t.team_id)).toEqual(["b", "a"]);
  });

  test("a thin sample cannot top the list", () => {
    const one = team("one", [11]);
    const five = team("five", [7, 7, 7, 7, 7]);
    expect(rankTeams([one, five], { sort: 5 }).map((t) => t.team_id)).toEqual(["five", "one"]);
  });

  test("venue filter applies before ranking", () => {
    const a = team("a", [9, 1, 9, 1, 9, 1], "2026-11-20", [true, false, true, false, true, false]);
    const b = team("b", [5, 5, 5, 5, 5, 5], "2026-11-20", [true, false, true, false, true, false]);
    expect(rankTeams([a, b], { sort: 5, venue: "home" }).map((t) => t.team_id)).toEqual(["a", "b"]);
    expect(rankTeams([a, b], { sort: 5, venue: "away" }).map((t) => t.team_id)).toEqual(["b", "a"]);
  });

  test("does not mutate the list it was given", () => {
    const list = [team("a", [1, 1, 1]), team("b", [9, 9, 9])];
    rankTeams(list, { sort: 5 });
    expect(list.map((t) => t.team_id)).toEqual(["a", "b"]);
  });
});
