import { PAGE_SIZE, SERIES_COLOURS, chartRows, pages, sliceGames, teamSummary } from "./formLines";

const g = (won, date, over = {}) => ({
  date, opponent: `Opp${won}`, home: true, won, conceded: 4, total: won + 4, ...over,
});
const team = (id, wons, over = {}) => ({
  team_id: id, name: id, form: wons.map((w, i) => g(w, `2026-09-${String(i + 1).padStart(2, "0")}`)), ...over,
});

describe("pages and colours", () => {
  test("never more than ten lines on a page", () => {
    const ts = Array.from({ length: 23 }, (_, i) => team(`t${i}`, [5]));
    const p = pages(ts);
    expect(p.map((x) => x.length)).toEqual([10, 10, 3]);
    expect(PAGE_SIZE).toBe(10);
    expect(new Set(SERIES_COLOURS).size).toBe(10);
  });
});

describe("chart rows", () => {
  test("right-aligned on the latest game: a shorter record starts later", () => {
    const rows = chartRows([team("a", [1, 2, 3, 4]), team("b", [7, 8])]);
    expect(rows.map((r) => r.ago)).toEqual([4, 3, 2, 1]);
    expect(rows.map((r) => r.a)).toEqual([1, 2, 3, 4]);
    expect(rows.map((r) => r.b)).toEqual([undefined, undefined, 7, 8]);
    expect(rows[3].b__g.opponent).toBe("Opp8");
  });

  test("diff mode plots each game against the team's own average", () => {
    const rows = chartRows([team("a", [4, 6, 8])], { mode: "diff" });
    expect(rows.map((r) => r.a)).toEqual([-2, 0, 2]);
  });

  test("window and venue apply per team, venue first", () => {
    const t = { team_id: "a", form: [g(1, "d1"), g(2, "d2", { home: false }), g(3, "d3"), g(4, "d4", { home: false })] };
    expect(chartRows([t], { venue: "away" }).map((r) => r.a)).toEqual([2, 4]);
    expect(chartRows([t], { window: 2 }).map((r) => r.a)).toEqual([3, 4]);
    expect(sliceGames(t.form, "home", 1).map((x) => x.won)).toEqual([3]);
  });

  test("a missing value is a gap, not a zero", () => {
    const t = { team_id: "a", form: [g(5, "d1"), g(6, "d2", { total: null })] };
    const rows = chartRows([t], { metric: "total" });
    expect(rows[1].a).toBeUndefined();
  });

  test("no teams is no rows", () => {
    expect(chartRows([])).toEqual([]);
    expect(chartRows(undefined)).toEqual([]);
  });
});

describe("team summary", () => {
  test("best and worst game against its own average, with the opponent", () => {
    const s = teamSummary(team("a", [3, 9, 6]));
    expect(s.avg).toBe(6);
    expect(s.best.opponent).toBe("Opp9");
    expect(s.best.diff).toBe(3);
    expect(s.worst.opponent).toBe("Opp3");
    expect(s.over).toBe(1);
    expect(s.under).toBe(1);
  });

  test("tracked teams get before / since tracking", () => {
    const s = teamSummary(team("a", [2, 4, 8, 10], { tracked_at: "2026-09-03T12:00:00Z" }));
    expect(s.since.games).toBe(2);
    expect(s.since.avg).toBe(9);
    expect(s.since.before_avg).toBe(3);
  });

  test("untracked teams have no since block", () => {
    expect(teamSummary(team("a", [5])).since).toBeNull();
  });
});
