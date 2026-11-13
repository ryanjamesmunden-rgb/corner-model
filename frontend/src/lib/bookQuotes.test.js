import {
  THIN_MARKET, OUTLIER_CLEAR,
  hasQuotes, quoteList, isOutlier, quoteSummary, quoteWarning, atBook, evAtBook,
} from "./bookQuotes";

// A market as value_board's shape() hands it over, quotes already best first.
const market = (quotes, over = {}) => ({
  key: "home_over_5.5", group: "home", label: "Home Team Over 5.5", line: 5.5,
  book_odds: quotes?.[0]?.price, fair_odds: 2.11, prob: 47.5, ev: 10.2,
  price_source: "api", book: quotes?.[0]?.book,
  quotes, ...over,
});

const TIGHT = [{ book: "Betano", price: 2.32 }, { book: "1xBet", price: 2.29 },
               { book: "Marathonbet", price: 2.28 }];
const LONE = [{ book: "Betano", price: 5.30 }];
const CLEAR = [{ book: "Betano", price: 3.45 }, { book: "1xBet", price: 3.00 },
               { book: "Pinnacle", price: 2.95 }];

describe("whether there is anything to open", () => {
  it("knows a market with books from one without", () => {
    expect(hasQuotes(market(TIGHT))).toBe(true);
    expect(hasQuotes(market([]))).toBe(false);
    // Rows stored before the feed kept every book have no quotes at all, and every
    // reader has to cope with that rather than assume the field is there.
    expect(hasQuotes({ book_odds: 2.1 })).toBe(false);
    expect(hasQuotes()).toBe(false);
  });
});

describe("the list", () => {
  it("comes back best first with the best marked", () => {
    const rows = quoteList(market(TIGHT));
    expect(rows.map((r) => r.book)).toEqual(["Betano", "1xBet", "Marathonbet"]);
    expect(rows[0].isBest).toBe(true);
    expect(rows[1].isBest).toBe(false);
  });

  it("says how far behind the best each other book is", () => {
    const rows = quoteList(market(TIGHT));
    expect(rows[0].behind).toBe(0);          // nothing is behind itself
    expect(rows[1].behind).toBe(1.3);        // 2.32 / 2.29
    expect(rows[2].behind).toBe(1.8);        // 2.32 / 2.28
  });

  it("uses the same arithmetic as the backend spread, so the two cannot disagree", () => {
    // quote_spread reports over_second as (best / second - 1) * 100. A row-level figure
    // computed the other way round would differ from the summary beside it.
    const rows = quoteList(market(CLEAR));
    expect(rows[1].behind).toBe(15);         // 3.45 / 3.00
  });

  it("drops a junk entry rather than sorting it", () => {
    const rows = quoteList(market([{ book: "A", price: 2.3 }, { book: "", price: 2.2 },
                                   { book: "C", price: null }, { book: "D", price: 0 }]));
    expect(rows.map((r) => r.book)).toEqual(["A"]);
  });

  it("is empty rather than throwing for nothing at all", () => {
    expect(quoteList(market([]))).toEqual([]);
    expect(quoteList({})).toEqual([]);
    expect(quoteList()).toEqual([]);
  });
});

describe("is the best price out on its own", () => {
  it("says no for a market that agrees with itself", () => {
    expect(isOutlier(market(TIGHT))).toBe(false);
  });

  it("says yes when only one book quoted it", () => {
    // THE CASE THAT MATTERS MOST. On the first ladder carrying quotes, the two biggest
    // edges on a fixture — +27.9% and +22.1% — were each a single book on a long rung,
    // while every rung three or more books priced came in under +11%.
    expect(isOutlier(market(LONE))).toBe(true);
    expect(THIN_MARKET).toBe(2);
  });

  it("says yes when several quoted it and the best is miles clear", () => {
    // The same problem wearing a disguise: the other books are the market.
    expect(isOutlier(market(CLEAR))).toBe(true);
    expect(OUTLIER_CLEAR).toBe(8);
  });

  it("is inclusive at the bar", () => {
    const at = [{ book: "A", price: 2.16 }, { book: "B", price: 2.0 }];   // exactly 8%
    expect(isOutlier(market(at))).toBe(true);
    const under = [{ book: "A", price: 2.1 }, { book: "B", price: 2.0 }]; // 5%
    expect(isOutlier(market(under))).toBe(false);
  });

  it("says no rather than yes when there is nothing to judge", () => {
    expect(isOutlier(market([]))).toBe(false);
  });
});

describe("the summary on the control", () => {
  it("counts the books and says how clear the best is", () => {
    expect(quoteSummary(market(TIGHT))).toBe("3 books · best +1.3% clear");
  });

  it("names the one book when there is only one", () => {
    expect(quoteSummary(market(LONE))).toBe("1 book only (Betano)");
  });

  it("says nothing when there is nothing to summarise", () => {
    expect(quoteSummary(market([]))).toBe("");
  });
});

describe("the warning, in words rather than in a colour", () => {
  it("stays silent on a market that agrees with itself", () => {
    expect(quoteWarning(market(TIGHT))).toBe("");
  });

  it("says a single quote has nothing to check it against", () => {
    expect(quoteWarning(market(LONE)))
      .toBe("Only one book quoted this line — nothing to check it against.");
  });

  it("names the gap when the best is clear of the field", () => {
    // A tint says "something is different" and nothing about what. The row that could
    // lose somebody money is the row that has to use words.
    expect(quoteWarning(market(CLEAR)))
      .toBe("This price is 15% clear of every other book. "
            + "A line that far out is more often stale than a genuine edge.");
  });
});

describe("the reader's own bookmaker", () => {
  it("finds their price and what it costs against the top", () => {
    const row = atBook(market(TIGHT), "Marathonbet");
    expect(row.price).toBe(2.28);
    expect(row.behind).toBe(1.8);
  });

  it("matches however the name is cased or spaced", () => {
    expect(atBook(market(TIGHT), "  marathonbet ").price).toBe(2.28);
  });

  it("answers null when they are not on the list at all", () => {
    // The feed takes the best of 33 books and the best is frequently not one anybody
    // holds, which is exactly what makes a headline edge unactionable.
    expect(atBook(market(TIGHT), "Bet365")).toBeNull();
    expect(atBook(market(TIGHT), "")).toBeNull();
  });

  it("recomputes the edge at their price, not at the best", () => {
    // prob is a PERCENTAGE on the wire. Using it as a fraction reports an edge about a
    // hundred times too big, which on this board would be a +10,000% row.
    expect(evAtBook(market(TIGHT), "Betano")).toBe(10.2);        // 2.32 * 0.475
    expect(evAtBook(market(TIGHT), "Marathonbet")).toBe(8.3);    // 2.28 * 0.475
  });

  it("answers null rather than guessing when it cannot", () => {
    expect(evAtBook(market(TIGHT), "Bet365")).toBeNull();
    expect(evAtBook(market(TIGHT, { prob: null }), "Betano")).toBeNull();
  });
});
