#!/usr/bin/env node
// The weekend's EV+ corner prices as one clip, and the caption that goes with it.
//
// WHY THIS EXISTS. The best prices on the board were going out as typed messages, one
// fixture at a time, which is slow enough that it only happens when there is time for it —
// so the shop window is open some weekends and not others. One clip off one list goes out
// in a minute, and because the list is built by a tested function rather than by whoever
// is typing, the weekend with two good prices on it gets published the same way as the
// weekend with eight.
//
// IT SELECTS BY RULE, NOT BY TASTE, and lib/tipsReel.js holds every one of those rules:
// one pick per fixture, the 5+/6+ band only, a real price that names its bookmaker, and
// the age of the oldest price on the face of the card. Read that file's header before
// changing what reaches the clip — each rule is there because the ledger or a real post
// showed what happens without it.
//
// WHAT IT DOES NOT DO: it never sends. The workflow decides that, and by default it builds
// the clip, prints the caption into the run summary and keeps the file, where it can be
// watched before anyone posts it. A clip cannot be unposted.
//
// Usage:  node tools/tips_reel.mjs [--days 4] [--max 8] [--min-ev 5]
//                                  [--band 5,6] [--heading "BEST PRICES"]
//                                  [--json-out tips.json] [--args-out tips_args.json]
// Env:    BACKEND_URL, SITE_URL, TOOLS_TOKEN (required)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const LIB = resolve(HERE, "..", "frontend", "src", "lib");
const { tipsFrom, tipsPost, BAND, MAX_TIP_ROWS, MIN_TIP_ROWS, MIN_TIP_EV } =
  await import(resolve(LIB, "tipsReel.js"));
const { headlineOf } = await import(resolve(LIB, "recordCard.js"));
const { countedRows, WIN, LOSS } = await import(resolve(LIB, "resultsReel.js"));

const arg = (name, fallback = null) => {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};

const BACKEND = process.env.BACKEND_URL || "https://corner-model.onrender.com";
const SITE = process.env.SITE_URL || "https://thecornermodel.com";
const TOKEN = process.env.TOOLS_TOKEN;
// FOUR DAYS, NOT SEVEN. A price eight days out is a price that will have moved twice
// before kick-off, and a clip is posted to be acted on this weekend. The board itself is
// built for a wider window; this is the slice of it worth quoting.
const DAYS = Number(arg("days", "4"));
const MAX = Number(arg("max", String(MAX_TIP_ROWS)));
const MIN_EV = Number(arg("min-ev", String(MIN_TIP_EV)));
// HOW MANY ROWS TO ASK THE BOARD FOR, which is not the same as how many go on the clip.
// The band filter and the floor both cut, so asking for exactly MAX would hand over eight
// rows and publish two. 120 is well inside value_board's own cap.
const SCAN = Number(arg("scan", "120"));
const BANDS = (arg("band", BAND.join(",")) || "").split(",")
  .map((s) => Number(s.trim())).filter((n) => Number.isFinite(n));
const HEADING = arg("heading", null);
const JOIN = arg("join", `${SITE.replace(/^https?:\/\//, "")}/join`);
const JSON_OUT = arg("json-out", "tips.json");
const ARGS_OUT = arg("args-out", "tips_args.json");

const fail = (m) => { console.error(`tips_reel: ${m}`); process.exit(1); };
if (!TOKEN) fail("TOOLS_TOKEN is required");
if (!BANDS.length) fail("--band needs at least one plus-line, e.g. --band 5,6");

const get = async (path, ms = 120000, what = "") => {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const res = await fetch(`${BACKEND}${path}`, { signal: ctl.signal });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      // 401 here means the token did not take: the endpoint falls back to a signed-in
      // reader and refuses the public one, so the message names the thing to go and fix.
      return { error: `HTTP ${res.status} — ${body.slice(0, 200)}` };
    }
    return { data: await res.json() };
  } catch (err) {
    return { error: `${what || path} — ${err.message}` };
  } finally {
    clearTimeout(timer);
  }
};

// THE BOARD. `boards=value` is the only one asked for: each of the five walks the whole
// team collection and this reads exactly one of them.
const board = await get(
  `/api/share/rows?token=${encodeURIComponent(TOKEN)}&days=${DAYS}`
  + `&limit=${SCAN}&boards=value`, 180000, "the value board");
if (board.error) fail(`could not read the value board — ${board.error}`);
const rows = board.data?.value || [];

// THE RECORD, AND NEVER FATAL. It is the honesty mechanism the card is built around, so
// it is fetched — but a clip that refused to exist because /api/results was slow would be
// the wrong trade. No record, no record on the end card, and the run says so.
let record = null;
const res = await get(`/api/results?token=${encodeURIComponent(TOKEN)}`, 120000,
                      "the graded record");
if (res.error) {
  console.error(`tips_reel: could not read the record (${res.error}) — no record on the card`);
} else {
  const all = countedRows(res.data || {});
  const summary = res.data?.summary;
  record = summary?.settled != null ? summary : {
    landed: all.filter((r) => r.result === WIN).length,
    settled: all.filter((r) => r.result === WIN || r.result === LOSS).length,
  };
  if (!headlineOf(record)) {
    console.error("tips_reel: nothing settled on the record yet — no record on the card");
    record = null;
  }
}

const { reel, faults, eligible } = tipsFrom(rows, {
  minEv: MIN_EV, band: BANDS, max: MAX, join: JOIN, record,
});

// WHY THE CLIP DID NOT HAPPEN, BY REASON. A weekend with no band prices and a weekend
// where every band price was a point under the floor are different problems with different
// fixes, and "nothing to animate" says neither. This is the diagnostic value_board's own
// docstring argues for: every drop produces a line rather than an empty screen.
const why = Object.entries(faults).sort((a, b) => b[1] - a[1])
  .map(([k, n]) => `${k} ${n}`).join(", ");

if (!reel) {
  console.error(`tips_reel: nothing to animate — ${eligible} publishable pick(s), `
                + `${MIN_TIP_ROWS} needed. ${rows.length} ok row(s) on the board`
                + (why ? ` · dropped: ${why}` : ""));
  writeFileSync(JSON_OUT, JSON.stringify({ empty: true, days: DAYS, eligible, faults },
                                         null, 2));
  process.exit(0);
}

const post = tipsPost({
  reel, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING } : {}),
});

writeFileSync(JSON_OUT, JSON.stringify({ empty: false, reel, post, faults, eligible },
                                       null, 2));
writeFileSync(ARGS_OUT, JSON.stringify({
  reel, site: SITE.replace(/^https?:\/\//, ""),
  ...(HEADING ? { heading: HEADING.toUpperCase() } : {}),
}));

// PRINTED, because the clip is the one thing nobody can check until it has been watched,
// and this line is the same claim in a form that survives a failed encode.
console.error(`tips_reel: ${reel.n} pick(s) over ${DAYS} days across ${reel.leagues} `
              + `competition(s)${reel.more ? ` (+${reel.more} trimmed)` : ""}`
              + ` · band ${reel.bandLabel} · floor ${MIN_EV}%`
              + ` · best +${reel.bestEv.toFixed(1)}%`
              + (reel.context ? ` · ${reel.context}` : " · no record on the card")
              + ` · ${reel.pricedNote}`);
// EVERY BOOK NAMED, in the log. The edges on this card are measured against the best of 33
// books, and the one question a reader of the run has that the caption cannot answer is
// "are these prices at a bookmaker I hold" — so the distribution is printed rather than
// left to be counted by hand off the clip.
const books = {};
reel.rows.forEach((r) => { books[r.book] = (books[r.book] || 0) + 1; });
console.error(`tips_reel: books — ${Object.entries(books)
  .sort((a, b) => b[1] - a[1]).map(([b, n]) => `${b} ${n}`).join(", ")}`);
if (why) console.error(`tips_reel: dropped — ${why}`);
