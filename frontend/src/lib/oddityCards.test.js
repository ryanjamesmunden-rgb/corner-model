import { oddityCard, oddityCards, CARD_KEYS } from "./oddityCards.js";

const post = (key, facts) => ({ key, facts, text: "some prose" });

describe("the hero is the number the fact is about", () => {
  it("takes the margin on a rout, not the winning count", () => {
    // 14-0 and 9-2 are both sevens of margin on the eye and are not the same fact; the
    // margin is what the post claims, so it is what the card leads with.
    const c = oddityCard(post("rout", {
      team: "Barnet", opponent: "Swindon Town", corners_for: 14,
      corners_against: 0, margin: 14, date: "2026-10-20",
    }));
    expect(c.hero).toBe("+14");
    expect(c.detail).toContain("Barnet 14, Swindon Town 0");
  });

  it("takes the gap on a venue split, not the home average", () => {
    const c = oddityCard(post("venue", {
      team: "Heracles", home_avg: 8.5, away_avg: 2.6, gap: 5.9, stronger: "home",
    }));
    expect(c.hero).toBe("5.9");
    expect(c.detail).toContain("8.5 at home");
    expect(c.detail).toContain("2.6 away");
  });

  it("says so when a side is better away, because the default sentence would be wrong", () => {
    const c = oddityCard(post("venue", {
      team: "Someone", home_avg: 3.1, away_avg: 7.0, gap: 3.9, stronger: "away",
    }));
    expect(c.headline).toMatch(/away/i);
  });

  it("keeps futility as a pair, because either half alone is unremarkable", () => {
    const c = oddityCard(post("futility", {
      team: "Oddevold", for_avg: 6.8, goals_avg: 0.6, games: 20,
    }));
    expect(c.hero).toBe("6.8 : 0.6");
  });

  it("renders a perfect record as the fraction it is", () => {
    const c = oddityCard(post("perfect", {
      team: "Rangers", games: 14, for_avg: 7.7, against_avg: 3.1,
    }));
    expect(c.hero).toBe("14/14");
  });
});

describe("the denominator survives the trip to a picture", () => {
  it("keeps the population on a floor claim", () => {
    const c = oddityCard(post("floor", { team: "X", floor: 4, games: 20 }),
                         { survey: { pool: { teams: 548 } } });
    expect(c.meta.join(" ")).toContain("548");
  });

  it("keeps the game count on a wildest-match claim", () => {
    const c = oddityCard(post("wildest", {
      team: "Cambridge United", opponent: "Wycombe", total: 21,
      corners_for: 12, corners_against: 9,
    }), { survey: { pool: { games: 12480 } } });
    expect(c.hero).toBe("21");
    expect(c.meta.join(" ")).toContain("12,480");
  });

  it("drops an empty meta slot rather than printing a dangling separator", () => {
    const c = oddityCard(post("wildest", {
      team: "A", opponent: "B", total: 19, corners_for: 10, corners_against: 9,
    }));
    expect(c.meta.every((m) => m && m.trim())).toBe(true);
  });
});

describe("it refuses rather than printing a blank number", () => {
  it("returns null when the hero figure is missing", () => {
    expect(oddityCard(post("haul", { team: "X", corners_for: null }))).toBeNull();
    expect(oddityCard(post("venue", { team: "X", gap: null }))).toBeNull();
    expect(oddityCard(post("leagues", { gap: 3.1 }))).toBeNull();   // no top/bottom
  });

  it("returns null for a key it has no spec for, rather than half a card", () => {
    expect(oddityCard(post("not_a_real_key", { anything: 1 }))).toBeNull();
  });

  it("survives a post with no facts at all", () => {
    expect(oddityCard({ key: "rout" })).toBeNull();
    expect(oddityCard(null)).toBeNull();
    expect(oddityCard({})).toBeNull();
  });

  it("drops the unsupported ones from a day's set instead of failing the set", () => {
    const cards = oddityCards([
      post("wildest", { team: "A", opponent: "B", total: 18, corners_for: 10, corners_against: 8 }),
      post("haul", { team: "C", corners_for: null }),
    ]);
    expect(cards).toHaveLength(1);
    expect(cards[0].key).toBe("wildest");
  });
});

describe("it carries the prose it came from", () => {
  it("keeps the post text so the picture and the words cannot diverge", () => {
    const c = oddityCard({ key: "haul", facts: { team: "A", corners_for: 20 },
                           text: "The most corners any side here has won is 20." });
    expect(c.text).toContain("20");
  });
});

describe("every finding has a card", () => {
  it("covers every builder key oddityPosts can produce", () => {
    // If a fact is added to oddityPosts and not here, the day it leads the rotation is
    // the day the tweet silently loses its picture. Kept in sync with BUILDERS by the
    // test below, which reads the real list rather than this copy of it.
    expect(CARD_KEYS.sort()).toEqual([
      "barren", "ceiling", "clearing", "club", "floor", "futility", "haul",
      "leagues", "leaky", "perfect", "punching", "rout", "unbeaten", "venue",
      "wildest",
    ].sort());
  });

  it("matches BUILDERS exactly, in both directions", () => {
    // The hand-written list above can drift from the code. This cannot: a builder with
    // no card loses its picture, and a card with no builder is dead weight nothing can
    // ever reach.
    const { BUILDERS } = require("./oddityPosts.js");
    expect(CARD_KEYS.sort()).toEqual(BUILDERS.map(([k]) => k).sort());
  });
});

describe("a run card carries its run and says when it is only a floor", () => {
  const run = (over = {}) => ({
    run: 14, since: "2026-08-16", at_least: false, games: 20, drawn: 0, ...over,
  });

  it("leads with the run length, because the date cannot be the hero", () => {
    const c = oddityCard(post("unbeaten", run()));
    expect(c.hero).toBe("14");
    expect(c.detail).toContain("16 August");
  });

  it("marks a run that fills our window as a floor, not a figure", () => {
    // The sync keeps a rolling window per team, so a run reaching the oldest game we
    // hold began somewhere we cannot see. "14" there would state our storage limit as
    // a fact about football.
    const c = oddityCard(post("unbeaten", run({ at_least: true })));
    expect(c.hero).toBe("14+");
    expect(c.meta.join(" ")).toContain("our record starts there");
  });

  it("says a level count did not break the run, so a checker is not surprised", () => {
    const c = oddityCard(post("unbeaten", run({ drawn: 3 })));
    expect(c.meta.join(" ")).toContain("3 finished level");
  });

  it("refuses without a start date, because half the claim is missing", () => {
    expect(oddityCard(post("unbeaten", run({ since: null })))).toBeNull();
  });

  it("puts the line in the unit on a clearing run", () => {
    const c = oddityCard(post("clearing", run({ line: 6 })));
    expect(c.hero).toBe("14");
    expect(c.unit).toContain("6+");
  });

  it("reads a barren run as the mark they have NOT reached", () => {
    const c = oddityCard(post("barren", run({ mark: 4, best_in_run: 3 })));
    expect(c.hero).toBe("14");
    expect(c.unit).toBe("games under 4");
    expect(c.headline).toContain("have not managed 4".replace("have", "Have"));
  });

  it("drops a clearing run with no line and a barren run with no mark", () => {
    expect(oddityCard(post("clearing", run()))).toBeNull();
    expect(oddityCard(post("barren", run()))).toBeNull();
  });
});

describe("the club profile leads with the club's own average", () => {
  const club = (over = {}) => ({
    team: "Barnsley", league: "League One", games: 18, for_avg: 7.75,
    against_avg: 5.2, floor: 3, ceiling: 13, home_avg: 8.4, away_avg: 6.9,
    goals_avg: 1.4, league_place: 2, league_size: 24, ...over,
  });

  it("is a profile, so the hero is an average and the headline is the name", () => {
    const c = oddityCard(post("club", club()));
    expect(c.hero).toBe("7.8");
    expect(c.headline).toBe("Barnsley");
  });

  it("gives the place a field size, because a place without one is not a place", () => {
    const c = oddityCard(post("club", club()));
    expect(c.meta.join(" ")).toContain("2 of 24");
  });

  it("drops the place rather than printing a rank out of one", () => {
    const c = oddityCard(post("club", club({ league_size: 1, league_place: 1 })));
    expect(c.meta.join(" ")).not.toContain("1 of 1");
  });

  it("survives a club with no venue split", () => {
    const c = oddityCard(post("club", club({ home_avg: null, away_avg: null })));
    expect(c.hero).toBe("7.8");
    expect(c.meta.every((m) => m && m.trim())).toBe(true);
  });
});
