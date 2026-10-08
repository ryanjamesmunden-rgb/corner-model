/**
 * Which team each number belongs to.
 *
 * Everything else in this file is scaffolding around one test: that the attacking side's
 * shots are paired with the DEFENDING side's shots conceded, and not with its own. That
 * mistake produces a panel that looks completely normal and is wrong on every fixture,
 * which is exactly why the pairing was pulled out of the component and put behind these.
 *
 * Every fixture below uses numbers that are distinct across all four slots, so a swap
 * cannot pass by coincidence.
 */
import { matchupRows, fixtureMatchup, hasMatchup, THIN_COVER } from "./shotMatchup.js";

const feats = (over = {}) => ({
  played: 10,
  covered: { shots: 10, shots_on_target: 10, blocked_shots: 10 },
  shots_for: 20.1, shots_against: 9.3,
  shots_on_target_for: 7.2, shots_on_target_against: 3.4,
  blocked_shots_for: 4.8, blocked_shots_against: 2.6,
  ...over,
});

// Deliberately nothing like the home side's, so a crossed wire is obvious.
const AWAY = feats({
  shots_for: 11.5, shots_against: 18.9,
  shots_on_target_for: 4.1, shots_on_target_against: 6.4,
  blocked_shots_for: 2.2, blocked_shots_against: 5.7,
});

describe("one direction", () => {
  test("takes is the attack's own, allows is the OPPONENT's conceded", () => {
    const [shots] = matchupRows(feats(), AWAY);
    expect(shots.takes).toBe(20.1);     // home shots_for
    expect(shots.allows).toBe(18.9);    // away shots_AGAINST
    // The two numbers it must never reach for.
    expect(shots.allows).not.toBe(9.3);     // the attack's own conceded
    expect(shots.allows).not.toBe(11.5);    // the defence's own shots taken
  });

  test("every column pairs the same way round", () => {
    const rows = matchupRows(feats(), AWAY);
    expect(rows.map((r) => [r.takes, r.allows])).toEqual([
      [20.1, 18.9], [7.2, 6.4], [4.8, 5.7],
    ]);
  });

  test("a missing half is not a pairing", () => {
    const [shots] = matchupRows(feats({ shots_for: null }), AWAY);
    expect(shots.paired).toBe(false);
    // The number that IS there is still carried — the panel can show one and say the
    // other is missing, which is better than drawing nothing.
    expect(shots.allows).toBe(18.9);
  });

  test("nulls do not become zeros", () => {
    const [shots] = matchupRows(feats({ shots_for: null }), feats({ shots_against: null }));
    expect(shots.takes).toBeNull();
    expect(shots.allows).toBeNull();
  });

  test("coverage rides on the row, from both sides", () => {
    const [shots] = matchupRows(
      feats({ covered: { shots: 3 } }), feats({ covered: { shots: 11 } }));
    expect(shots.takesCover).toBe(3);
    expect(shots.allowsCover).toBe(11);
    // The WEAKER half decides: a pairing is only as good as its thinner side.
    expect(shots.thin).toBe(true);
  });

  test("and a well covered pairing is not flagged", () => {
    const c = { shots: THIN_COVER, shots_on_target: THIN_COVER, blocked_shots: THIN_COVER };
    expect(matchupRows(feats({ covered: c }), feats({ covered: c }))[0].thin).toBe(false);
  });

  test("no features at all is no rows, rather than a row of dashes", () => {
    expect(matchupRows(null, null)).toEqual([]);
  });
});

describe("both directions of a fixture", () => {
  const fx = {
    home: { features: { home: feats(),
                        overall: feats({ shots_for: 15.0, shots_against: 7.7 }) } },
    away: { features: { away: AWAY,
                        overall: feats({ shots_for: 13.3, shots_against: 12.0 }) } },
    homeName: "NAC Breda", awayName: "MVV",
  };

  test("the home block is the home attack against the away defence", () => {
    const [h] = fixtureMatchup(fx);
    expect(h.team).toBe("NAC Breda");
    expect(h.opponent).toBe("MVV");
    expect(h.rows[0].takes).toBe(20.1);
    expect(h.rows[0].allows).toBe(18.9);
  });

  test("and the away block is the mirror of it, not a copy", () => {
    const [, a] = fixtureMatchup(fx);
    expect(a.team).toBe("MVV");
    expect(a.rows[0].takes).toBe(11.5);    // away's own shots
    expect(a.rows[0].allows).toBe(9.3);    // home's conceded
  });

  test("venue by default: home team's home games, away team's away games", () => {
    // Reading the wrong split is the other invisible failure — it produces plausible
    // numbers from the wrong pool.
    expect(fixtureMatchup(fx)[0].rows[0].takes).toBe(20.1);
  });

  test("overall moves BOTH sides, never one", () => {
    // One team's home form against the other's whole season is a comparison of two
    // different things.
    const [h, a] = fixtureMatchup({ ...fx, overall: true });
    expect(h.rows[0].takes).toBe(15.0);     // home overall, for
    expect(h.rows[0].allows).toBe(12.0);    // AWAY overall, against
    expect(a.rows[0].takes).toBe(13.3);     // away overall, for
    expect(a.rows[0].allows).toBe(7.7);     // HOME overall, against
  });

  test("hasMatchup is false when nothing pairs", () => {
    expect(hasMatchup(fixtureMatchup(fx))).toBe(true);
    expect(hasMatchup(fixtureMatchup({ homeName: "A", awayName: "B" }))).toBe(false);
  });
});
