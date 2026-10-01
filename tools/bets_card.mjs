#!/usr/bin/env node
// Today's bets: fetch the day's frozen slips, build the card and the post, write both.
//
// WHY ITS OWN TOOL rather than another board in social_draft.mjs. Every board in that file
// is a SELECTION made at post time — the streaks worth showing, the ten best chase spots,
// the day's slate. This one selects nothing. The backend freezes the day's bets before
// kick-off and this draws whatever was frozen, losers included, because a card that chose
// its rows after the results were in would be a different kind of object entirely. Keeping
// that separation in two files rather than one flag makes it hard to blur by accident.
//
// IT FETCHES AND THEREFORE IT FREEZES. /api/share/bets writes the day's picks into the
// ledger as it answers, so there is no path by which something is published and not
// recorded. `--preview` passes freeze=false for a run that must not create a record.
//
// WHY NODE, in a Python repo: the card's rules live in frontend/src/lib/betsCard.js, which
// the renderer and any future screen share. A second copy here in Python would drift, and
// the drift would be about what the account publicly claims it won.
//
// ONE CARD PER DAY, AND ONLY MORE THAN ONE WHEN TODAY IS QUIET. `--days` asks the backend
// to look forward, and it looks forward only when today has nothing: today's prices can
// still be taken, so a day with bets on it is never buried under tomorrow's. Each day that
// does come back gets its own card, because they settle on different evenings and one
// card mixing two days could not carry a day's result.
//
// Usage:  node tools/bets_card.mjs [--day YYYY-MM-DD] [--days 1] [--min-ev 0] [--rows 6]
//                                  [--preview] [--json-out bets.json]
//                                  [--args-prefix card_args]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (required)
//
// Exit status is 0 on a quiet day. `empty: true` in the JSON says there was nothing to
// post — no price typed in, or nothing clearing the floor — and the caller posts nothing.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { cardFrom, cardPost, MAX_CARD_ROWS } = await import(resolve(LIB, "betsCard.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const flag = (name) => process.argv.includes(`--${name}`);

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const TOKEN = process.env.TOOLS_TOKEN;
const DAY = arg("day", null);
const MIN_EV = Number(arg("min-ev", "0"));
const ROWS = Number(arg("rows", String(MAX_CARD_ROWS)));
const DAYS = Number(arg("days", "1"));
const JSON_OUT = arg("json-out", "bets.json");
// One file per card. A day is its own card (they settle on different evenings), so this
// is a prefix rather than a filename: card_args_1.json, card_args_2.json, ...
const ARGS_PREFIX = arg("args-prefix", "card_args");
const HEADING = arg("heading", null);

const fail = (m) => { console.error(`bets_card: ${m}`); process.exit(1); };
if (!TOKEN) fail("TOOLS_TOKEN is required");

// TWO ATTEMPTS, THE SECOND LONGER. The backend sleeps on the free tier and this endpoint
// settles pending bets on the way through, so a first call creeping past a minute is a
// slow instance rather than a dead one — the same reasoning social_draft.mjs sets out.
const FETCH_MS = [60000, 120000];

const params = new URLSearchParams({
  token: TOKEN,
  min_ev: String(MIN_EV),
  count: String(ROWS),
  days: String(DAYS),
  freeze: flag("preview") ? "false" : "true",
});
if (DAY) params.set("day", DAY);

// WHAT A 4xx MEANS HERE, since retrying one is pure delay: 404 is the backend not having
// deployed this endpoint yet, 403 is a bad token, 503 is TOOLS_TOKEN unset on the backend.
// None of them changes between two attempts a second apart, and the first real run spent
// its retry discovering a 404 twice before reporting it.
const ADVICE = {
  404: "the backend has not deployed /api/share/bets yet — wait for Render and run again",
  403: "TOOLS_TOKEN does not match the backend's",
  503: "TOOLS_TOKEN is not set on the backend, so the tool endpoints are disabled",
};

const get = async () => {
  for (let i = 0; i < FETCH_MS.length; i++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), FETCH_MS[i]);
    try {
      const res = await fetch(`${BACKEND}/api/share/bets?${params}`, { signal: ctl.signal });
      if (!res.ok) {
        // The body carries FastAPI's `detail`, which separates "bad token" from
        // "tool endpoints are disabled" — two different things to go and fix.
        const body = await res.text().catch(() => "");
        if (res.status < 500 && res.status !== 408 && res.status !== 429) {
          fail(`HTTP ${res.status} — ${ADVICE[res.status] || body.slice(0, 200)}`);
        }
        throw new Error(`HTTP ${res.status} ${body.slice(0, 200)}`);
      }
      return await res.json();
    } catch (err) {
      if (i === FETCH_MS.length - 1) fail(`could not reach the backend — ${err.message}`);
      console.error(`bets_card: attempt ${i + 1} failed (${err.message}) — retrying`);
    } finally {
      clearTimeout(timer);
    }
  }
  return null;
};

const data = await get();
const cards = [];

for (const entry of data.cards || []) {
  const card = cardFrom({
    rows: entry.rows || [], day: entry.day, summary: data, max: ROWS,
  });
  if (!card) continue;
  // THE HEADING FOLLOWS THE DATA, NOT THE CLOCK. The same job runs twice a day and the two
  // runs differ only in what has settled by the time they go, so deciding "bets" against
  // "results" from the hour would be a second source of truth about which run this is —
  // and the one that can be wrong. A card with nothing settled is bets; a card with a
  // result on it is results, whenever it happens to be drawn.
  //
  // A DAY THAT IS NOT TODAY SAYS SO IN THE HEADING, because "TODAY'S BETS" over tomorrow's
  // games is wrong in the one way a reader cannot check: the card's own date line is small
  // and the heading is what gets screenshotted.
  const today = entry.day === data.day;
  const auto = card.hasResult ? "Today's results"
    : today ? "Today's bets" : "Upcoming bets";
  const heading = HEADING || auto;
  const post = cardPost({ card, site: SITE.replace(/^https?:\/\//, ""), heading });
  const argsFile = `${ARGS_PREFIX}_${cards.length + 1}.json`;
  writeFileSync(argsFile, JSON.stringify({
    card, site: SITE.replace(/^https?:\/\//, ""), heading: heading.toUpperCase(),
  }));
  cards.push({
    day: card.day, post, args: argsFile, n: card.n,
    note: `${card.day}: ${card.n} bet${card.n === 1 ? "" : "s"}`
          + (card.hasResult ? ` · ${card.won}-${card.lost} · ${card.unitsText}` : " · all pending")
          + (card.hidden ? ` · ${card.hidden} held back` : ""),
  });
}

if (!cards.length) {
  // A QUIET WINDOW IS NOT A FAILURE, and the note says which kind of quiet it was — "no
  // prices stored at all" and "nothing cleared the floor" need opposite responses, and
  // from outside they look identical.
  const note = data.note || "nothing to post";
  console.error(`bets_card: ${note}`);
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, day: data.day, note, cards: [] }, null, 2));
  process.exit(0);
}

writeFileSync(JSON_OUT, JSON.stringify({
  empty: false, day: data.day, count: cards.length, cards,
  note: cards.map((c) => c.note).join("  ·  "),
  frozen: data.frozen ?? 0,
}, null, 2));
console.error(`bets_card: ${cards.length} card${cards.length === 1 ? "" : "s"} — `
              + cards.map((c) => c.note).join(" | "));
