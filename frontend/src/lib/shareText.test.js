/**
 * These builders are the contract between the share buttons and the scheduled draft
 * job. The failure they exist to prevent is drift — the automated post looking subtly
 * unlike the one a person clicked out an hour earlier — so what's pinned is the shape
 * of a line and the one thing a row limit must never break: the "+N more" count has to
 * describe the list it is actually attached to.
 */
import { streakShare, fixtureShare, bestTeamsShare, streakResultShare,
         fixtureStreakShare, telegramPick, wonLadder, openGameCase, postHeader,
         pickGame, gameShare, weekendCard, picksReview, moreVia,
         postDate, postTime, pickLabel } from "./shareText";

const NORWAY = "\u{1F1F3}\u{1F1F4}";
const soon = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(12, 0, 0, 0);
  return d.toISOString();
};

const streakRow = (name, league_id, line, run = 9) => ({
  name, league_id, line, line_label: `${line}+`, hits: 5, window: 5,
  streak: { length: run, status: "active" },
  next_fixture: { is_home: true, opponent: "Rosenborg", date: soon() },
});
const rows = ["A", "B", "C", "D", "E", "F", "G"].map((n, i) => streakRow(n, "nor-el", 5 + (i % 3), 9 - i));
const build = streakShare({ rows, subject: "team", side: "overall" });

describe("a streak line", () => {
  test("opens with the country flag instead of a bullet", () => {
    expect(build(1)).toContain(`${NORWAY} A`);
    expect(build(1)).not.toContain("• A");
  });

  test("carries the team, the line and the run — and nothing else", () => {
    expect(build(1).split("\n")[1]).toBe(`${NORWAY} A 5+ — 9 in a row`);
  });

  test("publishes the team's OWN run, not the filter's window", () => {
    // The bug this replaces: every row ended "(5/5)" because that is what the filter
    // asked for, so a nine-game run and one that scraped the minimum read identically
    // and the best rows on the board were the ones the post undersold.
    const out = build(3);
    expect(out).toContain("9 in a row");
    expect(out).toContain("8 in a row");
    expect(out).toContain("7 in a row");
    expect(out).not.toContain("5/5");
  });

  test("drops the opponent and the kick-off — neither is a reason to click", () => {
    const out = build(7);
    expect(out).not.toContain("Rosenborg");
    expect(out).not.toContain("Tomorrow");
    expect(out).not.toContain("All times");
  });

  test("an under is labelled as one rather than read as an over", () => {
    const under = streakShare({
      rows: [{ name: "A", league_id: "nor-el", line_label: "under 9", streak: { length: 6 } }],
      subject: "team", side: "overall",
    })(1);
    expect(under).toContain(`${NORWAY} A under 9 — 6 in a row`);
  });

  test("a missing line is left out rather than guessed at", () => {
    // Labelling an under as "9+" would be a public, permanent lie about the bet, so a
    // row with no label from the API says less instead of saying something wrong.
    const out = streakShare({
      rows: [{ name: "A", league_id: "nor-el", line: 9, streak: { length: 6 } }],
      subject: "team", side: "overall",
    })(1);
    expect(out).toContain(`${NORWAY} A — 6 in a row`);
    expect(out).not.toMatch(/9\+/);
  });

  test("a run of one is not called a run", () => {
    const out = streakShare({
      rows: [{ name: "A", league_id: "nor-el", line_label: "5+", streak: { length: 1 } }],
      subject: "team", side: "overall",
    })(1);
    expect(out).toContain(`${NORWAY} A 5+`);
    expect(out).not.toContain("in a row");
  });

  test("the heading names the subject and the side, and nothing more", () => {
    expect(build(1).split("\n")[0]).toBe("Team corner streaks running right now:");
    expect(streakShare({ rows, subject: "match", side: "away" })(1).split("\n")[0])
      .toBe("Match corner streaks running right now in away games:");
  });

  test("is shorter than what it replaced, which is the point", () => {
    // The old row was "🇳🇴 A vs Rosenborg (5/5) · Tomorrow 12:00" plus a times footer.
    // Room for more streaks is the whole reason for the change, so it is worth pinning.
    expect(build(6).length).toBeLessThan(200);
  });
});

describe("the row limit", () => {
  test("+N more always describes the list above it", () => {
    // The whole reason these are functions of a limit rather than one string that gets
    // truncated: a 4-row post and a 6-row one must not claim the same remainder.
    expect(build(4)).toContain("+3 more on the site");
    expect(build(6)).toContain("+1 more on the site");
    expect(build(7)).not.toContain("more on the site");
  });

  test("asking for more rows than exist is not an error", () => {
    expect(build(50)).not.toContain("more on the site");
    expect(build(50).split("\n").filter((l) => l.includes("in a row"))).toHaveLength(7);
  });
});

describe("an empty board shares nothing at all", () => {
  test.each([
    ["streaks", streakShare({ rows: [], subject: "team", side: "overall" })],
    ["fixtures", fixtureShare({ fixtures: [], days: "3" })],
    ["best teams", bestTeamsShare({ rows: [], side: "overall", windowLabel: "Season" })],
  ])("%s", (_label, b) => {
    // "" hides the share buttons; a heading with no rows under it would be posted.
    expect(b(4)).toBe("");
  });
});

describe("the other two boards", () => {
  const fixtures = [
    { league_id: "nor-el", home: "Bodø/Glimt", away: "Rosenborg", lambda_total: 11.4, date: soon(),
      angles: [{ team: "Bodø/Glimt", label: "5+ corners" }] },
    { league_id: "ita-sa", home: "Roma", away: "Lazio", lambda_total: 10.2, date: soon(), angles: [] },
  ];

  test("a fixture line carries both teams, the projection and the kick-off", () => {
    const out = fixtureShare({ fixtures, days: "3" })(2);
    expect(out).toContain(`${NORWAY} Bodø/Glimt v Rosenborg (λ 11.4) — Bodø/Glimt 5+ corners`);
    expect(out).toContain("Tomorrow");
  });

  test("a fixture with no angle still shares, without a dangling dash", () => {
    expect(fixtureShare({ fixtures, days: "3" })(2)).toContain("Roma v Lazio (λ 10.2) ·");
  });

  test("best teams is flag, name, number — and nothing else on the line", () => {
    const out = bestTeamsShare({
      rows: [{ name: "Celtic", league_id: "sco-pl", won_avg: 8.123 }],
      side: "overall", windowLabel: "Season",
    })(4);
    const row = out.split("\n")[1];
    expect(row).toBe("\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F} Celtic 8.12");
    // The unit belongs in the heading once, not after every team — 18 characters a row
    // saying the same thing eight times is what pushed the post over the limit.
    expect(row).not.toMatch(/corners|game/);
    expect(out.split("\n")[0]).toContain("avg corners won");
  });

  test("all eight teams fit one X post in the compact format", () => {
    const rows = Array.from({ length: 8 }, (_, i) =>
      ({ name: `Team ${i}`, league_id: "eng-pl", won_avg: 7 - i * 0.1 }));
    const out = bestTeamsShare({ rows, side: "overall", windowLabel: "Season" })(8);
    expect(out.split("\n").filter((l) => /\d\.\d\d$/.test(l))).toHaveLength(8);
    expect(out).not.toContain("more on the site");
  });
});

describe("the results post", () => {
  const results = [
    { name: "A", league_id: "nor-el", opponent: "Rosenborg", is_home: true, result: "win", value: 8, line: 5 },
    { name: "B", league_id: "eng-pl", opponent: "Everton", is_home: false, result: "loss", value: 3, line: 6 },
    { name: "C", league_id: "ita-sa", opponent: "Lazio", is_home: true, result: "win", value: 7, line: 5 },
    { name: "D", league_id: "ger-bl", opponent: "Union Berlin", is_home: true, result: "pending", value: null, line: 6 },
  ];
  const build = streakResultShare({ results, landed: 2, settled: 3, voided: 1 });

  test("reports the corner count, never the line", () => {
    // The count is a fact anyone can look up; the line is the product.
    expect(build(4)).toContain("8 corners");
    expect(build(4)).not.toMatch(/\d\+/);
  });

  test("carries no money at all — no units, no ROI, no price", () => {
    const out = build(4);
    expect(out).not.toMatch(/[+-]?\d+(\.\d+)?\s*u\b/i);
    expect(out).not.toMatch(/ROI|profit|odds|@\s*\d/i);
  });

  test("shows the misses — a results post that only lists wins is an advert", () => {
    expect(build(4)).toContain("❌");
    expect(build(4)).toContain("✅");
  });

  test("counts voids out loud rather than dropping them", () => {
    // 2/3 plus a stake-back is a different week from 2/3, and hiding it inflates it.
    expect(build(4)).toContain("1 void");
  });

  test("a trimmed post still shows a miss, even when the wins come first", () => {
    // Trimming takes the first N rows; if those happen to all be wins, an honest "2/3"
    // headline sits over a picture of a clean sweep. The count would be true and the
    // impression false.
    const winsFirst = [
      { name: "W1", league_id: "nor-el", opponent: "O", is_home: true, result: "win", value: 8 },
      { name: "W2", league_id: "nor-el", opponent: "O", is_home: true, result: "win", value: 8 },
      { name: "W3", league_id: "nor-el", opponent: "O", is_home: true, result: "win", value: 8 },
      { name: "L1", league_id: "eng-pl", opponent: "O", is_home: true, result: "loss", value: 2 },
    ];
    const out = streakResultShare({ results: winsFirst, landed: 3, settled: 4 })(2);
    expect(out).toContain("❌");
    expect(out).toContain("L1");
  });

  test("games not yet played are left out, not counted as anything", () => {
    expect(build(4)).not.toContain("D vs");
  });

  test("nothing settled yet shares nothing", () => {
    const pendingOnly = streakResultShare({
      results: [{ name: "X", league_id: "nor-el", result: "pending", value: null }],
      landed: 0, settled: 0,
    });
    expect(pendingOnly(4)).toBe("");
  });
});

describe("sharing one fixture and what is running into it", () => {
  const fixture = { home_name: "Derby", away_name: "West Brom", league_id: "eng-ch", date: soon() };
  const streaks = [
    { team: "Derby", subject: "team", line: 6, line_label: "6+", direction: "over", run: 9 },
    { team: "Derby", subject: "match", line: 10, line_label: "10+", direction: "over", run: 6 },
    { team: "West Brom", subject: "team", line: 4, line_label: "under 4", direction: "under", run: 4 },
  ];
  const build = fixtureStreakShare({ fixture, streaks });

  test("names the fixture and lists the lines with their runs", () => {
    const out = build(3);
    expect(out).toContain("Derby v West Brom");
    expect(out).toContain("Derby 6+ corners — 9 in a row");
    expect(out).toContain("West Brom under 4 corners — 4 in a row");
  });

  test("a match total says whose GAMES, not whose corners", () => {
    // "Derby 10+" and "Derby games 10+" are different claims, and a reader betting the
    // first when we meant the second has been misled by one missing word.
    expect(build(3)).toContain("Derby games 10+ corners");
  });

  test("carries no price", () => {
    // Same rule as every other public post: the line goes out, the model's number does not.
    expect(build(3)).not.toMatch(/\d\.\d\d/);
  });

  test("trimming drops the weakest run, because rows arrive best-first", () => {
    const out = build(1);
    expect(out).toContain("9 in a row");
    expect(out).not.toContain("4 in a row");
    expect(out).toContain("+2 more on the site");
  });

  test("a fixture with nothing running into it shares nothing", () => {
    expect(fixtureStreakShare({ fixture, streaks: [] })(3)).toBe("");
  });
});

describe("the fire mark and game state", () => {
  const fixture = { home_name: "Derby", away_name: "West Brom", league_id: "eng-ch", date: soon() };
  const form = [
    { team: "Derby", venue: "home", label: "unbeaten in 7" },
    { team: "West Brom", venue: "away", label: "without a win in 5" },
  ];
  const row = (run) => ({ team: "Derby", subject: "team", line: 6, line_label: "6+",
                          direction: "over", run });

  test("a long run is marked, a merely good one is not", () => {
    // Marking everything would mark nothing — the floor is already 5, so this is the
    // tier that stands out from the rows beside it.
    expect(fixtureStreakShare({ fixture, streaks: [row(9)] })(3)).toContain("🔥");
    expect(fixtureStreakShare({ fixture, streaks: [row(6)] })(3)).not.toContain("🔥");
  });

  test("game state is spelled out at the venue each side is playing", () => {
    const out = fixtureStreakShare({ fixture, streaks: [row(9)], form })(3);
    expect(out).toContain("Derby unbeaten in 7 at home");
    expect(out).toContain("West Brom without a win in 5 away");
  });

  test("no form means no dangling section", () => {
    const out = fixtureStreakShare({ fixture, streaks: [row(9)], form: [] })(3);
    expect(out.trimEnd()).toBe(out.trimEnd());
    expect(out).not.toContain("at home");
  });

  test("the state lines sit AFTER the +N more, so trimming cannot orphan them", () => {
    const many = [row(9), row(8), row(7)];
    const out = fixtureStreakShare({ fixture, streaks: many, form })(1);
    expect(out.indexOf("more on the site")).toBeLessThan(out.indexOf("unbeaten in 7"));
  });
});

// A POSTED PICK, against the real thing.
//
// The reference is an actual channel post, reproduced from its own numbers. What is
// pinned is the shape a reader recognises and the two places a generated post could
// quietly lie: a verdict it has not earned, and a ladder rung that never landed.
describe("a pick posted to the channel", () => {
  // Operario-PR v CRB, Série B. Kick-off pinned to UTC noon so the date line is the same
  // date in every zone the suite might run in — the time itself is asserted separately.
  const fixture = {
    league_id: "bra-sb", league_name: "Série B",
    home_name: "Operario-PR", away_name: "CRB",
    date: "2026-09-10T12:00:00Z",
  };
  const market = { key: "home_over_5.5", group: "home", line: 5.5, label: "Over 5.5",
                   prob: 61.0, fair_odds: 1.64, book_odds: 1.8, ev: 9.8 };
  const card = {
    home: { team: "Operario-PR", venue: "home", opponent: "CRB",
            won: { games: 10, scope: "home", hits: { 4: 10, 5: 9, 6: 7 }, avg: 6.8 },
            opp_conceded: { games: 10, scope: "away", hits: { 4: 9, 5: 9, 6: 8 }, avg: 6.7 },
            opp_fh: { games: 10, scope: "away", hits: 8 } },
  };
  const pick = (extra = {}) => telegramPick({
    fixture, market, card, lambdas: { home: 6.75, away: 4.1, total: 10.85 },
    price: 1.8, book: "Bet365", stake: 1.5, ...extra });

  test("opens on the date, the league and the fixture", () => {
    const out = pick();
    expect(out).toContain("📅 Thursday 10th September");
    expect(out).toContain("Série B @");
    expect(out).toContain("🏟️ Operario-PR v CRB");
  });

  test("says the line the way it is said, not the way it is stored", () => {
    expect(pick()).toContain("🚩 6+ Operario-PR corners");
    expect(pickLabel({ group: "total", line: 9.5 }, "A", "B")).toBe("10+ match corners");
    expect(pickLabel({ group: "away", line: 4.5 }, "A", "B")).toBe("5+ B corners");
  });

  test("carries the price, the book, the stake and the model's own number", () => {
    const out = pick();
    expect(out).toContain("📈 [1.80] via Bet365 💸 1.5u");
    expect(out).toContain("📊 Model price: 1.64 (61%) | EV: +9.8% ✅");
    expect(out).toContain("📊 Model: 6.75 expected corners for the hosts");
  });

  test("quotes the ladder as counts, every rung", () => {
    expect(pick()).toContain(
      "🔥 Operario-PR have won 4+ corners in 10/10 at home. 5+ in 9/10. 6+ in 7/10.");
  });

  test("a rung that never landed is dropped, not printed as 0/10", () => {
    const out = wonLadder("T", { games: 10, scope: "home", hits: { 4: 9, 5: 6, 6: 0 } });
    expect(out).toContain("4+ corners in 9/10");
    expect(out).not.toContain("0/10");
  });

  test("a thin venue split is described as what it actually counted", () => {
    const out = wonLadder("T", { games: 8, scope: "overall", hits: { 4: 6 } });
    expect(out).not.toContain("at home");
    expect(out).toContain("in their last games");
  });
});

// THE VERDICT HAS TO BE EARNED. "an open, stretched game" is a conclusion, and a builder
// that prints it unconditionally will sooner or later put it over a tight defence that
// never scores early — saying the opposite of the numbers directly above it.
describe("the open-game verdict", () => {
  const leaky = { avg: 6.7 }, tight = { avg: 4.1 };
  const early = { games: 10, hits: 8 }, late = { games: 10, hits: 2 };

  test("both halves true earns the verdict and the tick", () => {
    const out = openGameCase("CRB", leaky, early);
    expect(out).toBe("✅ CRB concede 6.7 per game AND score in the first half in 8/10"
      + " — so this should be an open, stretched game rather than a dead one.");
  });

  test("a tight defence states the facts and claims nothing", () => {
    const out = openGameCase("CRB", tight, early);
    expect(out).toContain("concede 4.1 per game");
    expect(out).not.toContain("open, stretched");
    expect(out.startsWith("✅")).toBe(false);
  });

  test("a side that never scores early does not earn it either", () => {
    expect(openGameCase("CRB", leaky, late)).not.toContain("open, stretched");
  });

  test("an unmeasured first half is left out rather than reported as 0/0", () => {
    const out = openGameCase("CRB", leaky, { games: 0, hits: 0 });
    expect(out).toContain("concede 6.7 per game");
    expect(out).not.toContain("first half");
    expect(out).not.toContain("0/0");
  });
});

// THE REASONING DOES NOT GO OUT FREE. X gets the streak board — a line and how long it
// has been landing. The ladder and the opponent's defending are what the channel is
// selling, so what is pinned here is that they are absent from anything public.
describe("what X is allowed to see", () => {
  const fixture = { league_id: "bra-sb", home_name: "Operario-PR", away_name: "CRB",
                    date: "2026-09-10T12:00:00Z" };
  const streaks = [{ subject: "team", team: "Operario-PR", line: 5.5, line_label: "6+",
                     direction: "over", run: 7, venue: "home" }];
  const form = [{ team: "Operario-PR", venue: "home", label: "unbeaten in 4" }];
  const out = fixtureStreakShare({ fixture, streaks, form })(4);

  test("the streak and the game state are the whole of it", () => {
    expect(out).toContain("Operario-PR 6+ corners — 7 in a row");
    expect(out).toContain("Operario-PR unbeaten in 4 at home");
  });

  test("the ladder stays behind the subscription", () => {
    expect(out).not.toContain("10/10");
    expect(out).not.toContain("have won");
  });

  test("so does the opponent's defending, and the verdict drawn from it", () => {
    expect(out).not.toContain("concede");
    expect(out).not.toContain("first half");
    expect(out).not.toContain("open, stretched");
  });

  test("and so does the price", () => {
    expect(out).not.toContain("1.64");
    expect(out).not.toContain("EV");
  });
});

describe("a pick reposted after the game", () => {
  const base = {
    fixture: { league_id: "bra-sb", league_name: "Série B", home_name: "Operario-PR",
               away_name: "CRB", date: "2026-09-10T12:00:00Z" },
    market: { group: "home", line: 5.5, fair_odds: 1.64, ev: 9.8 },
    card: {}, lambdas: { home: 6.75 }, price: 1.8, book: "Bet365", stake: 1.5,
  };

  test("the result mark rides on the stake line, and only once settled", () => {
    expect(telegramPick(base)).not.toContain("💸 1.5u ✅");
    expect(telegramPick({ ...base, result: "win" })).toContain("💸 1.5u ✅");
    expect(telegramPick({ ...base, result: "loss" })).toContain("💸 1.5u ❌");
  });

  test("a losing bet does not retract a price that was worth taking", () => {
    // EV is a claim about the price, not about the outcome. A settled loss must not
    // rewrite it — that would be grading the process by the result.
    expect(telegramPick({ ...base, result: "loss" })).toContain("EV: +9.8% ✅");
  });

  test("no price at all still produces a usable post rather than empty brackets", () => {
    const out = telegramPick({ ...base, price: undefined, book: "", stake: undefined });
    expect(out).not.toContain("[]");
    expect(out).toContain("🚩 6+ Operario-PR corners");
  });
});

test("the date line carries an ordinal, including the teens", () => {
  expect(postDate("2026-09-10T12:00:00Z")).toBe("Thursday 10th September");
  expect(postDate("2026-09-11T12:00:00Z")).toBe("Friday 11th September");
  expect(postDate("2026-09-01T12:00:00Z")).toBe("Tuesday 1st September");
  expect(postDate("2026-09-22T12:00:00Z")).toBe("Tuesday 22nd September");
  expect(postDate("")).toBe("");
});

test("the kick-off reads as a clock time, not a 24-hour stamp", () => {
  expect(postTime("2026-09-10T12:30:00Z")).toMatch(/^\d{1,2}:\d{2}(am|pm)$/);
});

// ONE OPENING, BOTH DESTINATIONS. The channel post and the X post are about the same game
// and go out within an hour of each other. Two copies of this header is exactly how one of
// them ends up saying "Sat 15:00" while the other says "Thursday 10th September".
describe("the header every fixture post opens with", () => {
  const fixture = { league_id: "bra-sb", home_name: "Operario-PR", away_name: "CRB",
                    date: "2026-09-10T12:00:00Z" };

  test("is the date, the league with its kick-off, then the fixture", () => {
    const [day, where, who] = postHeader({ fixture, leagueName: "Série B" });
    expect(day).toBe("📅 Thursday 10th September");
    expect(where).toMatch(/^🇧🇷 Série B @ \d{1,2}:\d{2}(am|pm)$/);
    expect(who).toBe("🏟️ Operario-PR v CRB");
  });

  test("X and the channel open on exactly the same three lines", () => {
    const streaks = [{ subject: "team", team: "Operario-PR", line: 5.5, line_label: "6+",
                       direction: "over", run: 7, venue: "home" }];
    const x = fixtureStreakShare({ fixture, streaks, leagueName: "Série B" })(4);
    const vip = telegramPick({
      fixture: { ...fixture, league_name: "Série B" },
      market: { group: "home", line: 5.5, fair_odds: 1.64 }, card: {}, lambdas: {} });
    const top = (s) => s.split("\n").slice(0, 3).join("\n");
    expect(top(x)).toBe(top(vip));
    expect(top(x)).toContain("📅 Thursday 10th September");
  });

  test("a missing league still opens on the date rather than a stray flag", () => {
    const [day, where] = postHeader({ fixture, leagueName: "" });
    expect(day).toBe("📅 Thursday 10th September");
    expect(where).toMatch(/^🇧🇷 @ /);
  });

  test("no date at all drops the line instead of printing an empty one", () => {
    const lines = postHeader({ fixture: { ...fixture, date: null }, leagueName: "Série B" });
    expect(lines.some((l) => l.startsWith("📅"))).toBe(false);
    expect(lines[0]).toContain("Série B");
  });
});

// ONE GAME, POSTED WHOLE.
//
// Rows here are real, taken from a live /api/share/rows response, because the trap this
// board has is a judgement one: the longest run on that board was Juventus 6+ at 7 games
// and a model probability of 37%. Posting it free, with no price beside it, is the post
// that looks wrong the moment it misses.
describe("the game of the day", () => {
  const row = (name, league_id, league_name, line_label, run, prob, opponent, is_home, avg) => ({
    name, league_id, league_name, line_label, avg,
    streak: { length: run, status: "active" },
    projection: { prob, fair_odds: Number((100 / prob).toFixed(2)) },
    next_fixture: { date: "2026-09-13T10:00:00Z", opponent, is_home },
  });
  const board = [
    row("Juventus", "ita-sa", "Serie A", "6+", 7, 37.3, "Sassuolo", false, 8.0),
    row("Club Brugge", "bel-pl", "Jupiler Pro League", "5+", 9, 79.4, "Antwerp", true, 8.2),
    row("Viking", "nor-el", "Eliteserien", "5+", 8, 76.7, "Kristiansund BK", true, 8.2),
    row("Grimsby", "eng-l2", "League Two", "6+", 5, 51.1, "Bristol Rovers", true, 7.0),
  ];

  test("the run breaks ties, it does not win them on its own", () => {
    // Club Brugge: 9 in a row AND 79%. Juventus has the second-longest run and the worst
    // number on the board, and must not be what goes out.
    expect(pickGame(board).name).toBe("Club Brugge");
  });

  test("a long run the model dislikes loses to a shorter one it likes", () => {
    const pick = pickGame([
      row("Longshot", "ita-sa", "Serie A", "8+", 11, 22.0, "X", true, 9.0),
      row("Solid", "nor-el", "Eliteserien", "5+", 5, 71.0, "Y", true, 8.0),
    ]);
    expect(pick.name).toBe("Solid");
  });

  test("when nothing clears the bar the ranking inverts to best odds first", () => {
    // The reason to drop the bar is that there is no strong line today. Answering that
    // with the longest shot on the board would be the opposite of the intent.
    const pick = pickGame([
      row("LongAndUnlikely", "ita-sa", "Serie A", "7+", 12, 18.0, "X", true, 9.0),
      row("ShortAndLessBad", "nor-el", "Eliteserien", "5+", 3, 44.0, "Y", true, 7.0),
    ]);
    expect(pick.name).toBe("ShortAndLessBad");
  });

  test("renders plain — one stat a line, no separators between clauses", () => {
    const out = gameShare({ row: pickGame(board) })();
    const lines = out.split("\n");
    // The hour is the READER'S clock, so it is asserted by shape — pinning 11:00am
    // would only be asserting the timezone the suite happens to run in.
    expect(lines[0]).toMatch(/^📅 Sunday 13th September \d{1,2}:\d{2}(am|pm)$/);
    expect(lines[1]).toBe("🇧🇪 Jupiler Pro League Club Brugge v Antwerp");
    expect(lines[2]).toBe("🔥 Club Brugge 5+ corners 9 in a row");
    expect(lines[3]).toBe("🎯 averaging 8.2 a game");
  });

  test("no template punctuation anywhere in it", () => {
    // A post that reads as generated gets scrolled past. The @, the slashes between
    // clauses and the em-dashes all went for that reason.
    const out = gameShare({ row: pickGame(board) })();
    expect(out).not.toContain(" @ ");
    expect(out).not.toContain(" / ");
    expect(out).not.toContain("—");
    expect(out).not.toContain(" · ");
  });

  test("the only blank line in the post is the one before the tail", () => {
    const out = gameShare({ row: pickGame(board), more: 14, site: "https://thecornermodel.com" })();
    expect(out.split("\n\n")).toHaveLength(2);
    expect(out.endsWith("14+ more via: thecornermodel.com")).toBe(true);
  });

  test("the tail counts other angles, and drops the scheme X does not need", () => {
    expect(moreVia(14, "https://thecornermodel.com")).toBe("\n\n14+ more via: thecornermodel.com");
    expect(moreVia(0, "https://thecornermodel.com")).toBe("\n\nMore via: thecornermodel.com");
    // No site configured is not a reason to publish a dangling "more via:".
    expect(moreVia(14, "")).toBe("");
  });

  test("an away team is named on the right side of the v", () => {
    const out = gameShare({ row: board[0] })();
    expect(out).toContain("Sassuolo v Juventus");
    expect(out).not.toContain("Juventus v Sassuolo");
  });

  test("a flag rather than a fire below the fire line", () => {
    expect(gameShare({ row: board[3] })()).toContain("🚩 Grimsby 6+ corners 5 in a row");
    expect(gameShare({ row: board[1] })()).toContain("🔥");
  });

  test("the model's number never reaches the tweet, in either form", () => {
    // A percentage and a fair price are the same fact — 79% IS 1.26 — so publishing the
    // percentage publishes the price. Both are pinned out.
    const out = gameShare({ row: pickGame(board) })();
    expect(out).not.toContain("%");
    expect(out).not.toContain("1.26");
    expect(out).not.toMatch(/\d\.\d\d/);
    expect(out).not.toMatch(/model/i);
  });

  test("what it does carry is countable by anyone", () => {
    // The run and the average are facts about games already played. Giving those away
    // costs nothing; giving the price away costs the subscription.
    const out = gameShare({ row: pickGame(board) })();
    expect(out).toContain("9 in a row");
    expect(out).toContain("averaging 8.2 a game");
  });

  test("an unmeasured average is dropped rather than printed as a number", () => {
    const bare = { ...board[1], avg: null };
    const out = gameShare({ row: bare })();
    expect(out).not.toContain("🎯");
    expect(out).toContain("🔥 Club Brugge");
  });

  test("a row with no fixture attached produces nothing to post", () => {
    expect(gameShare({ row: { ...board[1], next_fixture: null } })()).toBe("");
    expect(pickGame([])).toBeNull();
    expect(pickGame([{ name: "NoFixture", streak: { length: 9 } }])).toBeNull();
  });

  test("the whole post fits a tweet with room for the link", () => {
    for (const r of board) {
      const out = gameShare({ row: r })();
      expect(out.length).toBeLessThan(200);
    }
  });
});

// THE WEEKEND CARD — the only post that carries the model's numbers, because it is the
// only one that goes to people who have paid for them.
describe("the weekend card", () => {
  const R = (name, lid, ln, ll, run, prob, fair, opp, home, date) => ({
    name, league_id: lid, league_name: ln, line_label: ll,
    streak: { length: run }, projection: { prob, fair_odds: fair },
    next_fixture: { date, opponent: opp, is_home: home },
  });
  const rows = [
    R("Juventus", "ita-sa", "Serie A", "6+", 7, 37.3, 2.68, "Sassuolo", false, "2026-09-13T18:45:00Z"),
    R("Club Brugge KV", "bel-pl", "Jupiler", "5+", 9, 79.4, 1.26, "Antwerp", true, "2026-09-13T11:30:00Z"),
    R("Grimsby", "eng-l2", "League Two", "6+", 5, 51.1, 1.96, "Bristol Rovers", true, "2026-09-12T11:30:00Z"),
  ];
  const card = weekendCard({ rows, generatedAt: "2026-09-11T11:00:00Z" });

  test("is ordered by kick-off, not by how good the angle is", () => {
    // Someone placing these works down the card in time order. Club Brugge is the best
    // row on it and still sits second, behind Saturday's game.
    const order = ["Grimsby", "Club Brugge KV", "Sassuolo v Juventus"];
    let at = -1;
    for (const name of order) {
      const next = card.indexOf(name);
      expect(next).toBeGreaterThan(at);
      at = next;
    }
  });

  test("carries the model's number, unlike every public post", () => {
    expect(card).toContain("79% (1.26)");
    expect(card).toContain("37% (2.68)");
  });

  test("says the price is a bar rather than a bet", () => {
    // A card of percentages read without this looks like a list of bets.
    expect(card).toContain("fair price");
    expect(card).toContain("Anything shorter than that is not worth taking");
  });

  test("keeps every qualifying game — it is a card, not a trimmed post", () => {
    expect(card).toContain("Juventus");
    expect(card).toContain("Club Brugge KV");
    expect(card).toContain("Grimsby");
    expect(card).not.toContain("more on the site");
  });

  test("an away team is named on the right side of the v", () => {
    expect(card).toContain("Sassuolo v Juventus");
  });

  test("an unpriced row still lists, without inventing a number", () => {
    const bare = weekendCard({ rows: [{ ...rows[1], projection: {} }] });
    expect(bare).toContain("Club Brugge KV");
    expect(bare).toContain("9 in a row");
    expect(bare).not.toContain("%");
  });

  test("a weekend with nothing running into it sends nothing", () => {
    expect(weekendCard({ rows: [] })).toBe("");
    expect(weekendCard({ rows: [{ name: "X", streak: { length: 9 } }] })).toBe("");
  });
});

// MONDAY'S REVIEW OF THE CHANNEL'S OWN PICKS.
//
// This is the post that makes a claim about the product rather than the model, so the
// things pinned here are the ways it could flatter itself: hiding a miss when trimmed,
// counting a void as a win, quietly dropping games still running, or reaching back further
// than the week it says it covers.
describe("the picks review", () => {
  const DAY = 86400000;
  const now = Date.parse("2026-09-14T12:00:00Z");        // a Monday
  const row = (name, league_id, line_label, result, value, daysAgo) => ({
    name, league_id, line_label, result, value,
    kickoff: new Date(now - daysAgo * DAY).toISOString(),
  });
  const rows = [
    row("Club Brugge", "bel-pl", "5+", "win", 9, 1),
    row("Juventus", "ita-sa", "6+", "loss", 4, 1),
    row("Viking", "nor-el", "5+", "win", 8, 2),
    row("Grimsby", "eng-l2", "6+", "win", 7, 3),
  ];

  test("heads with the count it can actually support", () => {
    const out = picksReview({ rows, now })(6);
    expect(out).toContain("How the VIP picks landed — 3/4 last week:");
  });

  test("publishes the line, unlike the streak results post", () => {
    // Those runs are still live and the line is still the product. These are settled: the
    // bet is over, and a record whose rows cannot be checked against the game is an advert.
    const out = picksReview({ rows, now })(6);
    expect(out).toContain("Club Brugge 5+ — 9 corners ✅");
    expect(out).toContain("Juventus 6+ — 4 corners ❌");
  });

  test("a trimmed post still shows a miss", () => {
    // The first N rows can happen to be all wins, and an honest "3/4" over a clean sweep
    // is a true count and a false impression.
    const winsFirst = [rows[0], rows[2], rows[3], rows[1]];
    const out = picksReview({ rows: winsFirst, now })(2);
    expect(out).toContain("❌");
    expect(out).toContain("3/4");
  });

  test("voids are named rather than quietly dropped", () => {
    const out = picksReview({ rows: [...rows, row("X", "nor-el", "5+", "void", 5, 1)], now })(6);
    expect(out).toContain("1 void (exact line — stake back)");
    expect(out).toContain("3/4");          // the void is not counted as a win OR a loss
  });

  test("games still running are declared, not omitted", () => {
    // "3/3" posted while three more are outstanding is a different week, and the reader
    // has no way to tell which one they are being shown.
    const out = picksReview({ rows: [...rows, row("Y", "nor-el", "5+", null, null, 0)], now })(6);
    expect(out).toContain("1 still to settle");
  });

  test("it reaches back exactly the week it claims to", () => {
    const old = row("Ancient", "ita-sa", "6+", "win", 11, 30);
    const out = picksReview({ rows: [...rows, old], now })(8);
    expect(out).not.toContain("Ancient");
    expect(out).toContain("3/4");
  });

  test("a fixture that has not kicked off yet cannot be reviewed", () => {
    const future = row("Tomorrow", "ita-sa", "6+", "win", 11, -2);
    const out = picksReview({ rows: [...rows, future], now })(8);
    expect(out).not.toContain("Tomorrow");
  });

  test("a week with nothing settled posts nothing", () => {
    expect(picksReview({ rows: [], now })(6)).toBe("");
    expect(picksReview({ rows: [row("P", "nor-el", "5+", null, null, 1)], now })(6)).toBe("");
  });

  test("the channel is nameable, since the post says whose picks these are", () => {
    expect(picksReview({ rows, channel: "Telegram", now })(6)).toContain("Telegram picks");
  });
});
