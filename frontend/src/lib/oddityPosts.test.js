// Eleven posts that have to be eleven different posts.
//
// WHAT THESE GUARD. The failure this module exists to fix is not a crash — it is a set of
// candidates that are all the same sentence, which is what the old stat board produced and
// what got the complaint. So the first test below is a structural one: no two candidates
// may open the same way. The rest are the safety rules, which matter more here than
// anywhere else on the site because these posts NAME CLUBS and go out in public:
//
//   - A PREDICTION. Every sentence describes matches already played. FORWARD_WORDS is
//     asserted against every candidate, every time.
//   - AN UNBOUNDED SUPERLATIVE. "The widest in Europe" is a claim about leagues we do not
//     hold; "the widest of the 548 teams on the site" is checkable.
//   - A MISSING DENOMINATOR. A floor of 6 over 20 games is a story; over three it is not.
//   - BROKEN ENGLISH from a ternary spliced into a template — the bug digest.js shipped.
//   - OVER 280 by X's weighted count, with the link counted at its flat t.co cost.
//   - A LEAD THAT NEVER MOVES, which is the same complaint arriving a month later.
import {
  BUILDERS, FORWARD_WORDS, ceilingPost, dayIndex, floorPost, futilityPost, haulPost,
  leaguesPost, leakyPost, oddityPosts, perfectPost, punchingPost, rotate, routPost,
  venuePost, who, when, wildestPost,
} from "./oddityPosts.js";
import { xWeight, X_MAX_WEIGHT } from "./xLimit.js";

const SITE = "https://thecornermodel.com";
const NOW = new Date("2026-10-16T09:00:00Z");

const POOL = { teams: 548, teams_seen: 560, games: 9840, leagues: 26, min_games: 10 };

/** A full survey, so every builder has something to find. */
const survey = (over = {}) => ({
  pool: { ...POOL, ...(over.pool || {}) },
  findings: {
    biggest_rout: {
      team: "Blackburn", country: "England", league: "Championship",
      opponent: "Stoke", date: "2026-09-14T15:00:00Z", home: true,
      corners_for: 16, corners_against: 1, margin: 15, goals_for: 2, goals_against: 0,
    },
    biggest_haul: {
      team: "Vejle", country: "Denmark", league: "Superliga",
      opponent: "Lyngby", date: "2026-08-22T15:00:00Z", home: false,
      corners_for: 17, corners_against: 6, goals_for: 1, goals_against: 1,
    },
    wildest_game: {
      team: "Boca Juniors", country: "Argentina", league: "Liga Profesional",
      opponent: "Racing", date: "2026-09-03T22:00:00Z", home: true,
      corners_for: 14, corners_against: 13, total: 27, goals_for: 1, goals_against: 1,
    },
    highest_floor: {
      team: "Celtic", country: "Scotland", league: "Premiership",
      games: 20, floor: 5, ceiling: 14, for_avg: 8.4, against_avg: 2.9,
    },
    lowest_ceiling: {
      team: "Lecce", country: "Italy", league: "Serie A",
      games: 18, floor: 0, ceiling: 4, for_avg: 2.1, against_avg: 7.4,
    },
    widest_venue_gap: {
      team: "Rosenborg", country: "Norway", league: "Eliteserien",
      games: 20, home_avg: 8.4, away_avg: 3.1, gap: 5.3, stronger: "home",
      for_avg: 5.8, against_avg: 4.4,
    },
    never_outcornered: {
      team: "Lazio", country: "Italy", league: "Serie A",
      games: 20, won_count: 20, lost_count: 0, for_avg: 7.2, against_avg: 3.4,
    },
    all_corners_no_goals: {
      team: "Reading", country: "England", league: "League One",
      games: 18, for_avg: 7.9, goals_avg: 0.6, pool: 12, of: 548,
      against_avg: 4.1,
    },
    leakiest: {
      team: "Grimsby", country: "England", league: "League Two",
      games: 18, against_avg: 8.9, for_avg: 3.2,
    },
    league_extremes: {
      top: { league: "Liga Profesional", country: "Argentina", per_match: 11.8, tier: 1 },
      bottom: { league: "J1 League", country: "Japan", per_match: 8.6, tier: 1 },
      gap: 3.2, leagues: 26,
    },
    punching_up: {
      team: { team: "Harrogate", country: "England", league: "League Two",
              games: 18, for_avg: 7.4, tier: 4 },
      beats: { team: "Atalanta", league: "Serie A", country: "Italy",
               for_avg: 6.9, tier: 1 },
      beaten_leagues: 3, of_top_flights: 20,
    },
    ...(over.findings || {}),
  },
});

const all = (over) => oddityPosts({ survey: survey(over), site: SITE, now: NOW, limit: 99 });


describe("they are actually different posts", () => {
  // THE WHOLE POINT OF THE MODULE, ASSERTED FIRST. The board it replaced offered four
  // candidates that were one sentence with the threshold moved.
  test("no two candidates open with the same six words", () => {
    const openings = all().map((c) => c.text.split(/\s+/).slice(0, 6).join(" ").toLowerCase());
    expect(new Set(openings).size).toBe(openings.length);
  });

  test("no two candidates share a whole sentence", () => {
    const seen = new Map();
    for (const c of all()) {
      // The body only. Every post ends with the same link line by design, and counting
      // that as a shared sentence would fail this test for the one thing they are
      // supposed to have in common.
      const body = c.text.split("\n\n")[0];
      for (const s of body.split(/(?<=\.)\s+/)) {
        const key = s.trim().toLowerCase();
        if (key.length < 12) continue;          // "All 20." is not a template
        expect(seen.has(key)).toBe(false);
        seen.set(key, c.key);
      }
    }
  });

  test("every builder produces something from a full survey", () => {
    expect(all().map((c) => c.key).sort())
      .toEqual(BUILDERS.map(([k]) => k).sort());
  });
});


describe("nothing here is a tip", () => {
  // The line that must not move: these name clubs, so a single forward-looking verb turns
  // a published record into unqualified advice.
  test.each(BUILDERS)("%s carries no forward-looking language", (key, fn) => {
    const c = fn({ findings: survey().findings, pool: POOL, site: SITE });
    const text = c.text.toLowerCase();
    for (const word of FORWARD_WORDS) {
      expect(text).not.toContain(word);
    }
  });

  test("every sentence is in the past or the present perfect", () => {
    // A crude but effective check: no candidate may contain a bare future auxiliary.
    for (const c of all()) {
      expect(c.text).not.toMatch(/\b(will|won't|going to|set to)\b/i);
    }
  });

  test("no candidate mentions an upcoming fixture", () => {
    for (const c of all()) {
      expect(c.text.toLowerCase()).not.toMatch(/\b(tonight|tomorrow|saturday|kick-?off|face|host)\b/);
    }
  });
});


describe("every superlative is bounded and every claim counted", () => {
  test("the floor post names the pool it is the best of", () => {
    expect(floorPost({ findings: survey().findings, pool: POOL, site: SITE }).text)
      .toContain("548 teams here");
  });

  test("the venue post names the pool too", () => {
    expect(venuePost({ findings: survey().findings, pool: POOL, site: SITE }).text)
      .toContain("548 teams here");
  });

  test("a pool with no team count still bounds the claim to the site", () => {
    // The count is what makes the bound vivid, but the bound itself must survive
    // without it — an unbounded superlative is a claim about leagues we do not hold.
    const text = floorPost({ findings: survey().findings, pool: {}, site: SITE }).text;
    expect(text).toContain("every team here");
    expect(text).not.toMatch(/\b(europe|the world|anywhere|football)\b/i);
  });

  test("no post claims a record beyond the data we hold", () => {
    for (const c of all()) {
      expect(c.text).not.toMatch(/\bin (europe|the world|football)\b/i);
    }
  });

  test.each([
    ["floor", floorPost], ["ceiling", ceilingPost], ["perfect", perfectPost],
    ["futility", futilityPost], ["leaky", leakyPost],
  ])("%s states how many games it is drawn from", (key, fn) => {
    const c = fn({ findings: survey().findings, pool: POOL, site: SITE });
    expect(c.text).toMatch(/\b(18|20)\b/);
  });
});


describe("the sentences read like English", () => {
  // THE digest.js BUG, GUARDED HERE TOO. Four ternaries spliced into one template produced
  // "Every probabilities one is derived", which shipped because nothing read the output.
  test("no doubled words", () => {
    for (const c of all()) {
      expect(c.text).not.toMatch(/\b(\w+)\s+\1\b/i);
    }
  });

  test("no orphaned punctuation or double spaces", () => {
    for (const c of all()) {
      expect(c.text).not.toMatch(/\s[.,]/);
      expect(c.text).not.toMatch(/ {2}/);
      expect(c.text).not.toMatch(/\.\./);
    }
  });

  test("no undefined, null or NaN leaks into a post", () => {
    for (const c of all()) {
      expect(c.text).not.toMatch(/undefined|null|NaN/);
    }
  });

  test("every post ends with the site, on its own line", () => {
    for (const c of all()) {
      expect(c.text).toMatch(/\n\nthecornermodel\.com/);
    }
  });

  test("the floor post pre-empts the misreading it always gets", () => {
    // "Their worst return is 5" is read as an average by about half of everyone.
    expect(floorPost({ findings: survey().findings, pool: POOL, site: SITE }).text)
      .toContain("Not their average");
  });
});


describe("they fit in a post", () => {
  test.each(BUILDERS)("%s is within X's weighted limit", (key, fn) => {
    const c = fn({ findings: survey().findings, pool: POOL, site: SITE });
    expect(xWeight(c.text)).toBeLessThanOrEqual(X_MAX_WEIGHT);
  });

  test("a very long club name still produces a legal post", () => {
    const s = survey({ findings: { highest_floor: {
      team: "Borussia Mönchengladbach Fohlenelf Reserves II",
      country: "Germany", league: "2. Bundesliga",
      games: 20, floor: 6, ceiling: 15, for_avg: 9.1, against_avg: 3.0 } } });
    const c = floorPost({ findings: s.findings, pool: POOL, site: SITE });
    expect(xWeight(c.text)).toBeLessThanOrEqual(X_MAX_WEIGHT);
    expect(c.text).toContain("Borussia");
  });
});


describe("a thin survey produces fewer posts, not softer ones", () => {
  test("an empty survey produces nothing at all", () => {
    expect(oddityPosts({ survey: { pool: {}, findings: {} }, site: SITE, now: NOW }))
      .toEqual([]);
  });

  test("no survey at all is handled rather than thrown on", () => {
    expect(oddityPosts({ site: SITE, now: NOW })).toEqual([]);
  });

  test("one missing finding costs one candidate and nothing else", () => {
    const s = survey({ findings: { punching_up: null } });
    const keys = oddityPosts({ survey: s, site: SITE, now: NOW, limit: 99 })
      .map((c) => c.key);
    expect(keys).not.toContain("punching");
    expect(keys).toHaveLength(BUILDERS.length - 1);
  });

  test("a small rout is dropped rather than announced as a record", () => {
    // A margin of 4 is a good night, not a siege, and a post calling it one is the
    // loosened-bar failure in a new costume.
    const s = survey({ findings: { biggest_rout: {
      team: "Someone", country: "England", opponent: "Other",
      date: "2026-09-14T15:00:00Z", corners_for: 7, corners_against: 3, margin: 4 } } });
    expect(routPost({ findings: s.findings, pool: POOL, site: SITE })).toBeNull();
  });

  test("a finding missing its key number is dropped, not printed as a blank", () => {
    const s = survey({ findings: { leakiest: {
      team: "Nobody", country: "England", games: 18, against_avg: null } } });
    expect(leakyPost({ findings: s.findings, pool: POOL, site: SITE })).toBeNull();
  });

  test("a venue gap missing one side is dropped", () => {
    const s = survey({ findings: { widest_venue_gap: {
      team: "Lopsided", country: "Norway", games: 14,
      home_avg: 9.0, away_avg: null, gap: 9.0, stronger: "home" } } });
    expect(venuePost({ findings: s.findings, pool: POOL, site: SITE })).toBeNull();
  });
});


describe("the lead moves", () => {
  // "Generic, no variance" arriving a month later would be the same complaint, and a
  // static order is how it would get there.
  test("a different candidate leads on consecutive days", () => {
    const a = oddityPosts({ survey: survey(), site: SITE, now: new Date("2026-10-16T09:00:00Z") });
    const b = oddityPosts({ survey: survey(), site: SITE, now: new Date("2026-10-17T09:00:00Z") });
    expect(a[0].key).not.toBe(b[0].key);
  });

  test("the same day twice gives the same order", () => {
    const a = oddityPosts({ survey: survey(), site: SITE, now: new Date("2026-10-16T06:00:00Z") });
    const b = oddityPosts({ survey: survey(), site: SITE, now: new Date("2026-10-16T21:00:00Z") });
    expect(a.map((c) => c.key)).toEqual(b.map((c) => c.key));
  });

  test("every candidate gets the lead before any repeats it", () => {
    const n = BUILDERS.length;
    const leads = new Set();
    for (let i = 0; i < n; i += 1) {
      const day = new Date(Date.UTC(2026, 9, 16 + i, 9));
      leads.add(oddityPosts({ survey: survey(), site: SITE, now: day })[0].key);
    }
    expect(leads.size).toBe(n);
  });

  test("rotate keeps every element and only moves the start", () => {
    expect(rotate([1, 2, 3, 4], 1)).toEqual([2, 3, 4, 1]);
    expect(rotate([1, 2, 3, 4], 4)).toEqual([1, 2, 3, 4]);
    expect(rotate([1, 2, 3, 4], -1)).toEqual([4, 1, 2, 3]);
    expect(rotate([1], 7)).toEqual([1]);
    expect(rotate([], 3)).toEqual([]);
  });

  test("an unreadable date does not throw the rotation off a cliff", () => {
    expect(dayIndex(new Date("nonsense"))).toBe(0);
  });
});


describe("the small helpers", () => {
  test("who places a club by country, because most of them are unknown", () => {
    expect(who({ team: "Vejle", country: "Denmark" })).toBe("Vejle (Denmark)");
  });

  test("who survives a missing country rather than printing a bare bracket", () => {
    expect(who({ team: "Vejle" })).toBe("Vejle");
    expect(who({})).toBe("");
  });

  test("when renders a date a reader can picture", () => {
    expect(when("2026-09-14T15:00:00Z")).toBe("14 September");
  });

  test("when returns empty rather than Invalid Date", () => {
    expect(when("not a date")).toBe("");
    expect(when(null)).toBe("");
  });
});


describe("the posts say what they mean", () => {
  test("the punching-up post names both clubs and both leagues", () => {
    const text = punchingPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("Harrogate");
    expect(text).toContain("Atalanta");
    expect(text).toContain("League Two");
    expect(text).toContain("Serie A");
  });

  test("the leagues post gives both ends and the gap", () => {
    const text = leaguesPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("11.8");
    expect(text).toContain("8.6");
    expect(text).toContain("3.2");
  });

  test("a team stronger away is described that way round", () => {
    const s = survey({ findings: { widest_venue_gap: {
      team: "Traveller", country: "Norway", games: 20,
      home_avg: 3.1, away_avg: 8.4, gap: 5.3, stronger: "away",
      for_avg: 5.8, against_avg: 4.4 } } });
    const text = venuePost({ findings: s.findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("the wrong way round");
  });

  test("the rout post leads with the margin, not the site", () => {
    const text = routPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text.startsWith("Blackburn")).toBe(true);
    expect(text).toContain("16 corners to 1");
  });

  test("the futility post converts the averages into whole corners", () => {
    const text = futilityPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    // 7.9 x 18 = 142.2, 0.6 x 18 = 10.8
    expect(text).toContain("142 corners");
    expect(text).toContain("11 goals");
  });

  test("the wildest post names both sides of the match", () => {
    const text = wildestPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("27 corners");
    expect(text).toContain("Boca Juniors");
    expect(text).toContain("Racing");
  });

  test("the haul post is not the same game as the rout", () => {
    // The backend drops the collision; this checks the posts stay distinguishable when
    // both survive.
    const rout = routPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    const haul = haulPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(rout).not.toBe(haul);
    expect(haul).toContain("Vejle");
  });

  test("the ceiling post says how long the drought has run", () => {
    const text = ceilingPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("Not once in 18");
  });

  test("the perfect post gives the run and both averages", () => {
    const text = perfectPost({ findings: survey().findings, pool: POOL, site: SITE }).text;
    expect(text).toContain("All 20");
    expect(text).toContain("7.2");
    expect(text).toContain("3.4");
  });
});
