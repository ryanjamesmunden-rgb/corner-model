import { flattenGames, byDay, dayIsOpen, OPEN_DAYS } from "./browseOrder";

const game = (id, day, time, extra = {}) =>
  ({ fixture_id: id, day, date: `${day}T${time}:00+00:00`, home: `H${id}`, away: `A${id}`,
     ...extra });

const tree = [
  { country: "England",
    leagues: [
      { league_id: "eng-pl", name: "Premier League", is_cup: false,
        games: [game("a", "2026-10-11", "14:00"), game("b", "2026-10-10", "19:45")] },
      { league_id: "eng-fa", name: "FA Cup", is_cup: true,
        games: [game("c", "2026-10-11", "12:30")] },
    ] },
  { country: "Norway",
    leagues: [
      { league_id: "nor-el", name: "Eliteserien", is_cup: false,
        games: [game("d", "2026-10-11", "16:00")] },
    ] },
];

describe("flattening the tree", () => {
  it("returns every game in it", () => {
    expect(flattenGames(tree).map((g) => g.fixture_id).sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("gives each game the country it came from", () => {
    const by = Object.fromEntries(flattenGames(tree).map((g) => [g.fixture_id, g.country]));
    expect(by).toEqual({ a: "England", b: "England", c: "England", d: "Norway" });
  });

  it("and the competition, because time order has no header to inherit from", () => {
    // "Reading v Bradford" means something different in the Championship from what it
    // means in a cup, and a flat list has nothing above it saying which.
    const c = flattenGames(tree).find((g) => g.fixture_id === "c");
    expect(c.league_name).toBe("FA Cup");
    expect(c.is_cup).toBe(true);
  });

  it("carries the LEAGUE ID, which is what the flag is derived from", () => {
    // Not the country name: countryFlag.js is keyed on the id because ids carry a stable
    // three-letter prefix while names collide across borders.
    expect(flattenGames(tree).find((g) => g.fixture_id === "d").league_id).toBe("nor-el");
  });

  it("survives a payload with nothing in it", () => {
    expect(flattenGames()).toEqual([]);
    expect(flattenGames([{ country: "X" }])).toEqual([]);
    expect(flattenGames([{ country: "X", leagues: [{ league_id: "y" }] }])).toEqual([]);
  });
});

describe("grouping by day", () => {
  it("puts each game under the day it is played", () => {
    const days = byDay(flattenGames(tree));
    expect(days.map((d) => d.day)).toEqual(["2026-10-10", "2026-10-11"]);
    expect(days[0].games.map((g) => g.fixture_id)).toEqual(["b"]);
  });

  it("orders the days earliest first", () => {
    const days = byDay([game("x", "2026-12-01", "15:00"), game("y", "2026-01-05", "15:00")]);
    expect(days.map((d) => d.day)).toEqual(["2026-01-05", "2026-12-01"]);
  });

  it("orders games inside a day by kick-off", () => {
    const sunday = byDay(flattenGames(tree)).find((d) => d.day === "2026-10-11");
    expect(sunday.games.map((g) => g.fixture_id)).toEqual(["c", "a", "d"]);
  });

  it("mixes countries inside a day, which is the whole point of the order", () => {
    const sunday = byDay(flattenGames(tree)).find((d) => d.day === "2026-10-11");
    expect(new Set(sunday.games.map((g) => g.country))).toEqual(new Set(["England", "Norway"]));
  });

  it("groups on `day`, NOT on the timestamp", () => {
    // The server computed `day` in London. A 20:00 kick-off in Brazil is 23:00 UTC the
    // same day and a 01:30 one is the NEXT day in UTC, so grouping on the timestamp here
    // would scatter half the South American card into a day the reader is not in.
    const late = { fixture_id: "br", day: "2026-10-11", date: "2026-10-12T01:30:00+00:00" };
    expect(byDay([late])[0].day).toBe("2026-10-11");
  });

  it("drops a game with no day rather than inventing a group for it", () => {
    expect(byDay([{ fixture_id: "z" }])).toEqual([]);
  });

  it("survives nothing at all", () => {
    expect(byDay()).toEqual([]);
  });
});

describe("which day sections start open", () => {
  it("opens the first OPEN_DAYS and closes the rest", () => {
    expect(dayIsOpen({}, "2026-10-10", 0)).toBe(true);
    expect(dayIsOpen({}, "2026-10-11", OPEN_DAYS - 1)).toBe(true);
    expect(dayIsOpen({}, "2026-10-12", OPEN_DAYS)).toBe(false);
  });

  it("a click beats the position, both ways", () => {
    expect(dayIsOpen({ "2026-10-10": false }, "2026-10-10", 0)).toBe(false);
    expect(dayIsOpen({ "2026-10-20": true }, "2026-10-20", 9)).toBe(true);
  });

  it("is derived, so a different list is defaulted afresh", () => {
    // The state is keyed on the DAY, not the index, so yesterday's clicks do not land on
    // whatever now happens to sit in that position after a window or filter change.
    const clicked = { "2026-10-10": false };
    expect(dayIsOpen(clicked, "2026-11-30", 0)).toBe(true);
  });

  it("survives no state at all", () => {
    expect(dayIsOpen(undefined, "2026-10-10", 0)).toBe(true);
  });
});
