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
// Usage:  node tools/bets_card.mjs [--day YYYY-MM-DD] [--min-ev 0] [--rows 6] [--preview]
//                                  [--json-out bets.json] [--args-out card_args.json]
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
const JSON_OUT = arg("json-out", "bets.json");
const ARGS_OUT = arg("args-out", "card_args.json");
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
  freeze: flag("preview") ? "false" : "true",
});
if (DAY) params.set("day", DAY);

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
const card = cardFrom({ rows: data.rows || [], day: data.day, summary: data, max: ROWS });

if (!card) {
  // A QUIET DAY IS NOT A FAILURE, and the note says which kind of quiet it was — "no
  // prices stored at all" and "nothing cleared the floor" need opposite responses, and
  // from outside they look identical.
  const note = data.note || "nothing to post";
  console.error(`bets_card: ${note}`);
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, day: data.day, note }, null, 2));
  process.exit(0);
}

// THE HEADING FOLLOWS THE DATA, NOT THE CLOCK. The same job runs twice a day and the two
// runs differ only in what has settled by the time they go, so deciding "bets" against
// "results" from the hour would be a second source of truth about which run this is — and
// the one that can be wrong. A card with nothing settled is today's bets; a card with a
// result on it is today's results, whenever it happens to be drawn.
const auto = card.hasResult ? "Today's results" : "Today's bets";
const heading = HEADING || auto;
const post = cardPost({ card, site: SITE.replace(/^https?:\/\//, ""), heading });

writeFileSync(JSON_OUT, JSON.stringify({
  empty: false, day: card.day, post, card,
  note: `${card.n} bet${card.n === 1 ? "" : "s"}`
        + (card.hasResult ? ` · ${card.won}-${card.lost} · ${card.unitsText}` : " · all pending")
        + (card.hidden ? ` · ${card.hidden} held back` : ""),
  frozen: data.frozen ?? 0,
}, null, 2));
writeFileSync(ARGS_OUT, JSON.stringify({
  card, site: SITE.replace(/^https?:\/\//, ""), heading: heading.toUpperCase(),
}));
console.error(`bets_card: ${card.n} rows for ${card.day}`);
