import { gameStateBadge, gameStateReasons, GAME_STATE } from "./gameState";

const row = (gs) => ({ fixture_id: "f1", game_state: gs });

describe("the badge", () => {
  test("a chase spot, a parker and an avoid each get one", () => {
    for (const v of ["chase_spot", "caution", "avoid"]) {
      const b = gameStateBadge(row({ verdict: v, reasons: [] }));
      expect(b.verdict).toBe(v);
      expect(b.label).toBe(GAME_STATE[v].label);
    }
  });

  test("neutral gets none — marking the normal case marks every row", () => {
    expect(gameStateBadge(row({ verdict: "neutral", reasons: [] }))).toBeNull();
  });

  test("a total line, and a server from before the label, get none", () => {
    expect(gameStateBadge(row(null))).toBeNull();
    expect(gameStateBadge({ fixture_id: "f1" })).toBeNull();
  });
});

describe("the reasons", () => {
  test("capped so a phone is not mostly caveats", () => {
    const r = row({ verdict: "avoid", reasons: ["a", "b", "c"] });
    expect(gameStateReasons(r)).toEqual(["a", "b"]);
  });

  test("nothing to say is an empty list, not a crash", () => {
    expect(gameStateReasons(row(null))).toEqual([]);
    expect(gameStateReasons(row({ verdict: "neutral" }))).toEqual([]);
  });
});
