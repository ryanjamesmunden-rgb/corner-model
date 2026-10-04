#!/usr/bin/env node
// The week's results as one clip: fetch the graded record, build the reel and the caption.
//
// WHY THIS EXISTS. The results were going out as one card per pick — ten exports, ten
// uploads, and ten chances to quietly not publish the one that lost. One clip off one list
// is less work AND harder to shade: the rows come from /api/results in kick-off order and
// the tally at the end counts exactly what went past.
//
// IT SELECTS NOTHING. The window is a number of days and everything settled inside it is
// on the clip, losers and voids included. lib/resultsReel.js holds that rule and the one
// that matters more — a week is a CHOSEN period, so the overall record rides on the end
// card beside it, which is what makes "another 10 from 10" worth believing.
//
// `claimed` ONLY, which the endpoint already separates: rows logged after kick-off are
// published on the site and can never be animated into a highlight reel, because an angle
// written down once the result is known is not a prediction.
//
// Usage:  node tools/results_reel.mjs [--days 7] [--max 14] [--heading "THIS WEEK"]
//                                     [--json-out reel.json] [--args-out reel_args.json]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (required)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { reelFrom, reelPost, nextFrom, MAX_REEL_ROWS } = await import(resolve(LIB, "resultsReel.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const TOKEN = process.env.TOOLS_TOKEN;
const DAYS = Number(arg("days", "7"));
const MAX = Number(arg("max", String(MAX_REEL_ROWS)));
const HEADING = arg("heading", null);
// How far ahead the end card looks. 4 days from a Monday run reaches the weekend; the
// default matches the window the fixture board is built for.
const AHEAD = Number(arg("ahead", "7"));
const JOIN = arg("join", `${SITE.replace(/^https?:\/\//, "")}/join`);
const JSON_OUT = arg("json-out", "reel.json");
const ARGS_OUT = arg("args-out", "reel_args.json");

const fail = (m) => { console.error(`results_reel: ${m}`); process.exit(1); };
if (!TOKEN) fail("TOOLS_TOKEN is required");

const ctl = new AbortController();
const timer = setTimeout(() => ctl.abort(), 120000);
let data;
try {
  const res = await fetch(`${BACKEND}/api/results?token=${TOKEN}`, { signal: ctl.signal });
  if (!res.ok) {
    // 401 here means the token did not take — the endpoint falls back to a signed-in
    // reader and refuses the public one, so the message says which thing to go and fix.
    const body = await res.text().catch(() => "");
    fail(`/api/results answered HTTP ${res.status} — ${body.slice(0, 200)}`);
  }
  data = await res.json();
} catch (err) {
  fail(`could not read the record — ${err.message}`);
} finally {
  clearTimeout(timer);
}

// WHAT IS COMING, AND NEVER FATAL. The reel is a record of what happened; the end card is
// an advert for what is next, and a clip that refused to exist because the fixture board
// was slow would be the wrong trade. No fixtures, no end card — the clip ends on the
// tally, which is what it did before this and is still a complete post.
const upcoming = async () => {
  const ctl2 = new AbortController();
  const t = setTimeout(() => ctl2.abort(), 90000);
  try {
    const res = await fetch(
      `${BACKEND}/api/share/rows?token=${TOKEN}&days=${AHEAD}&limit=200&boards=fixtures`,
      { signal: ctl2.signal });
    if (!res.ok) {
      console.error(`results_reel: fixtures answered HTTP ${res.status} — no end card`);
      return null;
    }
    const d = await res.json();
    return nextFrom(d.fixtures || []);
  } catch (err) {
    console.error(`results_reel: could not read the fixture board (${err.message}) — no end card`);
    return null;
  } finally {
    clearTimeout(t);
  }
};

const next = await upcoming();
const reel = reelFrom(data, { days: DAYS, max: MAX, next, join: JOIN });
if (!reel) {
  // A QUIET WEEK IS NOT A FAILURE. Fewer than two settled picks in the window is a week
  // without a clip in it, and the caller posts nothing rather than animating one result.
  const n = (data?.posted?.claimed?.rows || []).length;
  console.error(`results_reel: nothing to animate — fewer than 2 settled picks in the last `
                + `${DAYS} days (${n} claimed rows on file in total)`);
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, days: DAYS }, null, 2));
  process.exit(0);
}

const post = reelPost({
  reel, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING } : {}),
});

writeFileSync(JSON_OUT, JSON.stringify({ empty: false, reel, post }, null, 2));
writeFileSync(ARGS_OUT, JSON.stringify({
  reel, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING.toUpperCase() } : {}),
}));
// PRINTED, because the clip is the thing nobody can check until it has been watched, and
// this line is the same claim in a form that survives a failed encode.
console.error(`results_reel: ${reel.big} over ${DAYS} days — ${reel.n} rows`
              + (reel.more ? ` (+${reel.more} trimmed)` : "")
              + (reel.voided ? `, ${reel.voided} void` : "")
              + (reel.units != null ? `, ${reel.units}u` : "")
              + ` · ${reel.context}`
              + (reel.next ? ` · next up ${reel.next.count} games in ${reel.next.leagues} leagues`
                           : " · no end card"));
