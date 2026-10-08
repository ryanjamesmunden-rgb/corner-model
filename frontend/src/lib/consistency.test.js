import {
  RUNGS, consistencyHeadline, consistencyLabel, consistencyRow, consistencyRows,
  floorOf, hitsAt, ladderFor, valuesFor, SUBJECTS, gameBars, lineWindow, defaultLine,
  windowsFor, WINDOWS, clampWindow, MIN_WINDOW, isPriorSeason, splitSeasons, thisSeasonOnly, seasonNote,
} from "./consistency";

/** A game row exactly as the fixture endpoint's `recent` emits it. */
const g = (won, conceded, extra = {}) => ({
  won, conceded, total: won + conceded, date: "2026-09-01T15:00:00Z",
  // shots_for is on every real row; 14 is an ordinary count. A game row WITHOUT it is a
  // separate case with its own test, because a missing shot count is stored as 0 and must
  // not read as "took none".
  shots_for: 14,
  opponent: "X", home: true, ...extra,
});

const WON = SUBJECTS.find((s) => s.key === "won");

describe("the floor", () => {
  test("is the highest line every game cleared", () => {
    expect(floorOf([6, 4, 7, 5])).toBe(4);
  });

  test("of zero is a real result, not an absence", () => {
    // A side kept to nothing once HAS a floor of 0. Returning null for it would make a
    // genuine finding indistinguishable from having no games at all.
    expect(floorOf([0, 5, 6])).toBe(0);
  });

  test("with no games there is none", () => {
    expect(floorOf([])).toBeNull();
  });
});

describe("reading values off the games", () => {
  test("it takes the subject's own column", () => {
    const games = [g(6, 3), g(4, 8)];
    expect(valuesFor(games, (m) => m.won)).toEqual([6, 4]);
    expect(valuesFor(games, (m) => m.conceded)).toEqual([3, 8]);
    expect(valuesFor(games, (m) => m.total)).toEqual([9, 12]);
  });

  test("a game missing that number is dropped, not counted as zero", () => {
    // A zero would drag the floor to 0 and silently destroy the claim, which is the
    // strongest thing on the panel.
    expect(valuesFor([g(6, 3), { won: null, conceded: 4 }], (m) => m.won)).toEqual([6]);
    expect(valuesFor([g(6, 3), {}], (m) => m.won)).toEqual([6]);
  });
});

describe("hit counts", () => {
  test("carry the denominator with them", () => {
    expect(hitsAt([6, 4, 7, 5], 5)).toEqual({ line: 5, hits: 3, n: 4, pct: 75 });
  });

  test("count a game landing exactly on the line as a hit", () => {
    // These are `line+` claims — 5 clears 5+. An over on a whole number is not a push.
    expect(hitsAt([5], 5).hits).toBe(1);
  });

  test("no games is 0 of 0 rather than a division by zero", () => {
    expect(hitsAt([], 5)).toEqual({ line: 5, hits: 0, n: 0, pct: 0 });
  });
});

describe("the ladder", () => {
  test("opens on the floor, so the first rung always holds", () => {
    const l = ladderFor([6, 4, 7, 5]);
    expect(l[0]).toMatchObject({ line: 4, hits: 4, n: 4 });
    expect(l[0].pct).toBe(100);
  });

  test("climbs to show where reliability runs out", () => {
    const l = ladderFor([6, 4, 7, 5]);
    expect(l.map((x) => [x.line, x.hits])).toEqual([[4, 4], [5, 3], [6, 2], [7, 1]]);
  });

  test("it stops rather than printing rungs nothing reached", () => {
    // 8+ is 0/4 here and a rung of zeroes is noise on a strip meant to be glanced at.
    expect(ladderFor([6, 4, 7, 5]).some((x) => x.hits === 0)).toBe(false);
  });

  test("a floor of zero opens at one instead", () => {
    // "0+ every game" is true of every team that has ever played.
    expect(ladderFor([0, 4, 5])[0].line).toBe(1);
  });

  test("it is capped so the strip stays one row", () => {
    expect(ladderFor([3, 14]).length).toBeLessThanOrEqual(RUNGS + 1);
  });

  test("a single flat value still gives one rung", () => {
    expect(ladderFor([5, 5, 5]).map((x) => x.line)).toEqual([5, 6, 7, 8].slice(0, 1));
  });

  test("no games is no ladder", () => {
    expect(ladderFor([])).toEqual([]);
  });
});

describe("one subject's row", () => {
  test("it reports the claim, the spread and the average together", () => {
    const row = consistencyRow([g(6, 3), g(4, 5), g(7, 4)], WON);
    expect(row).toMatchObject({ key: "won", every: 4, low: 4, high: 7, range: 3, n: 3 });
    expect(row.avg).toBe(5.7);
  });

  test("the range is there because a floor and a mean do not separate these two", () => {
    // Same floor, same average, completely different bet.
    const steady = consistencyRow([g(4, 0), g(5, 0), g(4, 0), g(5, 0)], WON);
    const wild = consistencyRow([g(4, 0), g(9, 0), g(4, 0), g(1, 0)], WON);
    expect(steady.range).toBeLessThan(wild.range);
  });

  test("a floor of zero carries no claim", () => {
    const row = consistencyRow([g(0, 4), g(6, 4)], WON);
    expect(row.every).toBeNull();
    expect(row.low).toBe(0);
  });

  test("no games is no row at all", () => {
    expect(consistencyRow([], WON)).toBeNull();
    expect(consistencyRows([])).toEqual([]);
  });

  test("every subject comes through for a normal set of games", () => {
    expect(consistencyRows([g(6, 3), g(5, 4)]).map((r) => r.key))
      .toEqual(["won", "conceded", "total", "shots"]);
  });

  test("a subject with nothing reported is left out rather than drawn empty", () => {
    // Shots are the case: a fixture set the provider never covered should produce three
    // rows, not four with one of them blank.
    const noShots = [{ won: 6, conceded: 3, total: 9 }, { won: 5, conceded: 4, total: 9 }];
    expect(consistencyRows(noShots).map((r) => r.key))
      .toEqual(["won", "conceded", "total"]);
  });
});

describe("the sentence", () => {
  test("names what held and where it stopped", () => {
    const row = consistencyRow([g(6, 0), g(4, 0), g(7, 0), g(5, 0)], WON);
    expect(consistencyLabel(row)).toBe("4+ every game · 5+ in 3 of 4");
  });

  test("says only what held when the next rung is empty", () => {
    const row = consistencyRow([g(5, 0), g(5, 0)], WON);
    expect(consistencyLabel(row)).toBe("5+ every game");
  });

  test("a floor of zero is stated as a range instead of a claim", () => {
    const row = consistencyRow([g(0, 0), g(7, 0)], WON);
    expect(consistencyLabel(row)).toBe("as low as 0 · up to 7");
  });

  test("nothing at all is an empty string, not 'undefined+'", () => {
    expect(consistencyLabel(null)).toBe("");
  });
});

describe("the panel header", () => {
  test("gives both floors, which is what the section is for", () => {
    const rows = consistencyRows([g(6, 5), g(5, 6), g(7, 5)]);
    expect(consistencyHeadline(rows)).toBe("wins 5+ every game · concedes 5+ every game");
  });

  test("names only the side that held one", () => {
    const rows = consistencyRows([g(6, 0), g(5, 4)]);
    expect(consistencyHeadline(rows)).toBe("wins 5+ every game");
  });

  test("says plainly when nothing held", () => {
    // Better than silence: "no line held in every game" is itself a finding about a side.
    const rows = consistencyRows([g(0, 0), g(9, 9)]);
    expect(consistencyHeadline(rows)).toBe("no line held in every game");
  });

  test("and nothing at all when there are no games", () => {
    expect(consistencyHeadline([])).toBe("");
  });
});


// THE CHART. Same grammar as the probability chart at the top of the page — vertical bars,
// a line picker, the split in words — over the opposite content: those bars are the model's
// forecast, these are the games that happened.
describe("the bars", () => {
  const games = [g(7, 3), g(4, 6), g(6, 5)];   // newest first, as the endpoint sends them

  test("run oldest first, so the chart reads left to right like the one above it", () => {
    expect(gameBars(games, (m) => m.won).map((b) => b.value)).toEqual([6, 4, 7]);
  });

  test("each bar carries the game it came from", () => {
    const b = gameBars([g(7, 3, { opponent: "Arsenal", home: false })], (m) => m.won)[0];
    expect(b).toMatchObject({ value: 7, opponent: "Arsenal", home: false });
  });

  test("an uncovered game is dropped, not drawn as an empty column", () => {
    // A phantom zero bar reads as a game they were kept to nothing in.
    expect(gameBars([g(7, 3), { won: null }], (m) => m.won).map((b) => b.value)).toEqual([7]);
  });

  test("every bar gets its own key even when two share a date", () => {
    const bars = gameBars([g(5, 1), g(5, 1)], (m) => m.won);
    expect(new Set(bars.map((b) => b.key)).size).toBe(2);
  });

  test("no games is no bars", () => {
    expect(gameBars([], (m) => m.won)).toEqual([]);
    expect(gameBars(undefined, (m) => m.won)).toEqual([]);
  });
});

describe("the line picker", () => {
  test("opens on the line they never went below", () => {
    expect(defaultLine([6, 4, 7, 5])).toBe(4);
  });

  test("a floor of zero opens at one, not at zero", () => {
    expect(defaultLine([0, 6])).toBe(1);
  });

  test("it offers a window around the floor, not every count", () => {
    // Centred on the floor because the floor is the claim the panel is built around.
    expect(lineWindow([6, 4, 7, 5])).toEqual([3, 4, 5, 6, 7]);
  });

  test("it never offers a line nothing in the window reached", () => {
    expect(lineWindow([4, 5])).toEqual([3, 4, 5]);
  });

  test("it never offers zero", () => {
    expect(lineWindow([0, 1, 2])).toEqual([1, 2]);
  });

  test("a flat set still gives something to pick", () => {
    expect(lineWindow([5, 5, 5])).toEqual([4, 5]);
  });

  test("no games is no picker and no default", () => {
    expect(lineWindow([])).toEqual([]);
    expect(defaultLine([])).toBeNull();
  });
});


describe("the subject vocabulary", () => {
  test("every subject carries the three words the chart needs", () => {
    // A missing `noun` renders "4+ undefined" in the caption, and a missing `short`
    // renders an empty switcher button — both compile and ship.
    SUBJECTS.forEach((s) => {
      expect(typeof s.label).toBe("string");
      expect(s.label.length).toBeGreaterThan(0);
      expect(typeof s.short).toBe("string");
      expect(s.short.length).toBeGreaterThan(0);
      expect(typeof s.noun).toBe("string");
      expect(s.noun.length).toBeGreaterThan(0);
      expect(typeof s.pick).toBe("function");
    });
  });

  test("the short labels fit a phone switcher", () => {
    SUBJECTS.forEach((s) => expect(s.short.length).toBeLessThanOrEqual(9));
  });

  test("each picks its own column off a game row", () => {
    // KEYED RATHER THAN POSITIONAL. The old version compared a bare array, so adding a
    // subject failed the test for the wrong reason — it said nothing about whether the
    // new one read the right column, only that the list had grown.
    const row = { ...g(6, 3), gf: 2, ga: 1 };
    const picked = Object.fromEntries(SUBJECTS.map((s) => [s.key, s.pick(row)]));
    expect(picked).toEqual({
      won: 6, conceded: 3, total: 9, shots: 14, scored: 2, goals_against: 1,
    });
  });
});


describe("shots, where a zero is not a zero", () => {
  const SHOTS = SUBJECTS.find((s) => s.key === "shots");

  test("a real shot count comes through", () => {
    expect(valuesFor([g(5, 4, { shots_for: 17 })], SHOTS.pick)).toEqual([17]);
  });

  test("a zero is treated as NOT REPORTED and dropped", () => {
    // THE WHOLE REASON THIS SUBJECT NEEDS ITS OWN PICK. sync_real coerces a missing shot
    // count to 0 because the live lambda consumes it and must not see null — so an
    // uncovered fixture and a shotless one are the same value in the database. Drawn as a
    // real zero it puts a floor of 0 on the panel and drags the claim down, and a side
    // taking literally no shots in a match essentially does not happen.
    expect(valuesFor([g(5, 4, { shots_for: 0 }), g(5, 4, { shots_for: 12 })], SHOTS.pick))
      .toEqual([12]);
  });

  test("so does a missing one", () => {
    expect(valuesFor([{ won: 5, conceded: 4 }], SHOTS.pick)).toEqual([]);
  });

  test("the floor is taken over the games that WERE reported", () => {
    const games = [g(5, 4, { shots_for: 0 }), g(5, 4, { shots_for: 14 }),
                   g(5, 4, { shots_for: 11 })];
    const row = consistencyRow(games, SHOTS);
    expect(row.n).toBe(2);
    expect(row.every).toBe(11);
  });
});


describe("which windows a split can honestly offer", () => {
  test("a full history offers all of them", () => {
    expect(windowsFor(new Array(20).fill(g(5, 4)))).toEqual([3, 5, 10, 20]);
  });

  test("fourteen games does not offer 'Last 20'", () => {
    // A tab reading "Last 20" over fourteen games is a label that lies.
    expect(windowsFor(new Array(14).fill(g(5, 4)))).toEqual([3, 5, 10]);
  });

  test("a thin venue split offers only what it has", () => {
    expect(windowsFor(new Array(6).fill(g(5, 4)))).toEqual([3, 5]);
  });

  test("it always offers something, even on almost nothing", () => {
    // Returning [] would leave the panel with no window selected and nothing drawn.
    expect(windowsFor([g(5, 4)])).toEqual([3]);
    expect(windowsFor([])).toEqual([3]);
  });
});


describe("each subject's share-image sentence", () => {
  test("every subject owns one", () => {
    // A missing claim renders the fallback, which is true but says less than it could.
    SUBJECTS.forEach((s) => {
      expect(typeof s.claim).toBe("function");
      expect(s.claim(5)).toContain("5");
    });
  });

  test("a conceded record is not described as 'cleared'", () => {
    // THE CASE THAT KILLED THE verb + noun TEMPLATE. A side does not clear corners it
    // shipped, and "cleared 5+ conceded" says the opposite of what the record is.
    const conceded = SUBJECTS.find((s) => s.key === "conceded");
    expect(conceded.claim(5)).toBe("conceded 5+ corners");
    expect(conceded.claim(5)).not.toContain("cleared");
  });

  test("and a won record is", () => {
    expect(SUBJECTS.find((s) => s.key === "won").claim(5)).toBe("cleared 5+ corners");
  });

  test("a match total reads as the match, not as one side", () => {
    expect(SUBJECTS.find((s) => s.key === "total").claim(10)).toBe("10+ corners in the match");
  });

  test("shots read as shots", () => {
    expect(SUBJECTS.find((s) => s.key === "shots").claim(12)).toBe("had 12+ shots");
  });
});


// THE NUMBER THAT PROMPTED THIS: "Plymouth won 5+ in 7 of 10" where two of the ten were last
// April. This season it is 5 of 7 — a different claim about a team with a new manager, a new
// formation and a third of the squad turned over, with a three-month gap in the middle.
describe("where last season starts", () => {
  const WON = SUBJECTS.find((s) => s.key === "won");
  /** Plymouth's ten, newest first: five clear 5+ this season, two more last season. */
  const PLYMOUTH = [
    g(6, 3, { season: 2026 }), g(7, 4, { season: 2026 }), g(2, 5, { season: 2026 }),
    g(5, 3, { season: 2026 }), g(6, 4, { season: 2026 }), g(3, 6, { season: 2026 }),
    g(5, 2, { season: 2026 }),
    g(8, 3, { season: 2025 }), g(6, 5, { season: 2025 }), g(1, 7, { season: 2025 }),
  ];

  test("a game from an earlier season is flagged", () => {
    expect(isPriorSeason({ season: 2025 }, 2026)).toBe(true);
    expect(isPriorSeason({ season: 2026 }, 2026)).toBe(false);
  });

  test("an unknown season counts as current, not as stale", () => {
    // Rows synced before the stamp shipped carry none. Flagging all of them would put a
    // "last season" warning on the whole board for a week after a deploy.
    expect(isPriorSeason({}, 2026)).toBe(false);
    expect(isPriorSeason({ season: null }, 2026)).toBe(false);
  });

  test("and an unknown CURRENT season flags nothing", () => {
    expect(isPriorSeason({ season: 2025 }, null)).toBe(false);
    expect(isPriorSeason({ season: 2025 }, undefined)).toBe(false);
  });

  test("the window splits at the boundary and keeps its order", () => {
    const { current, prior, crosses } = splitSeasons(PLYMOUTH, 2026);
    expect(current).toHaveLength(7);
    expect(prior).toHaveLength(3);
    expect(crosses).toBe(true);
    expect(current[0].won).toBe(6);
  });

  test("a window inside one season does not cross", () => {
    expect(splitSeasons(PLYMOUTH.slice(0, 5), 2026).crosses).toBe(false);
    expect(splitSeasons([], 2026).crosses).toBe(false);
  });

  test("THE PLYMOUTH CASE: 7 of 10 overall is 5 of 7 this season", () => {
    expect(hitsAt(valuesFor(PLYMOUTH, WON.pick), 5)).toMatchObject({ hits: 7, n: 10 });
    expect(thisSeasonOnly(PLYMOUTH, WON, 5, 2026)).toMatchObject({ hits: 5, n: 7, games: 7 });
  });

  test("this-season-only is absent when the window does not cross", () => {
    // Printing the same number twice invites the reader to look for a difference.
    expect(thisSeasonOnly(PLYMOUTH.slice(0, 5), WON, 5, 2026)).toBeNull();
  });

  test("and absent when nothing this season is on file", () => {
    const allOld = [g(6, 3, { season: 2025 }), g(7, 3, { season: 2025 })];
    expect(thisSeasonOnly(allOld, WON, 5, 2026)).toBeNull();
  });

  test("the note names the gap and why it matters", () => {
    // "2 from last season" is a fact; the reason it matters is the half a reader acts on.
    const note = seasonNote(PLYMOUTH, 2026);
    expect(note).toBe("3 of these are from last season"
      + " — squad and formation may have changed since");
  });

  test("it is singular for one", () => {
    expect(seasonNote([g(6, 3, { season: 2026 }), g(6, 3, { season: 2025 })], 2026))
      .toContain("1 of these is from last season");
  });

  test("and silent when the window is all current", () => {
    expect(seasonNote(PLYMOUTH.slice(0, 5), 2026)).toBe("");
    expect(seasonNote([], 2026)).toBe("");
  });
});


describe("the window a card actually uses", () => {
  test("a chosen window inside the pool is kept", () => {
    expect(clampWindow(5, 10)).toBe(5);
  });

  test("one larger than the pool SHRINKS to the pool", () => {
    // THE CASE THAT MATTERS ON A TEAM CARD. The scroller sits on the ladder, which counts
    // venue games; the chart under it can be on a split holding fewer. Returning 10 there
    // draws four bars under a label reading "Last 10".
    expect(clampWindow(10, 4)).toBe(4);
  });

  test("it defaults to ten, or the pool if that is smaller", () => {
    expect(clampWindow(undefined, 20)).toBe(10);
    expect(clampWindow(undefined, 6)).toBe(6);
    expect(clampWindow(null, 6)).toBe(6);
  });

  test("a junk value falls back rather than producing NaN", () => {
    // NaN as a slice length returns an empty array, which renders as a card with no chart
    // and no error.
    expect(clampWindow("nonsense", 8)).toBe(8);
  });

  test("an empty pool still returns a usable number", () => {
    expect(clampWindow(10, 0)).toBeGreaterThanOrEqual(1);
  });

  test("the floor is three, because two results are not a window", () => {
    expect(MIN_WINDOW).toBe(3);
  });
});

describe("goals, scored and conceded", () => {
  // "Have they scored in 8 of their last 10" had to be read off the recent-games table a
  // row at a time. The panel could always answer it — goals were simply never offered.
  const g = (gf, ga) => ({ gf, ga, won: 5, conceded: 4, total: 9 });
  const sub = (key) => SUBJECTS.find((s) => s.key === key);

  test("a line of 1 is phrased the way people say it", () => {
    // "scored 1+ goals in 8 of 10" is the same fact written badly.
    expect(sub("scored").claim(1)).toBe("scored");
    expect(sub("goals_against").claim(1)).toBe("conceded");
  });

  test("and the higher rungs keep the ladder's wording", () => {
    expect(sub("scored").claim(2)).toBe("scored 2+ goals");
    expect(sub("goals_against").claim(3)).toBe("conceded 3+ goals");
  });

  test("a goalless game is a real zero, not a dropped game", () => {
    // Unlike shots, where 0 means "not reported". A goalless game is the commonest result
    // in football and dropping it would delete the games these records are about.
    const games = [g(0, 1), g(2, 0), g(1, 1)];
    expect(valuesFor(games, sub("scored").pick)).toEqual([0, 2, 1]);
  });

  test("an unsynced score is dropped, not read as nil", () => {
    const games = [g(1, 0), g(null, null), g(2, 1)];
    expect(valuesFor(games, sub("scored").pick)).toEqual([1, 2]);
    expect(valuesFor(games, sub("goals_against").pick)).toEqual([0, 1]);
  });

  test("the default line lands on 1, which is the question being asked", () => {
    // A side with any goalless game has a floor of 0, and "0+ goals" is true of every
    // game ever played.
    expect(defaultLine(valuesFor([g(0, 0), g(2, 1), g(1, 0)], sub("scored").pick))).toBe(1);
  });

  test("scored and conceded do not read the same column", () => {
    const games = [g(3, 0), g(0, 2)];
    expect(valuesFor(games, sub("scored").pick)).toEqual([3, 0]);
    expect(valuesFor(games, sub("goals_against").pick)).toEqual([0, 2]);
  });

  test("so 'scored in 2 of 3' comes out of hitsAt at line 1", () => {
    const vals = valuesFor([g(1, 0), g(0, 1), g(2, 2)], sub("scored").pick);
    expect(hitsAt(vals, 1)).toMatchObject({ hits: 2, n: 3 });
  });
});
