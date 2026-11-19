import { dayOptions, boardParams, dayOf, londonDay } from "./valueQuery";

// The control that decides WHICH DAY the channel card is about. Getting it wrong does not
// break anything on screen — it posts the wrong games under the right heading.

describe("londonDay", () => {
  it("files a late kick-off under the London day, not the UTC one", () => {
    // 23:30 UTC on 21 June is 00:30 on the 22nd in London. The first ten characters of
    // the timestamp say the 21st; the day the game belongs to is the 22nd.
    expect(londonDay(new Date("2026-06-21T23:30:00Z"))).toBe("2026-06-22");
    // And in winter, when London is UTC, the two agree.
    expect(londonDay(new Date("2026-11-21T23:30:00Z"))).toBe("2026-11-21");
  });
});

describe("dayOptions", () => {
  const now = new Date("2026-11-19T10:00:00Z");   // a Thursday

  it("opens on all upcoming and names the next seven days", () => {
    const o = dayOptions(now);
    expect(o[0]).toEqual({ v: "all", l: "All upcoming" });
    expect(o[1].l).toBe("Today");
    expect(o[2].l).toBe("Tomorrow");
    expect(o.at(-1)).toEqual({ v: "w:7", l: "Next 7 days" });
    expect(o).toHaveLength(9);
  });

  it("carries the real dates, so Today is today", () => {
    const o = dayOptions(now);
    expect(o[1].v).toBe("d:2026-11-19");
    expect(o[2].v).toBe("d:2026-11-20");
    expect(o[3].v).toBe("d:2026-11-21");
  });

  it("names the days past tomorrow rather than counting them", () => {
    // "Sat 21 Nov" is readable next to a fixture list; "in 2 days" is not.
    expect(dayOptions(now)[3].l).toMatch(/Sat/);
    expect(dayOptions(now)[4].l).toMatch(/Sun/);
  });
});

describe("boardParams", () => {
  it("sends a day for a day", () => {
    expect(boardParams("d:2026-11-21", "5"))
      .toEqual({ day: "2026-11-21", min_ev: 5, limit: 40 });
  });

  it("sends a horizon for a range", () => {
    expect(boardParams("w:7", "0")).toEqual({ within_days: 7, min_ev: 0, limit: 40 });
  });

  it("sends NEITHER for all upcoming", () => {
    // within_days is optional on the server and leaving it out is how the horizon is
    // switched off. Sending 0 reads as a zero-day horizon and returns nothing.
    const p = boardParams("all", "-100");
    expect(p).toEqual({ min_ev: -100, limit: 40 });
    expect(p.within_days).toBeUndefined();
    expect(p.day).toBeUndefined();
  });

  it("passes extras through, which is how the card asks for the ladder", () => {
    expect(boardParams("d:2026-11-21", "5", { ladder: true }).ladder).toBe(true);
  });
});

describe("dayOf", () => {
  it("is the day, or nothing for a range", () => {
    expect(dayOf("d:2026-11-21")).toBe("2026-11-21");
    expect(dayOf("w:7")).toBe("");
    expect(dayOf("all")).toBe("");
    expect(dayOf(undefined)).toBe("");
  });
});
