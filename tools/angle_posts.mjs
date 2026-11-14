#!/usr/bin/env node
// One thread per fixture: the game, then its whole EV+ corner ladder, plus the clip.
//
// WHAT THIS PRODUCES, PER ANGLE. Two tweets in the account's own format and one set of
// render args. The first tweet is the game and the fixture link; the second is the ladder
// — 5+ through 9+ with the book's price, the model's and the edge — and the clip draws
// the same rungs landing one at a time against the model's distribution.
//
// THE WHOLE LADDER GOES OUT. That is what was asked for and it is the stronger post: five
// rows where the edge WIDENS with the line is one argument about a corner distribution,
// where a single rung is only an assertion. What it also does is publish the long lines,
// which are the ones most often quoted by a single book — so every rung carries how many
// books stand behind it, every thread reports how many of its rungs are thin, and the run
// says so out loud. Marked, never dropped: which to post is a judgement, and a tool that
// removed them would be editing the argument on the way past.
//
// Usage:  node tools/angle_posts.mjs [--days 3] [--min-ev 0] [--min-rungs 2]
//                                    [--max 6] [--league all]
//                                    [--out-dir angles] [--json-out angles.json]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (required)
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { angleThread } = await import(resolve(LIB, "anglePost.js"));

const arg = (n, d = null) => {
  const i = process.argv.indexOf(`--${n}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : d;
};

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = (process.env.SITE_URL || "https://thecornermodel.com").replace(/^https?:\/\//, "");
const TOKEN = process.env.TOOLS_TOKEN;
const DAYS = Number(arg("days", "3"));
const MAX = Number(arg("max", "6"));
const OUT_DIR = arg("out-dir", "angles");
const JSON_OUT = arg("json-out", "angles.json");

const fail = (m) => { console.error(`angle_posts: ${m}`); process.exit(1); };
if (!TOKEN) fail("TOOLS_TOKEN is required");

const qs = new URLSearchParams({
  token: TOKEN, days: String(DAYS),
  min_ev: arg("min-ev", "0"),
  min_rungs: arg("min-rungs", "2"),
  limit: "40",
});
const league = arg("league", null);
if (league && league !== "all") qs.set("league_id", league);

let data;
try {
  const res = await fetch(`${BACKEND}/api/share/angles?${qs}`,
                          { signal: AbortSignal.timeout(180000) });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    fail(`/share/angles answered HTTP ${res.status} — ${body.slice(0, 300)}`);
  }
  data = await res.json();
} catch (err) {
  fail(`could not read the angles — ${err.message}`);
}

const angles = data?.angles || [];
const faults = data?.faults || {};
const why = Object.entries(faults).sort((a, b) => b[1] - a[1])
  .map(([k, n]) => `${k} ${n}`).join(", ");

if (!angles.length) {
  console.error(`angle_posts: nothing to post over ${DAYS} day(s)`
                + (why ? ` · dropped: ${why}` : ""));
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, days: DAYS, faults }, null, 2));
  process.exit(0);
}

mkdirSync(OUT_DIR, { recursive: true });
const built = [];

for (const a of angles.slice(0, Math.max(1, MAX))) {
  // The lib does the selecting and the wording; this only hands it the row and files
  // what comes back. The ladder the endpoint returned is already this side's, so it is
  // passed as `ladder` and angleRungs filters on the group again — harmless, and it
  // means the tool cannot produce a thread the lib would not.
  const thread = angleThread({
    fixture_id: a.fixture_id, league_id: a.league_id, league_name: a.league_name,
    date: a.date, home_name: a.home_name, away_name: a.away_name,
    best: null, alternatives: [], ladder: a.ladder,
  }, { group: a.group, site: SITE });
  if (!thread) continue;

  const slug = `${a.fixture_id}-${a.group}`;
  writeFileSync(join(OUT_DIR, `${slug}.args.json`),
                JSON.stringify({ thread, dist: a.dist || [], site: SITE }));
  writeFileSync(join(OUT_DIR, `${slug}.txt`),
                `${thread.game}\n\n----- reply -----\n\n${thread.ladder}\n`);
  built.push({ slug, ...thread, dist: (a.dist || []).length, lambda: a.lambda });
}

writeFileSync(JSON_OUT, JSON.stringify({ empty: !built.length, threads: built, faults },
                                       null, 2));

if (!built.length) {
  console.error("angle_posts: every angle came back with no printable rungs");
  process.exit(0);
}

console.error(`angle_posts: ${built.length} thread(s) over ${DAYS} day(s)`);
for (const t of built) {
  console.error(`  ${t.slug}  ${t.team} — ${t.n} rung(s) to ${t.topLine}+, `
                + `best +${t.bestEv}%`
                + (t.thinRungs ? `  ⚠ ${t.thinRungs} rung(s) one book only` : "")
                + (t.unquoted ? `, ${t.unquoted} unquoted` : "")
                + (t.dist ? "" : "  (no curve — clip will draw rungs only)"));
}
// SAID OUT LOUD AT THE END. A set of threads built entirely on single-book prices is a
// set of posts quoting numbers nobody else is offering, and that is a decision somebody
// should make on purpose rather than discover afterwards.
const thin = built.reduce((n, t) => n + t.thinRungs, 0);
const all = built.reduce((n, t) => n + t.n, 0);
if (thin) {
  console.error(`angle_posts: ${thin} of ${all} rung(s) are quoted by ONE book — `
                + "check those prices before posting");
}
if (why) console.error(`angle_posts: dropped — ${why}`);
