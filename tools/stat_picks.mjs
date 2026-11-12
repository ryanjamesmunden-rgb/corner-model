#!/usr/bin/env node
// The stat-pick post: corner lines that have been landing, with the price and the edge.
//
// WHY THIS POST AND NOT THE VALUE BOARD AGAIN. The value board says where the price is
// wrong — which is the model's opinion, and a reader has to take it. This says how often
// the bet has actually landed, which is a count they can go and check against the form
// table the site already publishes unblurred. The count is what travels; the price is
// what makes it a pick rather than a fact.
//
// THE RULE IS IN THE POST, ABOVE THE ROWS. "Every team corner line on the card landing 7+
// from their last 10, at 1.50 or bigger, with a positive model edge." A list headed
// "stat picks" with no rule under it is a tip sheet; with the rule under it, it is a
// filter anyone can disagree with — and that is the whole reason the format works.
//
// IT NEVER SENDS. The workflow writes the post into the run summary and keeps it as an
// artifact. A post cannot be unposted.
//
// Usage:  node tools/stat_picks.mjs [--days 2] [--max 12] [--min-hit 0.7]
//                                   [--min-odds 1.5] [--min-ev 0] [--per-game 2]
//                                   [--band 5,6] [--heading "..."] [--json-out picks.json]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (required)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { picksFrom, picksPost, MIN_PICK_ROWS, MAX_PICK_ROWS } =
  await import(resolve(LIB, "statPicks.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const TOKEN = process.env.TOOLS_TOKEN;
// TWO DAYS, NOT SEVEN. "Save this before kick-off" is a post about today's card; a line
// three days out will have moved twice before anyone can take it.
const DAYS = Number(arg("days", "2"));
const MAX = Number(arg("max", String(MAX_PICK_ROWS)));
const HEADING = arg("heading", null);
const JSON_OUT = arg("json-out", "picks.json");

const fail = (m) => { console.error(`stat_picks: ${m}`); process.exit(1); };
if (!TOKEN) fail("TOOLS_TOKEN is required");

const qs = new URLSearchParams({
  token: TOKEN,
  days: String(DAYS),
  min_hit: arg("min-hit", "0.7"),
  min_odds: arg("min-odds", "1.5"),
  min_ev: arg("min-ev", "0"),
  per_game: arg("per-game", "2"),
  band: arg("band", "5,6"),
  limit: "60",
});

const ctl = new AbortController();
const timer = setTimeout(() => ctl.abort(), 180000);
let data;
try {
  const res = await fetch(`${BACKEND}/api/share/stat-picks?${qs}`, { signal: ctl.signal });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    // 400 here is a bad band — the endpoint refuses a plus-line it cannot measure a rate
    // for rather than returning nothing, which would read as a quiet day.
    fail(`/share/stat-picks answered HTTP ${res.status} — ${body.slice(0, 300)}`);
  }
  data = await res.json();
} catch (err) {
  fail(`could not read the picks — ${err.message}`);
} finally {
  clearTimeout(timer);
}

const post = picksFrom(data, { max: MAX });

// WHY THERE IS NO POST, BY REASON. A day with nothing priced and a day where everything
// priced was landing 6 from 10 are different problems with different fixes, and "no picks
// today" tells them apart not at all.
const faults = data?.faults || {};
const why = Object.entries(faults).sort((a, b) => b[1] - a[1])
  .map(([k, n]) => `${k} ${n}`).join(", ");

if (!post) {
  console.error(`stat_picks: nothing to post — ${(data?.picks || []).length} row(s) `
                + `cleared the filters, ${MIN_PICK_ROWS} needed`
                + (why ? ` · dropped: ${why}` : ""));
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, days: DAYS, faults }, null, 2));
  process.exit(0);
}

const text = picksPost({
  post, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING } : {}),
});

writeFileSync(JSON_OUT, JSON.stringify({ empty: false, post, text, faults }, null, 2));

// PRINTED, because the post is the one thing nobody can check until it has gone out, and
// this is the same claim in a form that survives the file being lost.
console.error(`stat_picks: ${post.n} pick(s) across ${post.fixtures} fixture(s)`
              + (post.more ? ` (+${post.more} trimmed)` : "")
              + ` · ${post.rule} · over ${post.window} games`
              + ` · books ${post.books.join(", ")}`);
// THE LENGTH, because X refuses a post over its limit and the failure arrives at the
// worst moment. 280 is the free ceiling; a premium account has far more, so this reports
// rather than refuses.
console.error(`stat_picks: ${text.length} characters`
              + (text.length > 280 ? " — over the 280 free limit, needs premium or an image"
                                   : ""));
if (why) console.error(`stat_picks: dropped — ${why}`);
console.log(text);
