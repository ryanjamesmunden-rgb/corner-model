#!/usr/bin/env node
// Builds the one daily message: the teams on a corner run, banded by what that line pays.
//
// WHY A SEPARATE TOOL FROM social_draft.mjs. That file builds eleven boards and knows how
// to post to X, to a channel and to a person, and the whole point of this one is that it
// does exactly one thing. Adding a twelfth board to the thing being replaced would have
// left the replacement sharing a timeout, a retry policy and a fetch with ten boards it
// does not use — and would have made "stop sending me the others" a change to the same
// file that sends them.
//
// IT ASKS FOR ONE BOARD. /api/share/rows?boards=streaks, and nothing else: no chase scan,
// no mismatch pass, no value board. The endpoint's own docstring warns that each board
// walks every team in the database and that asking for boards a caller will not read is
// how a free-tier backend times out, so asking for one is the cheap path as well as the
// honest one.
//
// AND IT ASKS FOR A LOT OF ROWS. The endpoint sorts streaks by LINE descending, so a small
// limit returns the highest lines — which are precisely the band with no record behind it.
// At limit 12 a digest built to lead on 5+ and 6+ could receive nothing but 8+ and 9+ rows
// and report, truthfully and uselessly, that the money band was empty. The limit is 200
// for the same reason the streak finder's is.
//
// WHAT IT WILL NOT DO. It never posts to the channel and has no flag that would let it.
// This message is for the person running the account; the audience-facing cards are still
// social_draft.yml's job.
//
// Usage:  node tools/digest.mjs [--days 2] [--min-run 5] [--out digest.md]
//                               [--json-out digest.json]
// Env:    BACKEND_URL (default the live Render backend), TOOLS_TOKEN (required),
//         SITE_URL (default thecornermodel.com)

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");

// The same modules the site's own screens use. Reimplementing the band table here would
// be a second copy of the P&L figures, and the two would disagree the first month one of
// them was updated — about what the account believes its own record is.
const { digestPost, DIGEST_MIN_RUN } = await import(resolve(LIB, "digest.js"));
const { postDayTime, POST_TZ } = await import(resolve(LIB, "shareText.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

const DAYS = Number(arg("days", "2"));
const MIN_RUN = Number(arg("min-run", String(DIGEST_MIN_RUN)));
const OUT = arg("out", null);
const JSON_OUT = arg("json-out", null);
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const TOKEN = process.env.TOOLS_TOKEN;

// SEE THE NOTE AT THE TOP: a small limit returns only the highest lines, because the
// endpoint sorts by line descending. 200 covers a full weekend's board.
const LIMIT = 200;

// A message built from yesterday's numbers reads exactly like one built from today's, and
// this one carries kick-off times. 14h is a little over the 12h sync cadence, matching
// social_draft.mjs — the same threshold, for the same reason.
const MAX_DATA_AGE_HOURS = 14;

const FETCH_MS = [60000, 120000];

const fail = (msg) => {
  console.error(`digest: ${msg}`);
  process.exit(1);
};

const getOnce = async (path, ms, fatal) => {
  let res;
  try {
    res = await fetch(`${BACKEND}${path}`, { signal: AbortSignal.timeout(ms) });
  } catch (err) {
    const what = err.name === "TimeoutError"
      ? `timed out after ${ms / 1000}s` : err.message;
    if (!fatal) throw new Error(what);
    fail(`could not reach ${BACKEND} — ${what}`);
  }
  // CONFIG ERRORS ARE FATAL ON THE FIRST ATTEMPT. A missing or wrong token answers the
  // same however often it is asked, and retrying only buries the one message that says
  // what a person has to go and change.
  if (res.status === 503) {
    fail("backend has no TOOLS_TOKEN set in its own environment — set it on Render, then "
         + "set the matching GitHub repo secret");
  }
  if (res.status === 403) {
    fail("backend rejected the token — the TOOLS_TOKEN repo secret does not match the "
         + "backend env");
  }
  if (!res.ok) {
    const what = `/share/rows returned ${res.status} ${res.statusText}`;
    if (!fatal) throw new Error(what);
    fail(what);
  }
  return res.json();
};

const get = async (path) => {
  for (let i = 0; i < FETCH_MS.length; i++) {
    const last = i === FETCH_MS.length - 1;
    try {
      return await getOnce(path, FETCH_MS[i], last);
    } catch (err) {
      if (last) throw err;
      console.error(`digest: attempt ${i + 1} failed (${err.message}) — retrying with `
                    + `${FETCH_MS[i + 1] / 1000}s`);
    }
  }
};

if (!TOKEN) fail("TOOLS_TOKEN is not set — add it as a repo secret");

const data = await get(`/api/share/rows?days=${DAYS}&limit=${LIMIT}&boards=streaks`
                       + `&token=${encodeURIComponent(TOKEN)}`);

// Printed whether or not the run goes on to send, because this endpoint has exceeded a
// caller's timeout before and one number for the whole request cannot say which pass was
// slow. Same reasoning as the timings block in server.py.
if (data?.timings_ms) {
  console.error(`digest: backend timings ${JSON.stringify(data.timings_ms)}`);
}

const age = data?.data_age_hours;
if (age !== null && age !== undefined && age > MAX_DATA_AGE_HOURS) {
  // NOT A SILENT SKIP. A digest that quietly does not arrive is indistinguishable from
  // one that arrived empty, and the cause here — a sync that has stopped — is worth
  // knowing about today rather than when somebody notices the message has gone.
  fail(`data is ${age}h old (limit ${MAX_DATA_AGE_HOURS}h) — the sync has probably `
       + "stalled; nothing sent");
}

const rows = Array.isArray(data?.streaks) ? data.streaks : [];

// THE WINDOW IN WORDS, so a row kicking off tomorrow is not read as one kicking off
// tonight. The kick-off time on each row is the precise answer; this is the heading that
// stops a reader assuming before they get there.
const windowLabel = DAYS <= 1 ? "today"
  : DAYS === 2 ? "today and tomorrow"
  : `the next ${DAYS} days`;

const dayLabel = new Intl.DateTimeFormat("en-GB", {
  timeZone: POST_TZ, weekday: "short", day: "numeric", month: "short",
}).format(new Date());

const post = digestPost({ rows, site: SITE, dayLabel, dayTime: postDayTime,
                          minRun: MIN_RUN, windowLabel });

// TELEGRAM'S OWN LIMIT, checked here rather than trusted. digest.js caps every band, so a
// message this long means a band table was widened without the caps being revisited — and
// the failure mode is a 400 from Telegram and no message at all, which looks like a quiet
// day. Better to see it in the log with the length attached.
const TELEGRAM_MAX = 4096;
if (post.length > TELEGRAM_MAX) {
  fail(`the digest came out at ${post.length} characters, over Telegram's `
       + `${TELEGRAM_MAX} — lower the caps in digest.js`);
}

if (OUT) writeFileSync(OUT, post);
if (JSON_OUT) {
  writeFileSync(JSON_OUT, JSON.stringify({
    post,
    rows: rows.length,
    days: DAYS,
    min_run: MIN_RUN,
    data_age_hours: age ?? null,
    generated_at: data?.generated_at ?? null,
  }, null, 2));
}

console.error(`digest: ${rows.length} streak rows on the board, ${post.length} characters`);
if (!OUT && !JSON_OUT) console.log(post);
