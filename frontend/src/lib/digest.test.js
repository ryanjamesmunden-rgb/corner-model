import { digestBands, digestPost, digestRow, claimOf, fixtureOf, ratesOf, priceOf, edgeOf,
         marginOf, runOf, DIGEST_MIN_RUN } from "./digest";
import { bandOf, LINE_BANDS } from "./lineBands";

const row = (name, line, run, extra = {}) => ({
  name, line, line_label: `${line}+`, league_id: "eng-ch",
  streak: { length: run }, avg: line + 2,
  next_fixture: { fixture_id: `fx-${name}`, opponent: "Hull", is_home: true,
                  date: "2026-10-13T14:00:00+00:00" },
  projection: { team_for: 7.8, opp_conceded: 6.2, fair_odds: 1.47 },
  ...extra,
});

const names = (res) => res.bands.flatMap((b) => b.rows.map((r) => r.name));
const bandNamed = (res, id) => res.bands.find((b) => b.band.id === id);


describe("the bands cover every line", () => {
  // bandOf returning null would render a row with no caption at all, which is the one
  // failure mode worse than a wrong caption.
  it("every line from 1 to 20 lands in exactly one band", () => {
    for (let n = 1; n <= 20; n++) {
      const hits = LINE_BANDS.filter((b) => n >= b.min && n <= b.max);
      expect(hits).toHaveLength(1);
      expect(bandOf(n)).toBe(hits[0]);
    }
  });

  it("the money band is 5 and 6, and nothing else", () => {
    expect(bandOf(4).id).not.toBe("money");
    expect(bandOf(5).id).toBe("money");
    expect(bandOf(6).id).toBe("money");
    expect(bandOf(7).id).not.toBe("money");
  });

  it("the money band reads first", () => {
    expect(LINE_BANDS[0].id).toBe("money");
  });
});


describe("what reaches the digest", () => {
  it("a run shorter than the floor is dropped and counted", () => {
    const res = digestBands([row("Reading", 5, 6), row("Hull", 5, 2)]);
    expect(names(res)).toEqual(["Reading"]);
    expect(res.skippedShort).toBe(1);
  });

  it("the floor is the one constant, not a literal", () => {
    const res = digestBands([row("Reading", 5, DIGEST_MIN_RUN)]);
    expect(names(res)).toEqual(["Reading"]);
    expect(digestBands([row("Reading", 5, DIGEST_MIN_RUN - 1)]).qualified).toBe(0);
  });

  it("a row with no line is dropped rather than banded as a zero", () => {
    // It would land in "4+ and below" and get that band's caption, which is a false
    // claim about a row whose line nobody knows.
    expect(digestBands([{ name: "X", streak: { length: 9 } }]).qualified).toBe(0);
  });

  it("a run with no upcoming fixture is dropped", () => {
    // It renders as a team, a line and a run with NOTHING under it — no opponent, no
    // kick-off, no link. That bare claim is what the digest exists to stop printing.
    const orphan = { ...row("Orphan", 5, 9), next_fixture: null };
    expect(digestBands([orphan]).qualified).toBe(0);
    expect(digestBands([orphan, row("Reading", 5, 6)]).shown).toBe(1);
  });

  it("survives an empty or missing payload", () => {
    expect(digestBands([]).shown).toBe(0);
    expect(digestBands().shown).toBe(0);
  });
});


describe("a measured edge leads its band", () => {
  const priced = (name, run, ev, book = 2.05) => {
    const r = row(name, 5, run);
    r.projection = { team_for: 7.8, opp_conceded: 6.2, fair_odds: 1.78,
                     book_odds: book, ev };
    return r;
  };

  it("a priced +EV row goes above a longer unpriced run", () => {
    // It is the only row in the message whose edge is measured rather than assumed.
    const res = digestBands([row("LongRun", 5, 9), priced("Priced", 5, 15.2)]);
    expect(bandNamed(res, "money").rows.map((r) => r.name))
      .toEqual(["Priced", "LongRun"]);
  });

  it("but a price the model does NOT beat gets no promotion", () => {
    // A checked price that fails is evidence AGAINST the row; letting it jump the queue
    // would reward having looked rather than having found something.
    const res = digestBands([row("LongRun", 5, 9), priced("Short", 5, -8.4, 1.55)]);
    expect(bandNamed(res, "money").rows.map((r) => r.name))
      .toEqual(["LongRun", "Short"]);
    expect(edgeOf(priced("Short", 5, -8.4, 1.55))).toBe(0);
  });

  it("the bigger edge leads when two are priced", () => {
    const res = digestBands([priced("Small", 5, 4.1), priced("Big", 5, 22.6)]);
    expect(bandNamed(res, "money").rows.map((r) => r.name)).toEqual(["Big", "Small"]);
  });

  it("a fair price alone is not an edge", () => {
    // Every unpriced row has fair_odds. If those counted, the key would do nothing.
    expect(edgeOf(row("Reading", 5, 6))).toBe(0);
    expect(edgeOf({})).toBe(0);
  });

  it("it does not reach across bands", () => {
    // A +EV 3+ does not belong above an unpriced 6+: the band order is the record, and
    // one priced row is not a reason to lead on the lines that have cost money.
    const low = priced("LowPriced", 9, 30);
    low.line = 3;
    low.line_label = "3+";
    const res = digestBands([low, row("Reading", 6, 5)]);
    expect(res.bands[0].band.id).toBe("money");
    expect(res.bands[0].rows.map((r) => r.name)).toEqual(["Reading"]);
  });
});


describe("the order inside a band is the run, not the line", () => {
  // The endpoint sorts by line descending. Left alone, the digest would re-apply that
  // order inside a band it had just finished re-sorting away from it.
  it("longest run first", () => {
    const res = digestBands([row("A", 5, 5), row("B", 6, 9), row("C", 5, 7)]);
    expect(bandNamed(res, "money").rows.map((r) => r.name)).toEqual(["B", "C", "A"]);
  });

  it("margin breaks a tie", () => {
    // Two six-game runs at 5+ are not the same bet if one clears by three a game and the
    // other by half of one.
    const tight = { ...row("Tight", 5, 6), avg: 5.4 };
    const roomy = { ...row("Roomy", 5, 6), avg: 8.2 };
    const res = digestBands([tight, roomy]);
    expect(bandNamed(res, "money").rows.map((r) => r.name)).toEqual(["Roomy", "Tight"]);
    expect(marginOf(roomy)).toBeCloseTo(3.2);
    expect(marginOf(tight)).toBeCloseTo(0.4);
  });

  it("a row with no average still ranks, last among its equals", () => {
    const blind = { ...row("Blind", 5, 6), avg: null };
    const res = digestBands([blind, row("Known", 5, 6)]);
    expect(bandNamed(res, "money").rows.map((r) => r.name)).toEqual(["Known", "Blind"]);
    expect(marginOf(blind)).toBeNull();
  });

  it("a missing number stays missing instead of becoming nought", () => {
    // Number(null) is 0 and so is Number(""), so the obvious one-liner turns an absent
    // average into a real zero — which ranks as if the team cleared its line by minus
    // five, and prints "Reading 0.0 at home" against a rate nobody measured.
    expect(marginOf({ avg: null, line: 5 })).toBeNull();
    expect(marginOf({ avg: "", line: 5 })).toBeNull();
    expect(marginOf({ avg: 7, line: null })).toBeNull();
    const blind = row("Blind", 5, 6);
    blind.projection = { team_for: null, opp_conceded: 6.2, fair_odds: 1.5 };
    expect(ratesOf(blind)).toBe("");
    expect(priceOf({ projection: { fair_odds: null } })).toBe("");
  });
});


describe("the caps", () => {
  const many = (n, line) => Array.from({ length: n },
                                       (_, i) => row(`T${i}`, line, 9 - (i % 4)));

  it("hold back the overflow and say how many", () => {
    const res = digestBands(many(10, 5), { caps: { money: 6, below: 3, long: 2 } });
    expect(bandNamed(res, "money").rows).toHaveLength(6);
    expect(bandNamed(res, "money").held).toBe(4);
    expect(res.held).toBe(4);
  });

  it("count the band's real total, not the capped one", () => {
    const res = digestBands(many(10, 5));
    expect(bandNamed(res, "money").total).toBe(10);
    expect(res.qualified).toBe(10);
  });

  it("a short list is not padded or truncated", () => {
    const res = digestBands(many(2, 5));
    expect(bandNamed(res, "money").rows).toHaveLength(2);
    expect(bandNamed(res, "money").held).toBe(0);
  });
});


describe("a row's three lines", () => {
  const dayTime = () => "Mon 15:00";

  it("the claim is the team, the line and the run", () => {
    expect(claimOf(row("Reading", 6, 7))).toBe("Reading 6+ — 7 in a row");
  });

  it("a run of one is not called a run", () => {
    expect(claimOf(row("Reading", 6, 1))).toBe("Reading 6+");
  });

  it("the venue letter is about the next game", () => {
    expect(fixtureOf(row("Reading", 6, 7), dayTime)).toBe("v Hull (H) · Mon 15:00");
    const away = row("Reading", 6, 7);
    away.next_fixture.is_home = false;
    expect(fixtureOf(away, dayTime)).toContain("(A)");
  });

  it("never claims the RUN happened at a venue", () => {
    // The board is asked for `overall` runs, so "7 in a row at home" would be false.
    const text = digestRow(row("Reading", 6, 7), { site: "", dayTime });
    expect(text).not.toMatch(/in a row at home/);
    expect(text).not.toMatch(/in a row away/);
  });

  it("the rates name both sides and which venue each is at", () => {
    expect(ratesOf(row("Reading", 6, 7)))
      .toBe("Reading 7.8 at home, Hull concede 6.2 away");
  });

  it("the rates are both or neither", () => {
    // Printing one invites a reader to check it against a price built from two.
    const half = row("Reading", 6, 7);
    half.projection = { team_for: 7.8, fair_odds: 1.5 };
    expect(ratesOf(half)).toBe("");
    expect(ratesOf({ name: "X" })).toBe("");
  });

  it("a fair price is just the price — the caveat is said once, at the bottom", () => {
    // The caveat is in the footer, once, not on all eleven rows.
    expect(priceOf(row("Reading", 6, 7))).toBe("fair 1.47");
  });

  it("a real price leads, with its edge", () => {
    const priced = row("Reading", 6, 7);
    priced.projection = { team_for: 7.8, opp_conceded: 6.2, fair_odds: 1.47,
                          book_odds: 1.85, ev: 25.9 };
    expect(priceOf(priced)).toBe("book 1.85 v fair 1.47 (+26% EV)");
  });

  it("the link goes to the fixture page the numbers came from", () => {
    expect(digestRow(row("Reading", 6, 7), { site: "https://x.com", dayTime }))
      .toContain("https://x.com/fixture/fx-Reading");
  });

  it("no site means no link, rather than a link to nowhere", () => {
    const text = digestRow(row("Reading", 6, 7), { dayTime });
    expect(text).not.toContain("↳");
    expect(text).not.toContain("/fixture/");
  });

  it("runOf and marginOf survive a row with nothing in it", () => {
    expect(runOf({})).toBe(0);
    expect(runOf(undefined)).toBe(0);
    expect(marginOf({})).toBeNull();
  });
});


describe("the message", () => {
  const opts = { site: "https://thecornermodel.com", dayLabel: "Mon 13 Oct",
                 dayTime: () => "Mon 15:00", windowLabel: "today and tomorrow" };

  it("leads with the money band and its record", () => {
    const text = digestPost({ rows: [row("Reading", 6, 7)], ...opts });
    expect(text.indexOf("5+ AND 6+")).toBeLessThan(text.indexOf("Reading"));
    expect(text).toContain("90 bets");
    expect(text).toContain("+48.47u");
  });

  it("every band record carries its denominator", () => {
    // A rate without one is unfalsifiable, and the 7+ band only reads honestly because
    // the 12 is next to it.
    const text = digestPost({ rows: [row("A", 6, 7), row("B", 4, 7), row("C", 8, 7)],
                              ...opts });
    LINE_BANDS.forEach((b) => expect(text).toContain(`${b.bets} bets`));
  });

  it("marks the low band rather than hiding it", () => {
    const text = digestPost({ rows: [row("Barnsley", 4, 6)], ...opts });
    expect(text).toContain("Barnsley");
    expect(text).toContain("below the money band");
    expect(text).toContain("-12.90u");
  });

  it("says the 7+ band is thin rather than calling it bad", () => {
    const text = digestPost({ rows: [row("Long", 8, 6)], ...opts });
    expect(text).toContain("too few to judge");
    expect(text).not.toMatch(/avoid/i);
  });

  it("an empty money band still prints, because that is the useful sentence", () => {
    const text = digestPost({ rows: [row("Barnsley", 4, 6)], ...opts });
    expect(text).toContain("5+ AND 6+");
    expect(text).toContain("Nothing here today.");
  });

  it("an empty low band is dropped — it is context, not the point", () => {
    const text = digestPost({ rows: [row("Reading", 6, 7)], ...opts });
    expect(text).not.toContain("4+ AND BELOW");
    expect(text).not.toContain("7+ AND UP");
  });

  it("nothing at all says WHICH kind of nothing", () => {
    const quiet = digestPost({ rows: [], ...opts });
    expect(quiet).toContain("Nothing on the streak board");

    const shortRuns = digestPost({ rows: [row("A", 5, 2), row("B", 6, 3)], ...opts });
    expect(shortRuns).toContain("2 shorter runs");
    expect(shortRuns).not.toContain("Nothing on the streak board");
  });

  it("says once, at the bottom, that the price is the model's", () => {
    const text = digestPost({ rows: [row("A", 6, 7), row("B", 5, 6)], ...opts });
    expect(text).toContain("the model's price");
    expect(text.match(/the model's price/g)).toHaveLength(1);
    // And NOT on every row, which is where the original complaint came from.
    expect(text).not.toContain("no book price stored");
  });

  it("labels the band figures as hand-kept, wherever they appear", () => {
    const text = digestPost({ rows: [row("A", 6, 7)], ...opts });
    expect(text).toContain("Typed by hand, not graded by the site");
  });

  it("says it is streaks only, which is the whole promise", () => {
    expect(digestPost({ rows: [row("A", 6, 7)], ...opts }))
      .toContain("no chase board");
    expect(digestPost({ rows: [], ...opts })).toContain("no chase board");
  });

  it("fits a Telegram message with a full board behind it", () => {
    const many = Array.from({ length: 80 },
                            (_, i) => row(`Team ${i}`, 4 + (i % 5), 5 + (i % 6)));
    const text = digestPost({ rows: many, ...opts });
    expect(text.length).toBeLessThan(4096);
    expect(text).toMatch(/more in this band on the site/);
  });

  it("names the window, so a row kicking off tomorrow is not read as tonight", () => {
    expect(digestPost({ rows: [row("A", 6, 7)], ...opts }))
      .toContain("today and tomorrow");
  });
});
