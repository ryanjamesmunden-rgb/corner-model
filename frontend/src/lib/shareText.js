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
    // The kick-off closes the line rather than interrupting it: the bet is what the
    // reader is deciding about, the time is what they act on once they've decided.
    const when = kickoffLabel(fx?.date);
    // The flag replaces the bullet rather than joining it — see flagBullet.
    return `${flagBullet(r.league_id)} ${r.name} ${isUnder ? "U" : ""}${r.line}${isUnder ? "" : "+"}${vs}`
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
