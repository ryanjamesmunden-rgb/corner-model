/**
 * These builders are the contract between the share buttons and the scheduled draft
 * job. The failure they exist to prevent is drift — the automated post looking subtly
 * unlike the one a person clicked out an hour earlier — so what's pinned is the shape
 * of a line and the one thing a row limit must never break: the "+N more" count has to
 * describe the list it is actually attached to.
 */
import { streakShare, fixtureShare, bestTeamsShare } from "./shareText";

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
    expect(build(1)).toContain(`${NORWAY} A 5+`);
    expect(build(1)).not.toContain("• A");
  });

  test("carries the opponent, the record and the kick-off", () => {
    const line = build(1).split("\n")[1];
    expect(line).toContain("vs Rosenborg");
    expect(line).toContain("(5/5)");
    expect(line).toContain("Tomorrow");
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

  test("best teams keeps its numbering, so the flag joins the name", () => {
    const out = bestTeamsShare({
      rows: [{ name: "Celtic", league_id: "sco-pl", won_avg: 8.123 }],
      side: "overall", windowLabel: "Season",
    })(4);
    // The ranking line, not the heading above it.
    expect(out.split("\n")[1]).toMatch(/^1\. \u{1F3F4}/u);
    expect(out).toContain("8.12 corners won/game");
  });
});
