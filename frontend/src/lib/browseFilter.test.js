import { matchesQuery, filterTree, totalOf, leagueChips, emptyReason, dayChips }
  from "./browseFilter";

const game = (home, away, extra = {}) =>
  ({ fixture_id: `${home}-${away}`, home, away, date: "2026-10-11T15:00:00+00:00",
     day: "2026-10-11", ...extra });

const tree = () => ([
  { country: "England", count: 4, leagues: [
    { league_id: "eng-pl", name: "Premier League", is_cup: false, count: 2,
      games: [game("Arsenal", "Everton"), game("Manchester United", "Chelsea")] },
    { league_id: "eng-ch", name: "Championship", is_cup: false, count: 2,
      games: [game("Cardiff", "Derby"), game("Hull", "Stoke")] },
  ] },
  { country: "Germany", count: 1, leagues: [
    { league_id: "ger-b2", name: "2. Bundesliga", is_cup: false, count: 1,
      games: [game("Energie Cottbus", "Hannover 96")] },
  ] },
]);

const names = (cs) => cs.flatMap((c) => c.leagues.flatMap(
  (l) => l.games.map((g) => `${g.home} v ${g.away}`)));


describe("matching what was typed", () => {
  const c = tree()[0];
  const l = c.leagues[0];
  const g = l.games[0];

  it("finds a team by part of its name", () => {
    expect(matchesQuery(g, l, c, "arse")).toBe(true);
    expect(matchesQuery(g, l, c, "ever")).toBe(true);
  });

  it("ignores case", () => {
    expect(matchesQuery(g, l, c, "ARSENAL")).toBe(true);
  });

  it("finds by league or country too", () => {
    expect(matchesQuery(g, l, c, "premier")).toBe(true);
    expect(matchesQuery(g, l, c, "england")).toBe(true);
  });

  it("takes every word, in any order", () => {
    // A single substring test fails both of these, and a search that fails looks
    // exactly like a site with no data in it.
    expect(matchesQuery(g, l, c, "arsenal everton")).toBe(true);
    expect(matchesQuery(g, l, c, "everton arsenal")).toBe(true);
    expect(matchesQuery(g, l, c, "arsenal premier")).toBe(true);
  });

  it("requires ALL the words, not any of them", () => {
    expect(matchesQuery(g, l, c, "arsenal liverpool")).toBe(false);
  });

  it("an empty query matches everything", () => {
    expect(matchesQuery(g, l, c, "")).toBe(true);
    expect(matchesQuery(g, l, c, "   ")).toBe(true);
    expect(matchesQuery(g, l, c, undefined)).toBe(true);
  });
});


describe("narrowing the tree", () => {
  it("with nothing on, it is the tree unchanged", () => {
    const t = tree();
    expect(filterTree(t, {})).toBe(t);
    expect(filterTree(t, { q: "", league: "" })).toBe(t);
  });

  it("a query keeps only the games that match", () => {
    expect(names(filterTree(tree(), { q: "cardiff" })))
      .toEqual(["Cardiff v Derby"]);
  });

  it("a league badge keeps only that competition", () => {
    expect(names(filterTree(tree(), { league: "ger-b2" })))
      .toEqual(["Energie Cottbus v Hannover 96"]);
  });

  it("the two compose", () => {
    expect(filterTree(tree(), { q: "cardiff", league: "eng-pl" })).toEqual([]);
    expect(names(filterTree(tree(), { q: "cardiff", league: "eng-ch" })))
      .toEqual(["Cardiff v Derby"]);
  });

  it("does not mutate what it was given", () => {
    const t = tree();
    filterTree(t, { q: "cardiff" });
    expect(names(t)).toHaveLength(5);
    expect(t[0].count).toBe(4);
  });
});


describe("the counts follow the filter", () => {
  // The rule the endpoint already keeps and a client-side filter is likeliest to break,
  // because hiding rows is so much easier than re-counting them.
  const check = (cs) => {
    cs.forEach((c) => {
      expect(c.count).toBe(c.leagues.reduce((a, l) => a + l.count, 0));
      c.leagues.forEach((l) => expect(l.count).toBe(l.games.length));
    });
    expect(totalOf(cs)).toBe(cs.reduce((a, c) => a + c.count, 0));
  };

  it("after a query", () => {
    const cs = filterTree(tree(), { q: "a" });
    check(cs);
  });

  it("after a league badge", () => {
    check(filterTree(tree(), { league: "eng-ch" }));
  });

  it("after both", () => {
    check(filterTree(tree(), { q: "hull", league: "eng-ch" }));
  });

  it("the total agrees with the rows actually rendered", () => {
    const cs = filterTree(tree(), { q: "a" });
    expect(totalOf(cs)).toBe(names(cs).length);
  });
});


describe("empty branches are dropped while filtering", () => {
  // The OPPOSITE of the endpoint's rule, deliberately. The endpoint keeps an empty
  // league because the tree is a stable thing you are scrolling and a vanishing row
  // moves what you were about to tap. A result list is not that.
  it("a league with no match goes", () => {
    const cs = filterTree(tree(), { q: "cardiff" });
    expect(cs[0].leagues.map((l) => l.league_id)).toEqual(["eng-ch"]);
  });

  it("and so does a country with nothing left in it", () => {
    expect(filterTree(tree(), { q: "cardiff" }).map((c) => c.country))
      .toEqual(["England"]);
  });

  it("nothing matching at all is an empty list, not a tree of zeros", () => {
    expect(filterTree(tree(), { q: "zzzzz" })).toEqual([]);
    expect(totalOf(filterTree(tree(), { q: "zzzzz" }))).toBe(0);
  });
});


describe("the badge row", () => {
  it("has one chip per competition with something on", () => {
    expect(leagueChips(tree()).map((x) => x.league_id).sort())
      .toEqual(["eng-ch", "eng-pl", "ger-b2"]);
  });

  it("is ordered by how much is on", () => {
    // The row scrolls sideways and most of it is off screen, so the first few chips
    // are the whole design.
    const chips = leagueChips(tree());
    expect(chips.map((x) => x.count)).toEqual([2, 2, 1]);
  });

  it("carries the country, so a flag can be derived", () => {
    const ger = leagueChips(tree()).find((x) => x.league_id === "ger-b2");
    expect(ger.country).toBe("Germany");
    expect(ger.name).toBe("2. Bundesliga");
  });

  it("drops a league with nothing on rather than showing a zero chip", () => {
    const t = tree();
    t[0].leagues.push({ league_id: "eng-fa", name: "FA Cup", count: 0, games: [] });
    expect(leagueChips(t).map((x) => x.league_id)).not.toContain("eng-fa");
  });

  it("counts come from the tree it is given, so a search re-counts them", () => {
    // A chip reading 12 beside a list of two is the same lie as a league header
    // doing it.
    const chips = leagueChips(filterTree(tree(), { q: "cardiff" }));
    expect(chips).toEqual([expect.objectContaining({ league_id: "eng-ch", count: 1 })]);
  });

  it("survives an empty payload", () => {
    expect(leagueChips()).toEqual([]);
    expect(leagueChips([{ country: "X" }])).toEqual([]);
  });
});


describe("saying why the page is empty", () => {
  // An empty page is ambiguous between "no such team", "nothing on in that league" and
  // "the site is broken", and only the first two are true here.
  it("names the term", () => {
    expect(emptyReason({ q: "cardif" })).toContain('"cardif"');
  });

  it("names the league", () => {
    expect(emptyReason({ league: "eng-ch", leagueName: "Championship" }))
      .toContain("Championship");
  });

  it("names both when both are on, since either could be the cause", () => {
    const msg = emptyReason({ q: "cardif", league: "eng-pl",
                              leagueName: "Premier League" });
    expect(msg).toContain('"cardif"');
    expect(msg).toContain("Premier League");
  });

  it("says nothing when no filter is on — that empty page has another cause", () => {
    expect(emptyReason({})).toBe("");
  });
});


describe("the day chips count what is actually showing", () => {
  const server = [{ day: "2026-10-11", count: 5 }, { day: "2026-10-12", count: 6 }];

  it("with no filter on, the server's calendar is used unchanged", () => {
    // It is built before the DAY filter on purpose, so the chips keep saying what else
    // is on. Nothing here should disturb that.
    expect(dayChips(tree(), server, { filtering: false })).toBe(server);
  });

  it("with a search on, they are recounted from what survived", () => {
    // Otherwise a chip offers "5" beside a list of one, and tapping it produces one —
    // because the query survives the day change.
    const cs = filterTree(tree(), { q: "cardiff" });
    expect(dayChips(cs, server, { filtering: true }))
      .toEqual([{ day: "2026-10-11", count: 1 }]);
  });

  it("a day with nothing left does not get a zero chip", () => {
    const cs = filterTree(tree(), { q: "cardiff" });
    expect(dayChips(cs, server, { filtering: true }).map((c) => c.day))
      .not.toContain("2026-10-12");
  });

  it("with a day already picked the counts are dropped, not guessed", () => {
    // The tree holds only that day, so there is nothing to count the others from. A
    // chip with no count beats a chip with a false one.
    const got = dayChips(filterTree(tree(), { q: "cardiff" }), server,
                         { filtering: true, day: "2026-10-11" });
    expect(got).toEqual([{ day: "2026-10-11", count: null },
                         { day: "2026-10-12", count: null }]);
  });

  it("survives an empty payload", () => {
    expect(dayChips([], [], { filtering: true })).toEqual([]);
    expect(dayChips()).toEqual([]);
  });
});
