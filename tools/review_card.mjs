#!/usr/bin/env node
// The review card: the channel's last few months, with the site's graded record beside them.
//
// TWO SOURCES, DELIBERATELY NOT MERGED. The monthly units come from lib/channelResults.js
// — the account's own record of the picks it sent out, which this site cannot verify
// because its ledger holds the model's automated selections rather than the posts. The hit
// rate comes from /api/results, which grades every published streak off a snapshot frozen
// BEFORE kick-off and can be checked row by row. The card draws them in separate blocks
// and says so on each; this tool keeps them separate on the way in.
//
// THE RECORD HALF IS OPTIONAL AND NEVER FATAL. If the backend is asleep, the token is
// wrong or nothing has settled, the card still draws with the stated months alone — which
// is the card this account could make before any of this existed. Losing the advert
// because the extra block could not be fetched would be the wrong trade.
//
// Usage:  node tools/review_card.mjs [--months 3] [--heading "THE RECORD"]
//                                    [--json-out review.json] [--args-out review_args.json]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (optional — without it, no graded block)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { reviewFrom, reviewPost, DEFAULT_PERIODS } = await import(resolve(LIB, "reviewCard.js"));
const { recentPeriods } = await import(resolve(LIB, "channelResults.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const TOKEN = process.env.TOOLS_TOKEN;
const MONTHS = Number(arg("months", String(DEFAULT_PERIODS)));
const HEADING = arg("heading", null);
const JSON_OUT = arg("json-out", "review.json");
const ARGS_OUT = arg("args-out", "review_args.json");

const fail = (m) => { console.error(`review_card: ${m}`); process.exit(1); };

/** The graded record, or null. Never throws — see the note at the top. */
const record = async () => {
  if (!TOKEN) {
    console.error("review_card: no TOOLS_TOKEN — drawing the stated months alone");
    return null;
  }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 90000);
  try {
    const res = await fetch(`${BACKEND}/api/results?token=${TOKEN}`, { signal: ctl.signal });
    if (!res.ok) {
      console.error(`review_card: /api/results answered HTTP ${res.status} — `
                    + "drawing the stated months alone");
      return null;
    }
    const data = await res.json();
    const s = data.summary || {};
    // PRINTED, because this is the half nobody can see without the token, and the whole
    // point of the block is that somebody could check it.
    console.error(`review_card: graded record — ${s.landed} of ${s.settled} landed, `
                  + `${s.pending} pending, ${s.voided} void, over ${s.weeks} weeks `
                  + `since ${s.since}`);
    return data;
  } catch (err) {
    console.error(`review_card: could not read the record (${err.message}) — `
                  + "drawing the stated months alone");
    return null;
  } finally {
    clearTimeout(timer);
  }
};

const periods = recentPeriods(MONTHS);
if (!periods.length) fail("no months in channelResults.js to publish");

const review = reviewFrom({ periods, record: await record(), count: MONTHS });
if (!review) fail("nothing to publish");

const post = reviewPost({
  review, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING } : {}),
});

writeFileSync(JSON_OUT, JSON.stringify({ review, post }, null, 2));
writeFileSync(ARGS_OUT, JSON.stringify({
  review, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING.toUpperCase() } : {}),
}));
console.error(`review_card: ${review.n} months, ${review.totalText}`
              + (review.partial ? ` (${review.running.join(", ")} still running)` : "")
              + (review.verified ? ` · graded ${review.verified.big}` : " · no graded block"));
