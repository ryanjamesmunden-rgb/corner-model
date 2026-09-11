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
// Usage:  node tools/social_draft.mjs --board streaks|fixtures|results [--days 3]
//                                    [--tag YYYY-MM-DD] [--out draft.md]
// Env:    BACKEND_URL (default the live Render backend), TOOLS_TOKEN (required)

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");

// The lib modules import each other by relative path and use no bundler features, so
// they load as-is. `shareText.js` pulls in countryFlag and kickoff itself.
const { streakShare, fixtureShare, streakResultShare, pickGame, gameShare, weekendCard,
        picksReview } = await import(resolve(LIB, "shareText.js"));
const { fixtureStoryMarkets } = await import(resolve(LIB, "storyImage.js"));
const { kickoffLabel } = await import(resolve(LIB, "kickoff.js"));
const { fitToPost, weightedLength, URL_WEIGHT, X_SHARE_ROWS } = await import(resolve(LIB, "xLimit.js"));
const { boardForDay } = await import(resolve(LIB, "postPlan.js"));

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
const DAYS = Number(arg("days", null) ?? planned?.days ?? 3);
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

const get = async (path, label) => {
  try {
    const res = await fetch(`${BACKEND}${path}`, { signal: AbortSignal.timeout(60000) });
    if (res.status === 404) return null;      // the caller decides whether that is fatal
    if (!res.ok) {
      // 503 from a gated endpoint is a CONFIG error, not an outage: _check_tools_token
      // raises it when the backend has no TOOLS_TOKEN at all. Left as a bare status it
      // reads as "Render is down" and sends you to the wrong dashboard.
      if (res.status === 503) {
        fail("backend has no TOOLS_TOKEN set in its own environment — set it on Render, "
             + "then set the matching GitHub repo secret");
      }
      fail(res.status === 403
        ? "backend rejected the token — the TOOLS_TOKEN repo secret does not match the backend env"
        : `${label} returned ${res.status} ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    fail(`could not reach ${BACKEND} — ${err.name === "TimeoutError" ? "timed out after 60s" : err.message}`);
  }
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
// /api/results is the one OPEN endpoint on the site — no token — because it is the
// evidence the product works, and evidence behind a login persuades nobody. Same reason
// this reads it rather than the members-only bets board: that board is other people's
// betting; this is the record of what was claimed here, in advance.
if (BOARD === "picks") {
  const r = await getSoft("/api/results");
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

// ---- the live boards.
// Render sleeps the free instance, so the first call after a quiet spell can take a
// while or fail outright. A crash here would surface in CI as a raw stack trace with
// the token in the URL; catching it keeps the failure readable and the secret out of
// the log.
const data = await get(`/api/share/rows?days=${DAYS}&token=${encodeURIComponent(TOKEN)}`, "backend");
if (!data) fail("backend has no /api/share/rows — it is running an older build");

if (data.data_age_hours != null && data.data_age_hours > MAX_DATA_AGE_HOURS) {
  skip(`data is ${data.data_age_hours}h old (limit ${MAX_DATA_AGE_HOURS}h) — not drafting from stale numbers`);
}

// ---- the weekend card. Goes to the PAID channel on a Friday, carrying the model's own
// numbers, so a member sees Sunday's games while the price is still there rather than on
// Sunday morning when it is not. Never trimmed and never posted to X — see weekendCard.
if (BOARD === "weekend") {
  const card = weekendCard({ rows: data.streaks || [], generatedAt: data.generated_at });
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
  const row = pickGame(data.streaks || []);
  if (!row) skip("no game today carries a run worth posting on its own");
  const post = gameShare({ row })();
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
  const weight = weightedLength(post) + 1 + URL_WEIGHT;
  const intent = `https://x.com/intent/tweet?text=${encodeURIComponent(post)}&url=${encodeURIComponent(SITE)}`;
  const prob = row.projection?.prob;
  emit(`**[Post this on X](${intent})** — opens the composer already filled in. Nothing is posted until you hit Post.

\`\`\`
${post}
\`\`\`

${weight} / 280 characters as X counts them.
${row.name} ${row.line_label}: ${row.streak?.length} in a row, model ${prob ?? "—"}%${
  row.projection?.fair_odds ? ` (fair ${row.projection.fair_odds})` : ""}${
  data.data_age_hours != null ? `, on data ${data.data_age_hours}h old` : ""}.
No price appears in this post — see gameShare.
`, { empty: false, board: "game", post, intent, weight, full: post, story,
     note: `${row.name} ${row.line_label} · ${row.streak?.length} in a row · model ${prob ?? "—"}%` });
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

const full = build(BOARD === "fixtures" ? 8 : 6);
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
