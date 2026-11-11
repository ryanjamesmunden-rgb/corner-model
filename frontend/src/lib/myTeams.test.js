import {
  SORTS, SOURCES, VIEWS, FORM_BAR, EV_BAR,
  formTone, scheduleTone, betSummary, evTone,
  idleTeams, missingTeams, filterSummary,
} from "./myTeams";

const proj = (over = {}) => ({
  line: 5, prob: 72.4, fair_odds: 1.38, lambda: 6.1,
  book_odds: 1.73, ev: 25.3, odds_source: "api", ...over,
});

describe("what a row may say about value", () => {
  it("states the edge when a real price is stored", () => {
    const out = betSummary({ projection: proj() });
    expect(out.kind).toBe("priced");
    expect(out.ev).toBe(25.3);
    expect(out.book).toBe(1.73);
    expect(out.line).toBe(5);
  });

  it("accepts a hand-typed price as real", () => {
    expect(betSummary({ projection: proj({ odds_source: "manual" }) }).kind).toBe("priced");
  });

  it("refuses to price against a seeded number", () => {
    // seed_team_odds writes fair_odds * uniform(0.90, 1.15), so an EV measured against
    // one of those is the model reading its own noise — and it looks exactly like an edge.
    const out = betSummary({ projection: proj({ odds_source: "demo" }) });
    expect(out.kind).toBe("model");
    expect(out.ev).toBeUndefined();
    expect(out.book).toBeUndefined();
  });

  it("refuses an unstamped price too", () => {
    // An unmarked document predates the stamp or came from a seeder. "Unknown" must not
    // read as "real".
    for (const src of [undefined, null, "", "unknown"]) {
      expect(betSummary({ projection: proj({ odds_source: src }) }).kind).toBe("model");
    }
  });

  it("keeps the model's own side when there is no price", () => {
    const out = betSummary({ projection: proj({ book_odds: null, ev: null }) });
    expect(out.kind).toBe("model");
    expect(out.prob).toBe(72.4);
    expect(out.fair).toBe(1.38);
    expect(out.note).toBe("no price stored");
  });

  it("distinguishes no price from not modelled", () => {
    // Collapsing the two is how a blank row starts reading as a negative verdict on a
    // game nobody has priced.
    expect(betSummary({ projection: null }).kind).toBe("none");
    expect(betSummary({}).kind).toBe("none");
    expect(betSummary({ projection: { line: 5 } }).kind).toBe("none");
  });
});

describe("form and fixture tone", () => {
  it("calls a lift of a corner a game in form", () => {
    expect(formTone(1.4).tone).toBe("hot");
    expect(formTone(FORM_BAR).tone).toBe("hot");
  });

  it("leaves a smaller move as steady", () => {
    // Below the bar a trend is a different opponent rather than a different team, and the
    // whole list would read as hot.
    expect(formTone(0.6).tone).toBe("steady");
    expect(formTone(-0.6).tone).toBe("steady");
  });

  it("marks a real decline", () => {
    expect(formTone(-1.8).tone).toBe("cold");
    expect(formTone(-1.8).l).toBe("-1.8 on their average");
  });

  it("says so when there is no form at all rather than showing zero", () => {
    expect(formTone(null).tone).toBe("unknown");
    expect(formTone(undefined).l).toBe("no form yet");
  });

  it("reads the server's own schedule label", () => {
    expect(scheduleTone("soft").tone).toBe("hot");
    expect(scheduleTone("tough").tone).toBe("cold");
    expect(scheduleTone("average").tone).toBe("steady");
    expect(scheduleTone(null).tone).toBe("unknown");
  });
});

describe("ev tone", () => {
  it("highlights at the same floor the bot sends on", () => {
    expect(evTone(EV_BAR)).toBe("hot");
    expect(evTone(25.3)).toBe("hot");
    expect(evTone(2.0)).toBe("steady");
    expect(evTone(-30)).toBe("cold");
    expect(evTone(null)).toBe("unknown");
  });
});

describe("rows that need explaining rather than ranking", () => {
  const teams = [
    { team_id: "a", name: "A", next: [{ fixture_id: "1" }] },
    { team_id: "b", name: "B", next: [] },
    { team_id: "c", missing: true, next: [] },
  ];

  it("finds the teams with nothing scheduled", () => {
    expect(idleTeams(teams).map((t) => t.team_id)).toEqual(["b"]);
  });

  it("keeps a missing follow out of the idle list", () => {
    // They are different problems: one side has no games, the other has no team.
    expect(missingTeams(teams).map((t) => t.team_id)).toEqual(["c"]);
  });

  it("survives an empty response", () => {
    expect(idleTeams(null)).toEqual([]);
    expect(missingTeams(undefined)).toEqual([]);
  });
});

describe("the controls", () => {
  it("offers a sort for each question, each with a hint", () => {
    // "Best form" and "Most corners" sound like the same thing and are not: one is the
    // change, the other is the level.
    for (const s of SORTS) {
      expect(s.v).toBeTruthy();
      expect(s.l).toBeTruthy();
      expect(s.hint).toBeTruthy();
    }
    expect(new Set(SORTS.map((s) => s.v)).size).toBe(SORTS.length);
  });

  it("covers both lists and both views", () => {
    expect(SOURCES.map((s) => s.v)).toEqual(["all", "favourites", "tracking"]);
    expect(VIEWS.map((v) => v.v)).toEqual(["teams", "fixtures"]);
  });

  it("summarises what is applied", () => {
    expect(filterSummary({ view: "fixtures", source: "tracking", sort: "run" }))
      .toBe("Fixtures · Tracking · Longest run");
  });

  it("drops an unknown choice rather than printing undefined", () => {
    expect(filterSummary({ view: "teams", source: "nope", sort: "form" }))
      .toBe("Teams · Best form");
  });
});
