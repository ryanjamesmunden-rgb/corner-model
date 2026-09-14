// The published results table.
//
// The failure guarded here is not a wrong number — it is a right number arranged into a
// wrong impression: a running month sitting beside closed ones with a total that reads as
// final. Same trap the day card had, on the page where a buyer is deciding whether to
// believe anything else on the site.

import { summarise, totalLabel, periodNote } from "./resultsSummary.js";

const CLOSED = [
  { period: "June - July", units: 17.14 },
  { period: "August", units: 20.73 },
];
const WITH_RUNNING = [...CLOSED, { period: "September", units: 16, partial: true }];

describe("totalling the months", () => {
  test("closed months add up and claim nothing extra", () => {
    expect(summarise(CLOSED)).toMatchObject({ total: 37.87, settled: 37.87, partial: false });
    expect(summarise(CLOSED).running).toEqual([]);
  });

  test("a running month is counted but flagged", () => {
    // Counted, because hiding it would understate; flagged, because a total containing a
    // fortnight of an unfinished month is not the same claim as one that does not.
    expect(summarise(WITH_RUNNING)).toMatchObject({
      total: 53.87, settled: 37.87, partial: true, running: ["September"],
    });
  });

  test("the settled figure excludes it, so there is always one nobody can argue with", () => {
    expect(summarise(WITH_RUNNING).settled).toBe(summarise(CLOSED).total);
  });

  test("floating point does not leak onto a money figure", () => {
    // 17.14 + 20.73 + 16 is 53.870000000000005 in binary floating point, and that is what
    // would be published without the rounding.
    expect(String(summarise(WITH_RUNNING).total)).toBe("53.87");
  });

  test("a losing month subtracts rather than being dropped", () => {
    expect(summarise([{ period: "A", units: 10 }, { period: "B", units: -4.5 }]).total)
      .toBe(5.5);
  });

  test("rubbish rows are ignored rather than becoming NaN", () => {
    // One malformed row must not turn the whole published total into "NaN pts".
    expect(summarise([{ period: "A", units: 10 }, { period: "B" }, null]).total).toBe(10);
    expect(summarise([]).total).toBe(0);
    expect(summarise().total).toBe(0);
  });
});

describe("what the table says about itself", () => {
  test("the total names the month that is still running", () => {
    // "1 month still running" makes a reader hunt for which one when the answer is in the
    // table in front of them.
    expect(totalLabel(WITH_RUNNING)).toBe("Since June · September still running");
  });

  test("and says nothing extra when every month has closed", () => {
    expect(totalLabel(CLOSED)).toBe("Since June");
  });

  test("the running row carries its own label too", () => {
    // Belt and braces: the caveat is on the row AND on the total, because a reader who
    // looks at one line is the reader most likely to misread it.
    expect(periodNote({ period: "September", partial: true })).toBe("month to date");
    expect(periodNote({ period: "August" })).toBe("");
    expect(periodNote()).toBe("");
  });
});
