import {
  MAX_LINE, MIN_GAMES, MIN_LINE, MIN_RATE, claimLine, direction, hasMismatch, headline, mismatches,
  sharedLine,
} from "./mismatch";

/** A game row as the fixture endpoint's `recent` emits it. */
const g = (won, conceded) => ({
  won, conceded, total: won + conceded, shots_for: 14,
  date: "2026-09-01T15:00:00Z", opponent: "X", home: true,
});

/** n games where this side wins `won` and concedes `conceded` every time. */
const flat = (n, won, conceded) => Array.from({ length: n }, () => g(won, conceded));

describe("the shared line", () => {
  test("is the highest line both sides clear", () => {
    // Attack wins 6 every game, defence ships 6 every game.
    expect(sharedLine([6, 6, 7, 6, 6], [6, 7, 6, 8, 6])).toBe(6);
  });

  test("it walks DOWN, so the strongest shared claim wins", () => {
    // Climbing up would stop at 3+ and report that where 5+ is also true of both.
    expect(sharedLine([5, 6, 7, 5, 5], [5, 5, 9, 6, 5])).toBe(5);
  });

  test("it is limited by whichever side is weaker", () => {
    // The attack clears 8 every game; the defence only ever ships 4.
    expect(sharedLine([8, 9, 8, 8, 8], [4, 4, 5, 4, 4])).toBe(4);
  });

  test("one bad game inside the rate does not break it", () => {
    // 4 of 5 is exactly MIN_RATE.
    expect(MIN_RATE).toBe(0.8);
    expect(sharedLine([5, 5, 5, 5, 1], [5, 5, 5, 5, 1])).toBe(5);
  });

  test("two bad games do", () => {
    expect(sharedLine([5, 5, 5, 1, 1], [5, 5, 5, 5, 5])).toBeNull();
  });

  test("a line below the floor is not a claim at all", () => {
    // FOUND BY A TEST, NOT BY DESIGN. Two quiet sides pair at "2+" — both halves 5 of 5,
    // both perfectly true, and every team in the league wins 2+ corners most weeks. The
    // streak board already refuses those via OVER_LINE_FLOOR; so does this.
    expect(MIN_LINE).toBe(3);
    expect(sharedLine([2, 2, 2, 2, 2], [2, 2, 2, 2, 2])).toBeNull();
  });

  test("it is capped, because a line nobody prices is not an angle", () => {
    const huge = [20, 20, 20, 20, 20];
    expect(sharedLine(huge, huge)).toBe(MAX_LINE);
  });

  test("no games on either side is no line", () => {
    expect(sharedLine([], [5, 5])).toBeNull();
    expect(sharedLine([5, 5], [])).toBeNull();
  });
});

describe("one direction", () => {
  test("pairs the attack's won record with the defence's conceded record", () => {
    const m = direction(flat(5, 6, 3), flat(5, 2, 6), "Arsenal", "Brighton");
    expect(m).toMatchObject({ attacker: "Arsenal", defender: "Brighton", line: 6 });
    expect(m.attack).toMatchObject({ hits: 5, n: 5 });
    expect(m.defence).toMatchObject({ hits: 5, n: 5 });
  });

  test("it reads the DEFENDER's conceded column, not their attack", () => {
    // The trap: Brighton win 2 and concede 6. Reading their `won` would find nothing and
    // the section would never render on the fixture it exists for.
    const m = direction(flat(5, 6, 3), flat(5, 2, 6), "Arsenal", "Brighton");
    expect(m.defenceValues).toEqual([6, 6, 6, 6, 6]);
  });

  test("a solid defence is not a mismatch at all", () => {
    // The defence never ships more than 1, so there is no shared line above the floor —
    // and "1+" would be a claim about nothing.
    expect(direction(flat(5, 7, 3), flat(5, 6, 1), "Arsenal", "Solid")).toBeNull();
  });

  test("too few games is no claim rather than a thin one", () => {
    expect(MIN_GAMES).toBe(4);
    expect(direction(flat(3, 7, 3), flat(3, 2, 7), "A", "B")).toBeNull();
    expect(direction(flat(5, 7, 3), flat(3, 2, 7), "A", "B")).toBeNull();
  });

  test("a side with no line in common produces nothing", () => {
    // Attack never clears anything; there is no honest pairing.
    expect(direction(flat(5, 0, 3), flat(5, 2, 7), "A", "B")).toBeNull();
  });

  test("an uncovered game is dropped rather than counted as zero", () => {
    const games = [...flat(4, 6, 3), { won: null, conceded: null }];
    const m = direction(games, flat(5, 2, 6), "A", "B");
    expect(m.attack.n).toBe(4);
  });
});

describe("both directions", () => {
  test("the away side attacking a leaky home defence is found too", () => {
    // Home are quiet and leaky; away are sharp. A home-biased read misses this entirely.
    const rows = mismatches(flat(5, 2, 7), flat(5, 7, 2), "Home", "Away");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ attacker: "Away", defender: "Home", line: 7 });
  });

  test("a game where both sides attack and both leak gives both directions", () => {
    const rows = mismatches(flat(5, 6, 6), flat(5, 6, 6), "Home", "Away");
    expect(rows).toHaveLength(2);
  });

  test("the stronger shared line is listed first", () => {
    // Home attack 7 into a defence shipping 7; away attack 5 into one shipping 5.
    const rows = mismatches(flat(6, 7, 5), flat(6, 5, 7), "Home", "Away");
    expect(rows[0].line).toBeGreaterThanOrEqual(rows[1]?.line ?? 0);
  });

  test("most fixtures are not a mismatch", () => {
    // Two solid sides conceding 2 a game. A section that rendered on every fixture would
    // mean nothing when it rendered on the right one.
    expect(mismatches(flat(5, 4, 2), flat(5, 4, 2), "A", "B")).toEqual([]);
    expect(mismatches([], [], "A", "B")).toEqual([]);
    expect(hasMismatch([])).toBe(false);
  });
});

describe("the words", () => {
  test("the claim names one line and both halves of it", () => {
    // ONE number, not two. Quoting each side at its own best line reads stronger and means
    // less, because the halves stop being about the same bet.
    const m = direction(flat(5, 6, 3), [...flat(4, 2, 6), g(2, 1)], "Arsenal", "Brighton");
    expect(claimLine(m)).toBe(
      "Arsenal won 6+ in 5 of 5 · Brighton conceded 6+ in 4 of 5");
  });

  test("the headline says 'every game' only when it was every game", () => {
    const perfect = direction(flat(5, 6, 3), flat(5, 2, 6), "Arsenal", "Brighton");
    expect(headline(perfect)).toBe(
      "Arsenal 6+ every game, Brighton conceding 6+ every game");
  });

  test("and hedges when it was not", () => {
    const m = direction(flat(5, 6, 3), [...flat(4, 2, 6), g(2, 1)], "Arsenal", "Brighton");
    expect(headline(m)).toBe("Arsenal 6+ against a defence shipping 6+");
  });

  test("nothing in is an empty string, not 'undefined won undefined+'", () => {
    expect(claimLine(null)).toBe("");
    expect(headline(null)).toBe("");
  });
});
