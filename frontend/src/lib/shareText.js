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
 * Corner Streak Finder: flag, team, line, run. Four things, nothing else.
 *
 * THE RUN IS THE TEAM'S OWN, NOT THE FILTER'S. Every row used to end "(5/5)" because
 * that is what the filter asked for — five of the last five — so a team on a nine-game
 * run and a team that scraped the minimum published the same number, and the best rows
 * on the board were the ones the post undersold. `streak.length` is the run actually
 * alive right now, counted over the whole history and counting WINS only (voids are
 * skipped by streak_runs rather than padding the number), so "9 in a row" means nine.
 *
 * THE OPPONENT AND THE KICK-OFF ARE GONE. Neither is a reason to click: the fixture is
 * the same information the reader gets everywhere else, and between them they cost about
 * a third of a post. What is left is the part that earns a visit — a team, the line it
 * keeps clearing, and how long it has been doing it.
 *
 * THE LINE IS PUBLISHED NOW. This used to be withheld deliberately, on the reasoning that
 * the line is the actionable half. The share images already print it, so withholding it
 * here only made the two disagree — and a streak with no line is a claim a reader cannot
 * size up, which is a worse advert than one they can. The price is still the paid half
 * and still never appears.
 */
export const streakShare = ({ rows = [], subject, side }) => (limit) => {
  if (!rows.length) return "";
  const what = subject === "match" ? "Match" : "Team";
  const where = side === "overall" ? "" : ` in ${side} games`;
  const head = `${what} corner streaks running right now${where}:`;
  const lines = rows.slice(0, limit).map((r) => {
    // "under 9" or "5+", straight from the API so the post cannot label a direction
    // differently from the screen. Absent, the row drops the line rather than guessing
    // one — mislabelling an under as an over is worse than saying less.
    const line = r.line_label ? ` ${r.line_label}` : "";
    // A run of one is not a run, and "1 in a row" reads as a mistake even when true.
    const run = Number(r.streak?.length);
    const tail = run >= 2 ? ` — ${run} in a row` : "";
    // The flag replaces the bullet rather than joining it — see flagBullet.
    return `${flagBullet(r.league_id)} ${r.name}${line}${tail}`;
  });
  return `${head}\n${lines.join("\n")}${more(rows.length, limit)}`;
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
 * Best Corner Teams: flag, team, number. Nothing else on the line.
 *
 * THE UNIT IS NAMED ONCE, IN THE HEADING, and never repeated per row — the same rule the
 * timezone footer follows. "corners won/game" after every team cost 18 characters a line
 * and said the same thing eight times; on a board headed "avg corners won" the number
 * needs no unit, and "per game" is what an average already means.
 *
 * The rank numbers are gone too. They cost three characters a row to state an order the
 * list is already in, and on X those three characters are a whole extra team.
 *
 * That takes a row from ~42 characters to ~16, which is the difference between three
 * teams surviving the post limit and all eight — the point being that fitToPost drops
 * rows it cannot fit, so shortening the line is what stops it having to.
 */
export const bestTeamsShare = ({ rows = [], side, windowLabel = "" }) => (limit) => {
  if (!rows.length) return "";
  const scope = side === "overall" ? "" : ` ${side}`;
  const window = windowLabel ? ` · ${windowLabel}` : "";
  return `Best corner teams${scope} — avg corners won${window}:\n`
    + rows.slice(0, limit).map((r) =>
        `${flagBullet(r.league_id)} ${r.name} ${r.won_avg.toFixed(2)}`).join("\n")
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
export const streakResultShare = ({ results = [], landed = 0, settled = 0, voided = 0,
                                   pending = 0 }) => (limit) => {
  const graded = results.filter((r) => r.result === "win" || r.result === "loss");
  if (!graded.length) return "";
  const mark = { win: "✅", loss: "❌" };
  const head = `How last week's corner streaks landed — ${landed}/${settled}:`;

  // A TRIMMED RESULTS POST MUST STILL SHOW A MISS.
  //
  // Trimming to fit takes the first N rows, and the first N can happen to be all wins —
  // which is how an honest "3/4" headline ends up over a picture of a clean sweep. The
  // count would be true and the impression false, and a reader has no way to tell. So
  // when the cut would hide every miss, the last visible win gives up its place to the
  // first miss. The post gets shorter-looking odds and stays a record rather than an
  // advert.
  let shown = graded.slice(0, limit);
  const missed = graded.filter((r) => r.result === "loss");
  if (missed.length && !shown.some((r) => r.result === "loss")) {
    shown = [...shown.slice(0, Math.max(0, shown.length - 1)), missed[0]];
  }
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
  // Games still unsettled are DECLARED, not omitted. "3/3" posted while three more are
  // outstanding is a different week from "3/3", and a reader has no way to tell which
  // one they are being shown unless the post says.
  const left = pending ? `\n${pending} still to settle` : "";
  const more = graded.length > limit ? `\n+${graded.length - limit} more on the site` : "";
  return `${head}\n${lines.join("\n")}${voids}${left}${more}`;
};

/**
 * One fixture, and what is already running into it.
 *
 * DIFFERENT QUESTION FROM THE STREAK BOARD. That board answers "which teams are on a
 * run"; this answers "what is running into THIS game", which is the question you have
 * once you are looking at a single fixture. A game is worth posting when something is
 * already alive going into it, and this is the post that says so.
 *
 * SUGGESTED LINES, NOT A PRICE. Each row is a line and how long it has been landing —
 * enough for a reader to judge whether it is worth their time, and nothing they could
 * bet from without the model's number, which stays on the site.
 *
 * Rows arrive already sorted longest-run-first from the backend, so trimming for length
 * drops the weakest rather than whatever happened to be last.
 */
// Long enough to be worth a mark. The share floor is already 5, so this is the tier above
// it — a run that stands out from the ones it is listed beside. Marking everything would
// mark nothing.
export const FIRE_RUN = 8;

export const fixtureStreakShare = ({ fixture = {}, streaks = [], form = [] }) => (limit) => {
  if (!streaks.length) return "";
  const when = kickoffLabel(fixture.date);
  const head = `${flagBullet(fixture.league_id, "")} ${fixture.home_name} v ${fixture.away_name}`
    .trim() + (when ? ` · ${when}` : "");
  const lines = streaks.slice(0, limit).map((s) => {
    // "Derby games 10+" for a match total, "Derby 6+" for that team's own corners — the
    // two are different claims and a reader has to be able to tell which is which.
    const what = s.subject === "match" ? `${s.team} games ${s.line_label}` : `${s.team} ${s.line_label}`;
    const mark = s.run >= FIRE_RUN ? "🔥 " : "";
    return `${mark}${what} corners — ${s.run} in a row`;
  });
  // GAME STATE, under the lines. A side unbeaten at home plays on the front foot and wins
  // corners; a side that cannot win away ends up chasing, which also produces them. The
  // two read as opposites and point the same way, which is worth a reader seeing.
  const state = form
    .filter((f) => f.label)
    .map((f) => `${f.team} ${f.label} ${f.venue === "away" ? "away" : "at home"}`);
  const tail = state.length ? `\n\n${state.join("\n")}` : "";
  return `${head}\n\nStreaks running into it:\n${lines.join("\n")}`
    + more(streaks.length, limit) + tail;
};
