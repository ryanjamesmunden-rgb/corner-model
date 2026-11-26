import { chaseRead, lastGames, ordinal, splitAverage, stateRows, tableGap } from "./fixtureContext";

const game = (gf, ga, won, conceded, shots) => ({ gf, ga, won, conceded, shots_for: shots });

describe("lastGames", () => {
  it("takes the newest five and averages them", () => {
    const recent = [game(2, 0, 7, 3, 15), game(1, 1, 5, 5, 12), game(0, 1, 2, 8, 8),
                    game(3, 1, 9, 2, 20), game(1, 2, 4, 6, 10), game(5, 0, 12, 1, 30)];
    const s = lastGames(recent);
    expect(s.played).toBe(5);
    expect([s.wins, s.draws, s.losses]).toEqual([2, 1, 2]);
    expect(s.won).toBeCloseTo(5.4);
    expect(s.gf).toBeCloseTo(1.4);
    expect(s.shotGames).toBe(5);
  });

  it("does not read a missing score as a draw", () => {
    const s = lastGames([game(null, null, 4, 4, null)]);
    expect(s.draws).toBe(0);
    expect(s.results).toEqual([null]);
    expect(s.shotGames).toBe(0);
  });
});

const split = {
  ht: {
    trailing: { games: 6, won: 7.0, conceded: 3.0 },
    level: { games: 8, won: 5.0, conceded: 4.0 },
    leading: { games: 6, won: 3.0, conceded: 6.0 },
  },
};

describe("state rows and the chase read", () => {
  it("weights the baseline by games", () => {
    expect(splitAverage(split)).toBeCloseTo((42 + 40 + 18) / 20);
  });

  it("calls a side that wins more when behind a chaser", () => {
    expect(chaseRead(split).verdict).toBe("chases");
  });

  it("calls a side that wins fewer when behind one that sits", () => {
    const sits = { ht: { ...split.ht, trailing: { games: 6, won: 2.0 } } };
    expect(chaseRead(sits).verdict).toBe("sits");
  });

  it("says nothing off a thin trailing bucket", () => {
    const thin = { ht: { ...split.ht, trailing: { games: 2, won: 9.0 } } };
    expect(chaseRead(thin)).toBeNull();
    expect(stateRows(thin)[0].thin).toBe(true);
  });
});

describe("tableGap", () => {
  it("names the higher side and flags a big gap", () => {
    const g = tableGap({ position: 18 }, { position: 4 }, "Bolton", "West Brom");
    expect(g.text).toBe("West Brom sit 14 places above Bolton");
    expect(g.big).toBe(true);
  });

  it("is silent when a side is unplaced", () => {
    expect(tableGap(null, { position: 1 }, "A", "B")).toBeNull();
  });
});

it("ordinals", () => {
  expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal))
    .toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]);
});
