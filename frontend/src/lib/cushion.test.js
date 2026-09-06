/**
 * A sign error here recommends the flimsiest runs on the board while claiming they are
 * the safest, so what is pinned is the asymmetry between the two directions:
 *
 *   - an OVER clears at exactly the line (4 corners wins "4+"), so margin 0 is a win;
 *   - an UNDER voids at exactly the line, so its smallest possible win is margin 1;
 *   - a MISS is never a small cushion — folding losses in as negative margins would let
 *     a broken run pass a "never close" filter by averaging out.
 */
import { legMargin, winMargins, tightestWin, lastMargin, comfortFilter } from "./cushion";

const leg = (value, result) => ({ value, result, opponent: "x", home: true, date: "" });

describe("one leg's margin", () => {
  test("an over clears by whatever it beat the line by, and 0 still counts", () => {
    expect(legMargin(7, 4, "over")).toBe(3);
    expect(legMargin(4, 4, "over")).toBe(0);      // exactly on the line WINS an over
  });

  test("an under counts down from the line", () => {
    expect(legMargin(8, 10, "under")).toBe(2);
    expect(legMargin(9, 10, "under")).toBe(1);    // the tightest win an under can have
  });
});

describe("across a run", () => {
  const solid = { line: 4, direction: "over", recent: [leg(9, "win"), leg(6, "win"), leg(7, "win")] };
  const scrapes = { line: 4, direction: "over", recent: [leg(4, "win"), leg(4, "win"), leg(5, "win")] };

  test("tells a comfortable 3/3 from a scraped one", () => {
    // 9, 6, 7 against a line of 4 are margins of 5, 2 and 3 — the run is only ever as
    // safe as its tightest leg, which is the 6.
    expect(tightestWin(solid)).toBe(2);
    expect(tightestWin(scrapes)).toBe(0);
  });

  test("reads the most recent game first", () => {
    expect(lastMargin(solid)).toBe(5);            // the 9, not the 7
  });

  test("ignores misses rather than scoring them as tight wins", () => {
    const broken = { line: 4, direction: "over", recent: [leg(1, "loss"), leg(8, "win")] };
    expect(winMargins(broken)).toEqual([4]);
    expect(tightestWin(broken)).toBe(4);
    expect(lastMargin(broken)).toBe(null);        // last game lost — not "comfortable"
  });

  test("a void is not a win either", () => {
    const voided = { line: 10, direction: "under", recent: [leg(10, "void"), leg(7, "win")] };
    expect(winMargins(voided)).toEqual([3]);
    expect(lastMargin(voided)).toBe(null);
  });

  test("has no answer when nothing in the window won", () => {
    expect(tightestWin({ line: 4, direction: "over", recent: [leg(1, "loss")] })).toBe(null);
    expect(tightestWin({ line: 4, direction: "over" })).toBe(null);
  });
});

describe("the comfort filters", () => {
  const scrapes = { line: 4, direction: "over", recent: [leg(4, "win"), leg(4, "win")] };
  const solid = { line: 4, direction: "over", recent: [leg(9, "win"), leg(6, "win")] };
  const lastOneBig = { line: 4, direction: "over", recent: [leg(9, "win"), leg(4, "win")] };

  test("'any' keeps everything, including the scrapes", () => {
    expect([scrapes, solid].filter(comfortFilter("any"))).toHaveLength(2);
  });

  test("'landed big last time' looks only at the newest game", () => {
    const keep = comfortFilter("last-big");
    expect(keep(lastOneBig)).toBe(true);          // newest cleared by 5
    expect(keep(scrapes)).toBe(false);
  });

  test("'never close' judges the whole run, so a big last game does not rescue it", () => {
    const keep = comfortFilter("never-close");
    expect(keep(solid)).toBe(true);
    expect(keep(lastOneBig)).toBe(false);         // the 4 is still in there
    expect(keep(scrapes)).toBe(false);
  });

  test("an unknown key falls back to keeping everything", () => {
    expect(comfortFilter("nonsense")(scrapes)).toBe(true);
  });
});
