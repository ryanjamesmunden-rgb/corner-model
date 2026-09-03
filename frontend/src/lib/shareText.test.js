/**
 * These builders are the contract between the share buttons and the scheduled draft
 * job. The failure they exist to prevent is drift — the automated post looking subtly
 * unlike the one a person clicked out an hour earlier — so what's pinned is the shape
 * of a line and the one thing a row limit must never break: the "+N more" count has to
 * describe the list it is actually attached to.
 */
import { streakShare, fixtureShare, bestTeamsShare, streakResultShare } from "./shareText";

const NORWAY = "\u{1F1F3}\u{1F1F4}";
const soon = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(12, 0, 0, 0);
  return d.toISOString();
};

const streakRow = (name, league_id, line) => ({
  name, league_id, line, hits: 5, window: 5,
  next_fixture: { is_home: true, opponent: "Rosenborg", date: soon() },
});
const rows = ["A", "B", "C", "D", "E", "F", "G"].map((n, i) => streakRow(n, "nor-el", 5 + (i % 3)));
const build = streakShare({ rows, subject: "team", isUnder: false, side: "overall", presetLabel: "5 of 5" });

describe("a streak line", () => {
  test("opens with the country flag instead of a bullet", () => {
    expect(build(1)).toContain(`${NORWAY} A`);
    expect(build(1)).not.toContain("• A");
  });

  test("carries the opponent, the record and the kick-off", () => {
    const line = build(1).split("\n")[1];
    expect(line).toContain("vs Rosenborg");
    expect(line).toContain("(5/5)");
    expect(line).toContain("Tomorrow");
  });

  test("NEVER publishes the line — that is the paid half", () => {
    // The one thing a public post must not carry. Asserted across every row and every
    // limit, because a leak here is permanent and public the moment it is posted.
    for (const n of [1, 4, 7]) {
      const out = build(n);
      expect(out).not.toMatch(/\d\+/);        // "5+", "6+"
      expect(out).not.toMatch(/\bU\d/);       // "U9" on an under
    }
  });

  test("names the zone once, at the foot", () => {
    expect(build(6).match(/All times/g)).toHaveLength(1);
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
    expect(build(50).split("\n").filter((l) => l.includes("5/5"))).toHaveLength(7);
  });
});

describe("an empty board shares nothing at all", () => {
  test.each([
    ["streaks", streakShare({ rows: [], subject: "team", isUnder: false, side: "overall" })],
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
