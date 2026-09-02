// The postable version of each board, in one place.
//
// These started out inside the three components, which was fine while a share was
// something a person clicked. It stopped being fine when a scheduled job began posting
// the same boards: two renderers drift, and the drift would show up as the automated
// post looking subtly unlike the one posted by hand an hour earlier — a different
// bullet, a missing kick-off, a "+N more" that disagrees with its own list.
//
// So the components and tools/social_draft.mjs both call these. Pure functions of rows:
// no React, no window, no fetch, which is what lets a Node script import them.
//
// Each builder returns a FUNCTION OF A ROW LIMIT rather than a string, because fitting
// an X post means rebuilding at fewer rows, not truncating — the "+N more on the site"
// tail has to keep matching the list above it at every size. See lib/xLimit.

import { flagBullet, withFlag } from "./countryFlag.js";
import { kickoffLabel, timesFooter } from "./kickoff.js";

const more = (total, limit) => (total > limit ? `\n+${total - limit} more on the site` : "");

/**
 * Corner Streak Finder. `presetLabel` is the window as the filter names it ("5 of 5"),
 * so the heading says which run the list below it is actually claiming.
 *
 * THE LINE IS NOT PUBLISHED. A row says which team, how the run reads and when they
 * play — not the number. The line is the actionable half and it is what the paid
 * channel is for, so it stays out of a public post entirely rather than being blurred
 * or abbreviated. The record and the kick-off are what keep the claim credible without
 * it: a reader can see a 5/5 run kicking off tonight and cannot bet it from the post.
 */
export const streakShare = ({ rows = [], subject, isUnder, side, presetLabel = "" }) => (limit) => {
  if (!rows.length) return "";
  const what = subject === "match" ? "match total corners" : "team corners";
  const head = `${isUnder ? "Under" : "Over"} ${what} — hit in ${presetLabel} `
    + `${side === "overall" ? "" : side + " "}games:`;
  const shown = rows.slice(0, limit);
  const lines = shown.map((r) => {
    const fx = r.next_fixture;
    const vs = fx ? ` ${fx.is_home ? "vs" : "@"} ${fx.opponent}` : "";
    // The kick-off closes the line rather than interrupting it: the team is what the
    // reader is weighing, the time is what they act on once they've decided.
    const when = kickoffLabel(fx?.date);
    // The flag replaces the bullet rather than joining it — see flagBullet.
    return `${flagBullet(r.league_id)} ${r.name}${vs}`
      + ` (${r.hits}/${r.window})${when ? ` · ${when}` : ""}`;
  });
  // The zone is named ONCE, not on every line — six repeats of "BST" is a third of a
  // tweet. See timesFooter for when it is dropped entirely.
  const times = timesFooter(shown.map((r) => r.next_fixture?.date));
  return `${head}\n${lines.join("\n")}${more(rows.length, limit)}${times}`;
};

/** Best Upcoming Games. `days` is the window as the tab names it ("3", "7"). */
export const fixtureShare = ({ fixtures = [], days = "3" }) => (limit) => {
  if (!fixtures.length) return "";
  const shown = fixtures.slice(0, limit);
  return `Best upcoming corner games (next ${days === "1" ? "day" : `${days} days`}):\n`
    + shown.map((f) => {
        const angle = (f.angles || [])[0];
        const tag = angle ? ` — ${angle.team} ${angle.label}` : "";
        // Same shape as the streak share, deliberately: both boards land in the same
        // channel an hour apart, and a reader shouldn't have to re-learn the line. The
        // board groups by day on screen, but the shared text is flat, so each line has
        // to carry its own day rather than inheriting a heading.
        const when = kickoffLabel(f.date);
        return `${flagBullet(f.league_id)} ${f.home} v ${f.away} (λ ${f.lambda_total})${tag}`
          + (when ? ` · ${when}` : "");
      }).join("\n")
    + more(fixtures.length, limit)
    + timesFooter(shown.map((f) => f.date));
};

/**
 * Best Corner Teams. Numbered rather than bulleted, so the flag joins the name instead
 * of replacing the marker — a ranking without its numbers is just a list.
 */
export const bestTeamsShare = ({ rows = [], side, windowLabel = "" }) => (limit) => {
  if (!rows.length) return "";
  return `Best corner teams — ${side === "overall" ? "all games" : side} (${windowLabel}):\n`
    + rows.slice(0, limit).map((r, i) =>
        `${i + 1}. ${withFlag(r.league_id, r.name)} — ${r.won_avg.toFixed(2)} corners won/game`).join("\n")
    + more(rows.length, limit);
};

/**
 * How the streaks that went out actually landed.
 *
 * Graded from a SNAPSHOT taken before kick-off, never from the board as it looks
 * afterwards — a team that misses drops off the board, so counting the survivors would
 * report a perfect week every week. See /api/streaks/snapshot.
 *
 * What each row publishes is the outcome and the corner count, and not the line. The
 * count is a fact about the game that anyone can look up; the line is the product. A
 * reader can check the model was right without being handed what to back next time.
 */
export const streakResultShare = ({ results = [], landed = 0, settled = 0, voided = 0 }) => (limit) => {
  const graded = results.filter((r) => r.result === "win" || r.result === "loss");
  if (!graded.length) return "";
  const mark = { win: "✅", loss: "❌" };
  const head = `How last week's corner streaks landed — ${landed}/${settled}:`;
  const shown = graded.slice(0, limit);
  const lines = shown.map((r) => {
    const vs = r.opponent ? ` ${r.is_home ? "vs" : "@"} ${r.opponent}` : "";
    // The corner count, not the line: it shows the call was right without giving away
    // what the call was.
    const got = r.value != null ? ` — ${r.value} corners` : "";
    return `${flagBullet(r.league_id)} ${r.name}${vs}${got} ${mark[r.result]}`;
  });
  // Voids are named rather than quietly dropped. A week reported as 4/4 that was really
  // 4/4 plus two stake-backs is a different week, and hiding that inflates the record.
  const voids = voided ? `\n${voided} void (exact line — stake back)` : "";
  const more = graded.length > limit ? `\n+${graded.length - limit} more on the site` : "";
  return `${head}\n${lines.join("\n")}${voids}${more}`;
};
