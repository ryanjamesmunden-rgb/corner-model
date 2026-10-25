import { boardLine, boardLines, hasRecord } from "./boardBreakdown.js";

const board = (over = {}) => ({
  key: "mismatch", label: "Quick scan", blurb: "this attack against THIS defence",
  claims: 80, frozen_rows: 310, snapshots: 4,
  settled: 40, landed: 26, missed: 14, voided: 0, pending: 40,
  hit_rate: 65.0, lo: 49.5, hi: 78.1, mean_prob: 63.8, residual: 1.2,
  ...over,
});

describe("a rate refuses to exist without settled games", () => {
  it("shows no rate when nothing has been played", () => {
    const r = boardLine(board({ settled: 0, landed: 0, missed: 0, hit_rate: null,
                                lo: null, hi: null }));
    expect(r.rate).toBeNull();
    expect(r.claims).toBe(80);
  });

  it("never turns an unsettled board into 0%", () => {
    // 0% would read as "everything missed", which is a different and worse claim.
    const r = boardLine(board({ settled: 0, hit_rate: 0 }));
    expect(r.rate).toBeNull();
  });

  it("shows the rate once something settles", () => {
    expect(boardLine(board()).rate).toBe(65.0);
  });
});

describe("the interval is printed whole or not at all", () => {
  it("carries both ends together", () => {
    expect(boardLine(board()).interval).toEqual({ lo: 49.5, hi: 78.1 });
  });

  it("drops the interval when only one end came back", () => {
    expect(boardLine(board({ hi: null })).interval).toBeNull();
    expect(boardLine(board({ lo: null })).interval).toBeNull();
  });

  it("has no interval before anything settles", () => {
    expect(boardLine(board({ settled: 0 })).interval).toBeNull();
  });
});

describe("the residual is the result, and it needs a stated price", () => {
  it("reads a positive residual as beating its own claim", () => {
    const r = boardLine(board({ residual: 1.2 }));
    expect(r.verdict).toBe("beat");
  });

  it("reads a negative residual as falling short, however high the hit rate", () => {
    // Perfect games: 73.1% landed against a stated 82.3%. A good-looking rate and a
    // losing board, which is the whole reason the residual is shown beside it.
    const r = boardLine(board({ hit_rate: 73.1, mean_prob: 82.3, residual: -9.2 }));
    expect(r.rate).toBe(73.1);
    expect(r.verdict).toBe("short");
  });

  it("distinguishes level from absent", () => {
    expect(boardLine(board({ residual: 0 })).verdict).toBe("level");
    expect(boardLine(board({ residual: null, mean_prob: null })).verdict).toBeNull();
  });

  it("does not infer a residual from the hit rate alone", () => {
    const r = boardLine(board({ residual: null, mean_prob: null }));
    expect(r.residual).toBeNull();
    expect(r.rate).toBe(65.0);
  });
});

describe("the repeats line appears only when there were repeats", () => {
  it("reports the gap between frozen rows and claims", () => {
    // These boards freeze every morning over a seven-day horizon, so the same fixture
    // is written down repeatedly. Counting rows instead of claims multiplies the
    // denominator several times over.
    expect(boardLine(board()).repeats)
      .toEqual({ frozen: 310, claims: 80, snapshots: 4 });
  });

  it("stays absent when every frozen row was its own claim", () => {
    expect(boardLine(board({ frozen_rows: 80, claims: 80 })).repeats).toBeNull();
  });

  it("stays absent rather than negative if the numbers disagree", () => {
    expect(boardLine(board({ frozen_rows: 40, claims: 80 })).repeats).toBeNull();
  });
});

describe("a board with nothing frozen is not a board with a bad record", () => {
  it("drops it entirely", () => {
    expect(boardLine(board({ claims: 0 }))).toBeNull();
    expect(hasRecord({ claims: 0 })).toBe(false);
  });

  it("survives junk without throwing", () => {
    expect(boardLine(null)).toBeNull();
    expect(boardLine({})).toBeNull();
    expect(boardLines(null)).toEqual([]);
    expect(boardLines(undefined)).toEqual([]);
  });

  it("keeps the boards that do have a record and drops the rest", () => {
    const rows = boardLines([
      board({ key: "streaks", claims: 120 }),
      board({ key: "perfect", claims: 0 }),
      board({ key: "mismatch", claims: 80 }),
    ]);
    expect(rows.map((r) => r.key)).toEqual(["streaks", "mismatch"]);
  });
});

describe("it keeps the label and the reasoning the board rests on", () => {
  it("carries both through", () => {
    const r = boardLine(board());
    expect(r.label).toBe("Quick scan");
    expect(r.blurb).toContain("THIS defence");
  });

  it("falls back to the key rather than rendering nothing", () => {
    expect(boardLine(board({ label: null })).label).toBe("mismatch");
  });
});
