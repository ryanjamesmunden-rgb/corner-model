#!/usr/bin/env node
// Builds the scheduled X post as a DRAFT for review. It never posts anything.
//
// WHY A DRAFT. Posting straight to a timeline needs X API write credentials and puts a
// bad data day — a stalled sync, a mis-parsed fixture — in front of an audience with no
// one having looked. This writes the post to a GitHub issue instead, with a one-click
// intent link that opens X's composer already filled in. Nothing reaches anyone until a
// person clicks Post. That also means no developer app, no credentials, and no API cost.
//
// WHY NODE, in a Python repo. The share format lives in frontend/src/lib/shareText.js
// and is what the site's own share buttons render. Reimplementing it here in Python
// would be a second copy of the flag map, the kick-off format, the "+N more" tail and
// X's weighted character counting — four things that would drift apart quietly, and
// whose drift would show up as the automated post looking unlike the manual one. So the
// same modules are imported directly. They are plain ES modules with no React, no
// window and no fetch, which is what makes that possible.
//
// Usage:  node tools/social_draft.mjs --board streaks|fixtures|results|game|weekend|picks|menu|slip [--days 3]
//                                    [--tag YYYY-MM-DD] [--out draft.md]
//         node tools/social_draft.mjs --board slip [--rows 3] [--tag YYYY-MM-DD]
// Env:    BACKEND_URL (default the live Render backend), TOOLS_TOKEN (required)

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");

// The lib modules import each other by relative path and use no bundler features, so
// they load as-is. `shareText.js` pulls in countryFlag and kickoff itself.
const { streakShare, fixtureShare, streakResultShare, pickGame, pickGameDetailed, gameShare, cardPost,
        picksReview, angleMenu, PUBLIC_STREAK_ROWS } = await import(resolve(LIB, "shareText.js"));
const { fixtureStoryMarkets } = await import(resolve(LIB, "storyImage.js"));
const { kickoffLabel } = await import(resolve(LIB, "kickoff.js"));
const { fitToPost, weightedLength, xWeight, URL_WEIGHT, X_SHARE_ROWS } = await import(resolve(LIB, "xLimit.js"));
const { boardForDay } = await import(resolve(LIB, "postPlan.js"));
const { slipFrom, slipPost, dayKey } = await import(resolve(LIB, "dailySlip.js"));
const { slateFrom, slatePost } = await import(resolve(LIB, "chaseSlate.js"));
const { streakFinder, liveDrop, finderWindow } = await import(resolve(LIB, "streakFinder.js"));
const { tweetStat } = await import(resolve(LIB, "tweetStat.js"));
const { tweetStats } = await import(resolve(LIB, "tweetStats.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

// `--board auto --weekday 4` asks the plan what today is for. The rotation lives in
// lib/postPlan.js, where it is tested — a case statement in the workflow's bash could only
// be checked by pushing it and waiting until Thursday.
const WEEKDAY = arg("weekday", null);
const planned = WEEKDAY ? boardForDay(WEEKDAY) : null;
const BOARD = arg("board", "streaks") === "auto" ? (planned?.board ?? "streaks") : arg("board", "streaks");
const TAG = arg("tag", null);
// THE FINDER ASKS FOR ITS OWN WINDOW, because the fetch happens before any board runs.
//
// FOUND ON THE FIRST REAL RUN, and it is the quietest failure in this file: at the default
// of 3 the backend returns streaks kicking off within three days, the finder then filters
// those to its Friday-to-Monday window, and the result is an empty post on a board full of
// runs — reported as "no streaks clear the bar", which is indistinguishable from a genuinely
// quiet week. A window the CALLER applies has to be reflected in what is ASKED FOR.
//
// 8 is the furthest any drop reaches (+7) plus today. The limit goes up with it: over eight
// days the backend's own top 60 can be spent on games outside the window before the
// finder's twenty are reached.
const FINDER_DAYS = 8;
const FINDER_LIMIT = 200;
const DEFAULT_DAYS = BOARD === "finder" ? FINDER_DAYS : (planned?.days ?? 3);
const DAYS = Number(arg("days", null) ?? DEFAULT_DAYS);
const OUT = arg("out", null);
// The post on its own, as JSON, for a caller that is going to deliver it somewhere other
// than a GitHub issue — the daily job sends it to Telegram with a one-tap post button.
const JSON_OUT = arg("json-out", null);
// THE DOMAIN PEOPLE ARE MEANT TO LAND ON. This defaulted to the Vercel deployment URL,
// which is the address the host happens to serve from rather than the address the site is
// called — so every posted tweet advertised corner-model.vercel.app. It sends the wrong
// signal on a post whose whole job is to look like a place worth visiting, and it ties
// every link already published to one particular host.
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const TOKEN = process.env.TOOLS_TOKEN;

// A post is public and permanent in a way a stale screen is not, so a draft built from
// old numbers is worse than no draft: it reads exactly like a good one.
const MAX_DATA_AGE_HOURS = 14;   // a little over the 12h sync cadence
const MIN_ROWS = 3;              // fewer than this is a quiet day, not a post

// TWO ATTEMPTS, AND A LONGER ONE SECOND.
//
// This had a single 60-second try, and when the backend crept past it the daily post
// simply stopped — two days running, with "timed out after 60s" as the only evidence and
// no way to tell a slow instance from a dead one. One attempt is a coin toss on a
// free-tier host whose own docstring says these boards walk every team in the database.
//
// The retry is NOT the fix for a slow endpoint: it buys the post while the cause is
// measured (see `timings_ms`, printed below). A second attempt also costs nothing on the
// common path, because it only happens after a failure.
const FETCH_MS = [60000, 120000];

const get = async (path, label) => {
  for (let i = 0; i < FETCH_MS.length; i++) {
    const last = i === FETCH_MS.length - 1;
    try {
      return await getOnce(path, label, FETCH_MS[i], last);
    } catch (err) {
      if (last) throw err;
      console.error(`social_draft: attempt ${i + 1} failed (${err.message}) — retrying `
                    + `with ${FETCH_MS[i + 1] / 1000}s`);
    }
  }
};

const getOnce = async (path, label, ms, fatal) => {
  let res;
  try {
    res = await fetch(`${BACKEND}${path}`, { signal: AbortSignal.timeout(ms) });
  } catch (err) {
    // Timeout or network. Worth another go with a longer rope — unless this was the
    // last one, in which case say so with the limit that was actually applied rather
    // than a hardcoded 60 that stops being true the moment the retry widens it.
    const what = err.name === "TimeoutError"
      ? `timed out after ${ms / 1000}s` : err.message;
    if (!fatal) throw new Error(what);
    fail(`could not reach ${BACKEND} — ${what}`);
  }
  if (res.status === 404) return null;        // the caller decides whether that is fatal

  // CONFIG ERRORS ARE FATAL ON THE FIRST ATTEMPT, never retried. A bad or missing token
  // answers identically however many times it is asked, so retrying only doubles the wait
  // before the same message — and buries it under a "retrying" line that implies the
  // problem might be transient. It is not; it needs a person to change a secret.
  if (res.status === 503) {
    fail("backend has no TOOLS_TOKEN set in its own environment — set it on Render, "
         + "then set the matching GitHub repo secret");
  }
  if (res.status === 403) {
    fail("backend rejected the token — the TOOLS_TOKEN repo secret does not match the backend env");
  }
  if (!res.ok) {
    const what = `${label} returned ${res.status} ${res.statusText}`;
    if (!fatal) throw new Error(what);        // a 5xx may well be the instance struggling
    fail(what);
  }
  return await res.json();
};

/** Like get, but a failure is NOT fatal.
 *
 * For things the post is better with and fine without — the picture, so far. `get` exits
 * the process on any non-404, which is right when the fetch IS the post and catastrophic
 * when it is the decoration: a 500 on the fixture endpoint would take down a text post
 * that was already built and correct. */
const getSoft = async (path) => {
  try {
    const res = await fetch(`${BACKEND}${path}`, { signal: AbortSignal.timeout(45000) });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
};

const fail = (msg) => { console.error(`social_draft: ${msg}`); process.exit(1); };
// A quiet day is not a failure — it exits 0 with no draft, and the workflow posts nothing.
const skip = (msg) => { console.log(`SKIP: ${msg}`); writeIfAsked(""); process.exit(0); };

function writeIfAsked(body) {
  if (OUT) writeFileSync(OUT, body);
  // An empty body means "nothing to post today", and the JSON has to say so too — a
  // stale draft.json left over from yesterday's run would otherwise be delivered again
  // as if it were today's.
  if (JSON_OUT && !body) writeFileSync(JSON_OUT, JSON.stringify({ empty: true }));
}

/** The finished draft: to the file the workflow reads, or to stdout when run by hand. */
function emit(body, payload = null) {
  writeIfAsked(body);
  if (JSON_OUT && payload) writeFileSync(JSON_OUT, JSON.stringify(payload));
  if (!OUT && !JSON_OUT) console.log(body);
}

if (!TOKEN) fail("TOOLS_TOKEN is not set — add it as a repo secret");

// ---- picks: the angles actually posted to the channel, and how they went.
//
// /api/results USED to be the one open endpoint here. It went behind a free account, and
// this job holds no session — so it reads it with the tools token, which is exactly why
// that token path exists on the endpoint. Without it Monday would 401, fall silently down
// its fallback chain to results and then streaks, and nothing in the log would say why the
// picks review stopped happening.
//
// Still this rather than the members-only bets board: that board is other people's
// betting; this is the record of what was claimed here, in advance.
if (BOARD === "picks") {
  const r = await getSoft(`/api/results?token=${encodeURIComponent(TOKEN)}`);
  if (!r) skip("could not read the public record — nothing to review");
  // CLAIMED ONLY. The backend splits posted angles by a server-clock stamp taken at the
  // moment they were logged; `recalled` is the ones added after kick-off. Both are
  // published on the site, and only the first can count towards a rate.
  const rows = r.posted?.claimed?.rows || [];
  const build = picksReview({ rows });
  const post = fitToPost(build, X_SHARE_ROWS);
  if (!post) skip("no channel picks settled in the last week");
  const full = build(12);
  const weight = weightedLength(post) + 1 + URL_WEIGHT;
  const intent = `https://x.com/intent/tweet?text=${encodeURIComponent(post)}&url=${encodeURIComponent(SITE)}`;
  const t = r.posted?.claimed || {};
  emit(`**[Post this on X](${intent})** — opens the composer already filled in. Nothing is posted until you hit Post.

\`\`\`
${post}
\`\`\`

${weight} / 280 characters as X counts them.
All time on the record: ${t.landed ?? "—"} landed of ${t.settled ?? "—"} settled${
  t.voided ? `, ${t.voided} void` : ""}${t.pending ? `, ${t.pending} still to settle` : ""}.
Only angles logged BEFORE kick-off appear — see /api/results.

<details><summary>Longer version, for Telegram (no character limit)</summary>

\`\`\`
${full}
\`\`\`

</details>
`, { empty: false, board: "picks", post, intent, weight, full,
     note: `${t.landed ?? "—"}/${t.settled ?? "—"} on the record all time` });
  process.exit(0);
}

// ---- results: graded off the snapshot frozen before kick-off, never off the live board.
// A streak row only exists while its run is alive, so the board on Monday lists the
// survivors and nothing else. See /api/streaks/snapshot.
if (BOARD === "results") {
  if (!TAG) fail("--board results needs --tag YYYY-MM-DD (the Friday it was frozen)");
  const r = await get(`/api/streaks/snapshot/${TAG}/results?token=${encodeURIComponent(TOKEN)}`,
                      "snapshot results");
  // No snapshot is a fact about last Friday, and Monday cannot fix it. Worth a line in
  // the log, not a red run.
  if (!r) skip(`no snapshot tagged ${TAG} — nothing was frozen that day, so nothing can be graded`);
  if (r.settled < MIN_ROWS) {
    skip(`only ${r.settled} of ${r.results.length} settled so far — too few to post a week on`);
  }
  const build = streakResultShare(r);
  const post = fitToPost(build, X_SHARE_ROWS);
  const full = build(8);
  const weight = weightedLength(post) + 1 + URL_WEIGHT;
  const intent = `https://x.com/intent/tweet?text=${encodeURIComponent(post)}&url=${encodeURIComponent(SITE)}`;
  emit(`**[Post this on X](${intent})** — opens the composer already filled in. Nothing is posted until you hit Post.

\`\`\`
${post}
\`\`\`

${weight} / 280 characters as X counts them.
Graded from the snapshot frozen on ${TAG}: ${r.landed} landed, ${r.missed} missed${r.voided ? `, ${r.voided} void` : ""}${r.pending ? `, ${r.pending} still to settle` : ""}.
No line and no stake appear in this post — see streakResultShare.

<details><summary>Longer version, for Telegram (no character limit)</summary>

\`\`\`
${full}
\`\`\`

</details>
`, { empty: false, board: "results", post, intent, weight, full,
     note: `${r.landed} landed, ${r.missed} missed, graded off the ${TAG} snapshot` });
  process.exit(0);
}

// ---- the card, built from the SAME endpoint the site's panel renders.
//
// IT USED TO BE BUILT FROM /api/share/rows AND A --days WINDOW, and that is how the card
// in the channel and the card on the site drifted into being different cards. The site
// asks angle_of_day which card is live and what dates it covers; the channel post scanned
// "three days from now" and rendered whatever came back. On a Wednesday those are not the
// same set: the weekend card covers Friday to Monday, so a three-day scan could not reach
// Sunday or Monday at all, while Thursday's games — which belong to the MIDWEEK card —
// were eligible for it.
//
// Keeping two windows in step by hand is the bug, not the fix. This asks the one place
// that already knows, so the channel cannot disagree with the site about which games are
// on the card or what the card is called.
//
// IT IS ALSO MUCH CHEAPER. /api/angles/card serves a precomputed screen; share/rows walks
// every team in the database and is the call that has been timing out.
if (BOARD === "card") {
  // `--count` is optional and deliberately not defaulted here: blank means the backend's
  // own COUNT, which is what the schedule publishes and what the site shows. Putting a
  // number in this file would be a second opinion about how big a card is.
  const n = arg("count", null);
  const a = await get(`/api/angles/card?token=${encodeURIComponent(TOKEN)}`
    + (n ? `&count=${encodeURIComponent(n)}` : ""), "angles");
  if (!a) fail("backend has no /api/angles/card — it is running an older build");
  // The backend decides whether today has a card worth publishing, including refusing on
  // stale data. Repeating that judgement here would be a second opinion that can differ.
  if (a.dead) skip(`${a.label || "card"}: ${a.note || a.reason || "nothing qualifies"}`);
  const card = cardPost({ rows: a.angles || [], generatedAt: new Date().toISOString(),
                          site: SITE, label: a.label || "" });
  if (!card) skip(`${a.label || "card"}: nothing cleared the bar`);
  emit(`${a.label} card for the channel — not for X.

\`\`\`
${card}
\`\`\`
`, { empty: false, board: "card", post: card, intent: "", weight: card.length, full: card,
     note: `${(a.angles || []).length} angles · covers ${a.covers?.first} to ${a.covers?.last}`
           + `${a.data_age_hours != null ? ` · data ${a.data_age_hours}h old` : ""}` });
  process.exit(0);
}

// ---- the live boards.
// Render sleeps the free instance, so the first call after a quiet spell can take a
// while or fail outright. A crash here would surface in CI as a raw stack trace with
// the token in the URL; catching it keeps the failure readable and the secret out of
// the log.
// limit=60 rather than the default 12: the game post advertises how many OTHER angles are
// live, and a page of twelve would under-report that by however many it cut off.
// The menu is the only board that reads all four. The other three boards walk every team
// in the database, so asking for them on a Tuesday game post would make it pay for work it
// never reads — on a free-tier backend that is the difference between a post and a timeout.
const BOARDS = BOARD === "menu" ? "streaks,mismatches,chase,value"
  : BOARD === "chase" ? "chase"
  // The finder is streaks and nothing else. Asking for `fixtures` alongside would make it
  // pay for a board it never reads, and on a free-tier backend that is the difference
  // between a post and a timeout.
  : BOARD === "finder" ? "streaks"
  // THE STAT BOARD NOW READS TWO. It was `streaks` alone when it produced one post about
  // one board; it offers several candidates now, and the mismatch one is the only angle
  // here that is not another cut of the same rows. Still not `fixtures` or `value`: it
  // reads neither, and every extra board walks the whole team collection.
  : BOARD === "stat" ? "streaks,mismatches"
  : "streaks,fixtures";
const data = await get(`/api/share/rows?days=${DAYS}`
  + `&limit=${BOARD === "finder" ? FINDER_LIMIT : 60}&boards=${BOARDS}`
  + `&token=${encodeURIComponent(TOKEN)}`, "backend");
if (!data) fail("backend has no /api/share/rows — it is running an older build");

// WHERE THE TIME WENT, printed on every run rather than only on a slow one.
//
// This endpoint began exceeding the fetch timeout and the log could say nothing except
// that it had. Printing the breakdown only past some threshold would mean the run that
// finally fails is the first one with no baseline to compare against — so it goes out
// every time, and the number that matters is the one that grew.
if (data.timings_ms && Object.keys(data.timings_ms).length) {
  const parts = Object.entries(data.timings_ms)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${k} ${(v / 1000).toFixed(1)}s`);
  const total = Object.values(data.timings_ms).reduce((a, b) => a + b, 0);
  console.error(`social_draft: backend spent ${(total / 1000).toFixed(1)}s — ${parts.join(", ")}`);
}
// FastAPI ignores a query parameter it does not know, so an older backend answers a menu
// request with streaks and fixtures and nothing else — and the menu would render with three
// empty sections, looking exactly like a quiet day. `boards` comes back only on a build that
// understood the ask, which is what makes that difference visible.
if (BOARD === "menu" && !data.boards) {
  fail("backend does not understand ?boards= — it is running a build from before the angle "
       + "menu, and would answer with streaks only");
}

if (data.data_age_hours != null && data.data_age_hours > MAX_DATA_AGE_HOURS) {
  skip(`data is ${data.data_age_hours}h old (limit ${MAX_DATA_AGE_HOURS}h) — not drafting from stale numbers`);
}

// ---- the chase board for a day: ten spots, each with the reason it is on the card.
//
// THIS REPLACED THE STREAK SLATE BELOW as the morning post, and the reason was a fair
// complaint: a streak row gives no context. "Kiel 5+ corners, eight in a row" is a fact
// about eight games already played and no argument at all about the next one. A chase row
// carries the argument — the team's corner average at this venue, what the opponent
// concedes at theirs, and how often this team has actually cleared the line there.
//
// IT IS ALSO THE ONLY SECTION WITH A MEASURED RECORD. Chase spots are auto-logged daily and
// graded; mismatches, value and the projections are not logged at all, so nothing says
// whether they pick winners. The ledger goes on the card's header, which is what lets the
// rest of it be checked rather than taken on trust.
if (BOARD === "chase") {
  // SOFT, because the record is worth having and the board is worth posting without it.
  // A 500 on the ledger must not cost the morning post that was already built and correct.
  const ledger = await getSoft("/api/ledger");
  const day = TAG || dayKey();
  const slate = slateFrom({ rows: data.chase || [], ledger, day,
                            max: Number(arg("rows", "10")) });
  if (!slate) skip(`fewer than three spots clear the bar on ${day} — no board worth posting`);
  const post = slatePost({ slate, site: SITE });
  const rec = slate.record;
  emit(`Today's chase board — ${slate.n} spots, each with its reason and a link.

\`\`\`
${post}
\`\`\`

${rec ? `Section record: ${rec.won} of ${rec.settled} settled${rec.rate === null ? "" : ` (${rec.rate}%)`}${
  rec.roi === null ? ", no prices logged so no units" : `, ${rec.profit > 0 ? "+" : ""}${rec.profit}u from ${rec.staked} priced`}.`
  : "No graded record yet — nothing has settled, so the card carries no claim."}
${slate.priced} of ${slate.n} rows carry a real price; the rest show the model's fair odds.
`, { empty: false, board: "chase", post, intent: "", weight: post.length, full: post,
     // The card is drawn from the SAME object the post was built from, so the graphic and
     // the text cannot disagree about what today's board is.
     slate,
     note: `${slate.n} chase spots on ${day}`
       + (slate.priced ? `, ${slate.priced} priced` : ", none priced")
       + (rec ? ` · section ${rec.won}/${rec.settled}` : "")
       + (data.data_age_hours != null ? ` · data ${data.data_age_hours}h old` : "") });
  process.exit(0);
}

// ---- the daily X post: SEVERAL statistics about the boards, not a list of rows.
//
// EVERY OTHER BOARD HERE HANDS OVER ROWS, because rows are what a member wants — they are
// the product. A public post has a different job: be interesting to somebody who has never
// heard of the site, in one screen, without giving away what people pay for. So these lead
// on numbers about the boards as a whole and send the reader to the page for the names.
//
// SEVERAL A DAY, NOT ONE. One post a day off one board is the same sentence with a
// different number in it, which is what people learn to scroll past. tweetStats builds a
// candidate per angle — the board's breadth, today's slice of it, the deep runs, the
// higher line, and the mismatch board — and every one of them is dropped rather than
// loosened when it cannot clear its own bar. So a quiet day costs candidates, not honesty.
//
// THE CHOICE STAYS WITH A PERSON. They all go out together with a Post button each; none
// of them posts by itself. Posting through X's API needs a paid tier, and the composer link
// is free, is one tap, and puts a human between a generated sentence and the timeline.
// See tweetStats.js for what the wording is and is not allowed to claim.
if (BOARD === "stat") {
  const built = tweetStats({ rows: data.streaks || [], mismatches: data.mismatches || [],
                             days: DAYS, site: SITE });
  // Not a failure. A board too quiet to be worth a statistic is a real answer, and the
  // alternative — loosening the bar until the number looks good — is how a daily post
  // stops meaning anything. See STAT_MIN_TEAMS.
  if (!built.length) {
    skip(`no board clears its own bar over ${DAYS} days — no statistic worth posting`);
  }
  const withIntent = built.map((c) => ({
    ...c, intent: `https://x.com/intent/tweet?text=${encodeURIComponent(c.text)}`,
  }));
  const md = withIntent.map((c, i) => `**${i + 1}. [Post this on X](${c.intent})** — \`${c.key}\`, ${c.weight}/280

\`\`\`
${c.text}
\`\`\`
`).join("\n");
  emit(`${withIntent.length} statistic${withIntent.length === 1 ? "" : "s"} today. Each link opens the composer already filled in; nothing is posted until you hit Post.

${md}`, { empty: false, board: "stat",
     // `post` and `intent` stay singular and point at the FIRST candidate, because the
     // Telegram step and the issue fallback both read those fields and neither should
     // silently start sending nothing when the shape changes underneath them.
     post: withIntent[0].text, intent: withIntent[0].intent,
     weight: withIntent[0].weight, full: withIntent[0].text,
     stats: withIntent.map(({ key, text, weight, intent, stats }) =>
       ({ key, text, weight, intent, stats })),
     note: `${withIntent.length} statistics over ${DAYS}d`
       + (data.data_age_hours != null ? ` \u00b7 data ${data.data_age_hours}h old` : "") });
  process.exit(0);
}

// ---- the streak finder: one line per team, sorted by line then by run.
//
// TWO DROPS A WEEK, AND EACH COVERS DAYS THE OTHER DOES NOT. Monday posts Friday to
// Monday; Thursday posts Tuesday to Thursday. Every day of the week belongs to exactly one
// of them — a day covered twice is a fixture claimed twice, and a day covered by neither is
// a night this channel never had a view on. The arithmetic lives in streakFinder.js so the
// windows cannot drift from the tests that check they tile the week.
//
// THE WINDOW IS TAKEN FROM THE DROP IN FORCE, WALKING BACK. Fired by hand on a Wednesday
// this carries Monday's weekend list, which is the one the channel is already expecting —
// not Thursday's midweek, for games that have not been selected yet. `--drop` overrides it
// for a deliberate off-schedule post.
//
// IT CARRIES MODEL PRICES, WHICH IS WHY IT CAN GO OUT DAYS AHEAD. A fair price exists the
// moment the fixture does, so this post does not wait for a book to put the game up — which
// is the whole point of a list you read to know where to look when the odds drop.
if (BOARD === "finder") {
  const today = TAG || dayKey();
  const live = liveDrop(today);
  const drop = arg("drop", null) || live?.drop;
  const publishedOn = arg("drop", null) ? today : live?.publishedOn;
  const w = finderWindow(drop, publishedOn);
  if (!w) fail(`no such drop ${drop} — expected weekend or midweek`);
  const built = streakFinder({ rows: data.streaks || [], site: SITE,
                               first: w.first, last: w.last,
                               max: Number(arg("rows", "20")) });
  // Not a failure. A window with no qualifying run is a quiet week, and the honest answer
  // is no post — the same card on an empty board teaches the reader to skim the next one.
  if (!built.text) {
    skip(`no streaks of ${w.first} to ${w.last} clear the bar — nothing worth posting`);
  }
  emit(`${w.label} streak finder — ${built.n} rows, ${w.first} to ${w.last}.

\`\`\`
${built.text}
\`\`\`

Model prices, not offers: these games are days away and no book has them up yet.
`, { empty: false, board: "finder", post: built.text, intent: "",
     weight: built.text.length, full: built.text,
     note: `${built.n} streak rows for ${w.label.toLowerCase()} (${w.first} to ${w.last})`
       + (data.data_age_hours != null ? ` · data ${data.data_age_hours}h old` : "") });
  process.exit(0);
}

// ---- the morning slate: today's games, as a card and a post with a link under each row.
//
// THE ONE BOARD THAT LOOKS ONE DAY AHEAD AND MEANS IT. Everything else here answers "what
// is interesting this week", which is the right question for a draft somebody will post
// when they get to it. A morning post answers "what is on today", and a row a reader cannot
// act on before lunchtime is a row that should not be on it.
//
// THE LINKS ARE WHY THIS IS NOT JUST AN IMAGE. A graphic is a claim you have to take on
// trust; the link under each row is the page with the distribution, the run, and every
// number the row was built from. It is also the only part of the post that can bring
// somebody back to the site.
if (BOARD === "slip") {
  const day = TAG || dayKey();
  const slip = slipFrom({ rows: data.streaks || [], day, max: Number(arg("rows", "3")) });
  // Not a failure. A morning with one playable angle on it is a quiet morning, and the card
  // for one is the same card the good days use, advertising that today is not one of them.
  //
  // The DAY is named rather than called "today", because --tag previews another one and a
  // skip line reading "today" while answering about tomorrow sends you looking for a bug in
  // the wrong place.
  if (!slip) skip(`fewer than two angles kick off on ${day} — nothing worth a slate`);
  const post = slipPost({ slip, site: SITE });
  emit(`Today's slate — ${slip.n} ${slip.label.toLowerCase()}, with a link under each.

\`\`\`
${post}
\`\`\`

${slip.priced} of ${slip.n} carry a real price; the rest show the model's fair odds, which
the card labels and the post says once at the bottom.
`, { empty: false, board: "slip", post, intent: "", weight: post.length, full: post,
     // The card is drawn from the SAME object the post was built from, so the graphic and
     // the text cannot disagree about what today's games are.
     slip,
     note: `${slip.n} ${slip.label.toLowerCase()} today`
       + (slip.priced ? `, ${slip.priced} priced` : ", none priced yet")
       + (data.data_age_hours != null ? ` · data ${data.data_age_hours}h old` : "") });
  process.exit(0);
}

// ---- the menu. NOT A POST — it goes to whoever is running the account, and it is the one
// message here whose job is to be chosen from rather than published.
//
// The daily job used to hand over one streak. A streak on its own is the weakest angle the
// site finds: it says what a team keeps doing and nothing about who they play, what the game
// will look like, or what the price is. This offers all four readings, numbered, and a person
// picks. See angleMenu.
if (BOARD === "menu") {
  const { text, items } = angleMenu({
    streaks: data.streaks || [], mismatches: data.mismatches || [],
    chase: data.chase || [], value: data.value || [],
    generatedAt: data.generated_at, site: SITE,
  });
  if (!items.length) skip("nothing on any of the four boards — no menu to send");

  // HAND THE NUMBERED ROWS TO THE BACKEND, or a reply of "3" resolves to nothing.
  //
  // The menu is built here, in Node, because the share format has exactly one definition
  // and it lives in shareText.js. The bot that answers a reply is Python. So the rows are
  // handed over rather than recomputed — and recomputing would be wrong anyway: the board
  // moves, and "3" has to mean the row numbered 3 in the message that was actually sent.
  const num = (r) => {
    const n = Number(r);
    return Number.isFinite(n) ? n : null;
  };
  const menuItems = items.map((i) => {
    const r = i.row || {};
    const nf = r.next_fixture || {};
    // The three board shapes name their line differently. A streak carries `line` and
    // `direction`; a mismatch and a chase spot carry a bare `line` that is always an over;
    // a value row is about a market rather than a team and cannot be logged as an angle,
    // so it goes over with no line and the backend refuses it rather than guessing.
    return {
      n: i.n, kind: i.kind, team: r.name || "", headline: i.headline || "",
      line: num(r.line), direction: r.direction || "over",
      subject: r.subject || "team",
      opponent: nf.opponent || "", is_home: nf.is_home ?? null,
      kickoff: nf.date || r.date || null,
      fixture_id: i.fixtureId || null, league_id: r.league_id || null,
      prob: num(r.prob ?? r.projection?.prob),
    };
  });
  // THE CHAT IS CHECKED BEFORE THE CALL, not left to the backend. A menu is stored under
  // the chat it was sent to, and an absent TG_CHAT would key it to "" — a row nothing can
  // ever match, written and accepted without complaint. That is exactly what happened on a
  // hand-fired `board: menu`, where the step building the menu had no TG_CHAT in its env:
  // the message arrived, the store reported success, and replying to it said "I haven't
  // sent you a menu yet". A missing chat is a configuration fault, so it is named as one.
  const chat = String(process.env.TG_CHAT || "").trim();
  const stored = !chat ? null : await fetch(
    `${BACKEND}/api/telegram/menu?token=${encodeURIComponent(TOKEN)}`,
    { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ chat_id: chat, items: menuItems }),
      signal: AbortSignal.timeout(30000) }).catch(() => null);
  // NOT FATAL. The menu is worth sending even when the reply handler cannot be armed —
  // it is a list to read as well as a list to answer. But it is worth saying in the log,
  // because "I replied 3 and nothing happened" is otherwise unexplainable.
  if (!chat) {
    console.log("::warning::TG_CHAT is not set for this step — the menu cannot be stored"
      + " against a chat, so replying with a number will not resolve");
  } else if (!stored || !stored.ok) {
    console.log(`::warning::could not store the menu (${stored ? stored.status : "unreachable"})`
      + " — replying with a number will not resolve");
  }
  const counts = ["streak", "mismatch", "chase", "value"]
    .map((k) => `${items.filter((i) => i.kind === k).length} ${k}`).join(", ");
  emit(`Angle menu — for you, not for posting.

\`\`\`
${text}
\`\`\`
`, { empty: false, board: "menu", post: text, intent: "", weight: text.length, full: text,
     note: `${items.length} angles to choose from: ${counts}${
       data.data_age_hours != null ? ` · data ${data.data_age_hours}h old` : ""}` });
  process.exit(0);
}

// ---- the weekend card. Goes to the PAID channel on a Friday, carrying the model's own
// numbers, so a member sees Sunday's games while the price is still there rather than on
// Sunday morning when it is not. Never trimmed and never posted to X — see cardPost.
if (BOARD === "weekend") {
  const card = cardPost({ rows: data.streaks || [], generatedAt: data.generated_at,
                             site: SITE });
  if (!card) skip("nothing with a live run kicks off this weekend");
  emit(`Weekend card for the channel — not for X.

\`\`\`
${card}
\`\`\`
`, { empty: false, board: "weekend", post: card, intent: "", weight: card.length, full: card,
     note: `${(data.streaks || []).length} rows${
       data.data_age_hours != null ? ` · data ${data.data_age_hours}h old` : ""}` });
  process.exit(0);
}

// ---- one game, posted whole. A board is a list; this is a game, and it gets three lines
// to say when it is, who is playing and why it is worth a look. See gameShare.
if (BOARD === "game") {
  // VALUE FIRST where a real price exists, form only when none does. `basis` says which,
  // so the note can be honest about it rather than letting a confidence ranking read as a
  // value one — see pickGameDetailed.
  const { row, basis } = pickGameDetailed(data.streaks || []);
  if (!row) skip("no game today carries a run worth posting on its own");
  // EVERY OTHER ANGLE ON THE SITE, not what this post trimmed. The post shows one game;
  // the reason to click is all the ones it is not showing.
  const more = Math.max(0, (data.streaks || []).length - 1);
  const post = gameShare({ row, more, site: SITE })();
  if (!post) skip("the best row has no fixture attached — nothing to post about");

  // THE PICTURE, built from the same fixture the text is about.
  //
  // A separate call, because the board rows carry no probability CURVE — only the single
  // number for their own line. The curve is what makes the image worth looking at, and it
  // lives on the fixture endpoint, which is public: no token, and a failure here must not
  // cost the post, so it degrades to text rather than throwing.
  let story = null;
  const fid = row.next_fixture?.fixture_id;
  if (fid) {
    const detail = await getSoft(`/api/fixtures/${encodeURIComponent(fid)}`);
    const dists = detail?.model?.distribution;
    // The group the ANGLE is about — a home-corners streak should not draw the match
    // total's curve underneath it.
    const group = String(row.projection?.market_key || "total").split("_")[0];
    const dist = dists?.[group] || dists?.total;
    if (dist?.length) {
      story = {
        homeName: detail.fixture?.home_name || "",
        awayName: detail.fixture?.away_name || "",
        leagueId: detail.fixture?.league_id || row.league_id || "",
        kickoff: kickoffLabel(detail.fixture?.date || row.next_fixture?.date),
        dist, group: dists?.[group] ? group : "total",
        markets: fixtureStoryMarkets(detail.model?.markets || [], detail.model?.lambdas || {},
          { homeName: detail.fixture?.home_name, awayName: detail.fixture?.away_name }),
      };
    }
  }
  // NO &url= HERE. The post already ends on the link, and the intent parameter would put
  // a second copy of the same address underneath it.
  //
  // xWeight, NOT weightedLength, and the old comment here had it backwards: it claimed
  // weightedLength "already charges the flat t.co weight", which it does not — it is a
  // character weigher and charged this address its full 26. The figure printed beside a
  // draft was a few over what X counts, which is exactly the number somebody checks against
  // X's own composer before editing.
  const weight = xWeight(post);
  const intent = `https://x.com/intent/tweet?text=${encodeURIComponent(post)}`;
  const prob = row.projection?.prob;
  emit(`**[Post this on X](${intent})** — opens the composer already filled in. Nothing is posted until you hit Post.

\`\`\`
${post}
\`\`\`

${weight} / 280 characters as X counts them.
Chosen on ${basis === "value" ? "VALUE — the biggest edge over a price you typed in"
  : "FORM — no bookmaker price stored, so this is the model's confidence, NOT value"}.
${row.name} ${row.line_label}: ${row.streak?.length} in a row, model ${prob ?? "—"}%${
  row.projection?.fair_odds ? ` (fair ${row.projection.fair_odds})` : ""}${
  data.data_age_hours != null ? `, on data ${data.data_age_hours}h old` : ""}.
No price appears in this post — see gameShare.
`, { empty: false, board: "game", post, intent, weight, full: post, story,
     note: `${row.name} ${row.line_label} · ${row.streak?.length} in a row · model ${prob ?? "—"}%`
       + (basis === "value"
           ? ` · picked on VALUE, EV ${row.projection?.ev > 0 ? "+" : ""}${row.projection?.ev}%`
           : " · picked on form — no real price to measure value against") });
  process.exit(0);
}

const build = BOARD === "fixtures"
  ? fixtureShare({ fixtures: data.fixtures || [], days: String(DAYS) })
  : streakShare({ rows: data.streaks || [], subject: "team", side: "overall" });

// How many rows actually survived the trim, for the note under the draft. Counted by what
// opens a row — a flag or the bullet that stands in for one — rather than by punctuation
// inside it: this used to look for "·" or "(9", which both vanished from a streak row when
// the kick-off and the (5/5) came out, and the note would have quietly reported zero rows.
const countRows = (text) =>
  text.split("\n").filter((l) => /^(\p{Regional_Indicator}{2}|\u{1F3F4}[\u{E0000}-\u{E007F}]+|•)\s/u.test(l)).length;

const rowCount = (BOARD === "fixtures" ? data.fixtures : data.streaks || []).length;
if (rowCount < MIN_ROWS) skip(`only ${rowCount} rows cleared the bar — nothing worth posting`);

// FIVE STREAKS, NOT SIX — and the cap is a product decision, not a formatting one. A free
// post that lists every run on the board leaves the channel with nothing to sell: a member
// is paying for the rest of the list, the price beside it, and the reasoning under it. The X
// version is capped tighter still by the character limit; this is the Telegram one, which
// has no limit and therefore no natural brake. See PUBLIC_STREAK_ROWS.
const full = build(BOARD === "fixtures" ? 8 : PUBLIC_STREAK_ROWS);
const post = fitToPost(build, X_SHARE_ROWS);
const weight = weightedLength(post) + 1 + URL_WEIGHT;
const intent = `https://x.com/intent/tweet?text=${encodeURIComponent(post)}&url=${encodeURIComponent(SITE)}`;

const body = `**[Post this on X](${intent})** — opens the composer already filled in. Nothing is posted until you hit Post.

\`\`\`
${post}
\`\`\`

${weight} / 280 characters as X counts them (flags cost 2 each; the link is a flat ${URL_WEIGHT}).
Trimmed to ${countRows(post)} rows from ${rowCount} that cleared the bar${data.data_age_hours != null ? `, on data ${data.data_age_hours}h old` : ""}.

<details><summary>Longer version, for Telegram (no character limit)</summary>

\`\`\`
${full}
\`\`\`

</details>
`;

emit(body, {
  empty: false, board: BOARD, post, intent, weight, full,
  note: `${countRows(post)} of ${rowCount} rows`
    + (data.data_age_hours != null ? `, data ${data.data_age_hours}h old` : ""),
});
