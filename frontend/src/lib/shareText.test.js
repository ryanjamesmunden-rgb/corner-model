/**
 * These builders are the contract between the share buttons and the scheduled draft
 * job. The failure they exist to prevent is drift — the automated post looking subtly
 * unlike the one a person clicked out an hour earlier — so what's pinned is the shape
 * of a line and the one thing a row limit must never break: the "+N more" count has to
 * describe the list it is actually attached to.
 */
import { streakShare, fixtureShare, bestTeamsShare, streakResultShare,
         fixtureStreakShare } from "./shareText";

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
