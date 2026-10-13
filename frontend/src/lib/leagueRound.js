// A league's round: a cluster of its games inside a few days, and a post about it.
//
// WHAT IT IS FOR. A whole division plays inside three or four days and that window is one
// story — "the Championship this weekend" — rather than twelve unrelated fixtures. The
// browse page could already show you those games and had no way to say "this is a round,
// here is the post". So: find the clusters, rank the games in each by the strongest run
// going into them, and hand the lot to the share buttons before anything kicks off.
//
// CLUSTERED BY DATE, NOT BY THE PROVIDER'S ROUND LABEL, and that is the whole design
// decision here. `round` is stored on every fixture and would have been the obvious key,
// but a provider round is not the thing being asked for: a "Round 12" can legitimately run
// Friday to the following Tuesday, which is five days and not a weekend, and in a cup it
// can span a fortnight. The criterion is "games inside three or four days", so the dates
// ARE the criterion and the label is only a name for what the dates found. Where every
// game in a cluster agrees on a real label, it is used as the title; where they do not,
// the window names itself.
//
// AND "Upcoming" IS NOT A ROUND. sync_real falls back to "Upcoming" when the provider
// sends no round, and the synthetic seed writes "Upcoming Round". Keyed on the label, every
// such fixture in a league would have merged into one giant fake round spanning the whole
// window — which is exactly the sort of plausible, wrong grouping that gets published once
// and believed. Clustering by date cannot make that mistake, and the fallback labels are
// still filtered out of the TITLE so a round is never named after a missing value.
//
// ONE ROW PER GAME. A single fixture can carry six qualifying runs across three subjects
// and two venues, so a post ranked purely by run length would be one game listed six times
// — the opposite of "the best games". Each game contributes its strongest run and nothing
// else, which makes the same list answer both halves of the question: the games are ordered
// by their best run, so it is the best games AND the highest streaks, not two lists.
//
// THE WORDING COMES FROM streakClaim, and that is not a convenience. A conceded run
// rendered without its verb reads as the opposite bet — "Arsenal under 4" for a side
// SHIPPING under four — and that exact bug has already shipped on the browse row once. The
// formatter is single-sourced so it cannot come back here.

import { flagBullet } from "./countryFlag.js";
import { streakClaim, markFor } from "./fixtureStreaks.js";

/**
 * How many games make a round worth posting about.
 *
 * FOUR. A division playing a full card is ten; four is the smallest number that reads as
 * "a lot of this league is on" rather than a couple of fixtures that happen to be close
 * together, and it keeps a mid-week pair of catch-up games out of the list.
 */
export const ROUND_MIN_GAMES = 4;

/**
 * The window, in CALENDAR DAYS INCLUSIVE — so four means Friday to Monday, and the
 * difference between the first and last day must be at most three.
 *
 * Stated in the unit the request was made in ("over the space of 3-4 days") rather than as
 * the off-by-one it becomes in arithmetic, because that off-by-one is the whole bug risk
 * in this file: at a diff of 4 a Friday-to-Tuesday cluster passes and is not a weekend.
 */
export const ROUND_SPAN_DAYS = 4;

/** Rows a post starts from. fitToPost trims from here; it never adds. */
export const ROUND_MAX_ROWS = 6;

/**
 * How long a run has to be to earn a row.
 *
 * FIVE, matching SHARE_MIN_RUN and the browse filter's own floor. A post is public and
 * permanent in a way a screen is not, and three games is what a side does by accident.
 */
export const ROUND_MIN_RUN = 5;

/**
 * Labels that are a MISSING round rather than a round. See the note at the top: keyed on
 * these, a whole league's fixtures merge into one fake round.
 */
export const ROUND_FALLBACK_LABELS = ["upcoming", "upcoming round", "regular season"];

const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** Whole days between two YYYY-MM-DD strings. Midday, so no DST shift can move it. */
export const dayGap = (a, b) => {
  if (!a || !b) return null;
  const x = new Date(`${a}T12:00:00Z`);
  const y = new Date(`${b}T12:00:00Z`);
  if (Number.isNaN(x.getTime()) || Number.isNaN(y.getTime())) return null;
  return Math.round((y - x) / 86400000);
};

/** Is this label a real round, or the fallback a missing one leaves behind? */
export const isRealRound = (label) => {
  const s = String(label || "").trim();
  if (!s) return false;
  return !ROUND_FALLBACK_LABELS.includes(s.toLowerCase());
};

/**
 * The cluster's title: the provider's round, but only when every game agrees on one real
 * label. A cluster whose games carry two different rounds gets no title rather than the
 * first one — naming a weekend after one of the two rounds in it is a wrong label, and
 * the window below says what the dates are anyway.
 */
export const roundTitle = (games = []) => {
  const labels = new Set((games || []).map((g) => String(g?.round || "").trim()));
  if (labels.size !== 1) return "";
  const only = [...labels][0];
  return isRealRound(only) ? only : "";
};

/**
 * The games of one league, split into date clusters.
 *
 * GREEDY FROM THE EARLIEST GAME, extending while the cluster still spans at most
 * ROUND_SPAN_DAYS. A league playing Saturday, Sunday, then Wednesday gives a weekend
 * cluster and a midweek one, which is right: they are two posting moments, not one
 * five-day blur.
 */
export const clusterByDate = (games = []) => {
  const sorted = [...(games || [])]
    .filter((g) => g && g.day)
    .sort((a, b) => String(a.day).localeCompare(String(b.day))
                 || String(a.date || "").localeCompare(String(b.date || "")));
  const out = [];
  let run = [];
  for (const g of sorted) {
    if (!run.length) { run = [g]; continue; }
    const gap = dayGap(run[0].day, g.day);
    if (gap !== null && gap <= ROUND_SPAN_DAYS - 1) run.push(g);
    else { out.push(run); run = [g]; }
  }
  if (run.length) out.push(run);
  return out;
};

/**
 * Every game's strongest qualifying run, best first — one row per game.
 *
 * THE RUN IS ALREADY RANKED SERVER-SIDE: browse sends `streaks` sorted by run then margin
 * and `streak` as the best of them, so the first entry is taken rather than re-ranked
 * here. Re-sorting would be a second ranking rule for the same rows, and the one that
 * disagreed would be whichever was edited second.
 */
export const roundRows = (games = [], minRun = ROUND_MIN_RUN) => {
  const rows = [];
  for (const g of games || []) {
    const best = g?.streak || (g?.streaks || [])[0];
    if (!best || (num(best.run) || 0) < minRun) continue;
    const opponent = best.team === g.home ? g.away : g.home;
    rows.push({ ...best, game: g, opponent, fixture_id: g.fixture_id, date: g.date });
  }
  return rows.sort((a, b) => (num(b.run) - num(a.run))
                          || ((num(b.margin) ?? 0) - (num(a.margin) ?? 0)));
};

/**
 * Every qualifying round in the payload, soonest first.
 *
 * SOONEST FIRST, not biggest first. The list is a schedule of posting moments and the one
 * that matters is the one kicking off next — a bigger round a week out can wait, and
 * posting it early spends it. The game count rides on each entry so size is still visible.
 */
export function roundsOf(countries = [], { minGames = ROUND_MIN_GAMES,
                                           minRun = ROUND_MIN_RUN } = {}) {
  const out = [];
  for (const c of countries || []) {
    for (const l of c?.leagues || []) {
      for (const cluster of clusterByDate(l.games)) {
        if (cluster.length < minGames) continue;
        const rows = roundRows(cluster, minRun);
        out.push({
          key: `${l.league_id}:${cluster[0].day}`,
          league_id: l.league_id,
          league_name: l.name,
          country: c.country,
          is_cup: !!l.is_cup,
          title: roundTitle(cluster),
          games: cluster,
          first: cluster[0].day,
          last: cluster[cluster.length - 1].day,
          span: (dayGap(cluster[0].day, cluster[cluster.length - 1].day) ?? 0) + 1,
          rows,
          // COUNTED, so a round with a full card and no runs in it says so rather than
          // rendering as an empty card that looks like a loading failure.
          run_count: rows.length,
        });
      }
    }
  }
  return out.sort((a, b) => String(a.first).localeCompare(String(b.first))
                         || (b.games.length - a.games.length)
                         || String(a.league_name).localeCompare(String(b.league_name)));
}

/** "Sat–Mon", or "Sat" where the whole round is one day. UK short weekdays. */
export const roundWindow = (round, tz = "Europe/London") => {
  const day = (iso) => {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat("en-GB", { timeZone: tz, weekday: "short" })
        .format(new Date(`${iso}T12:00:00Z`));
    } catch { return ""; }
  };
  const a = day(round?.first);
  const b = day(round?.last);
  if (!a) return "";
  return !b || a === b ? a : `${a}–${b}`;
};

/** "Championship, Round 12" — or just the league where no single round owns the window. */
export const roundName = (round) =>
  [round?.league_name, round?.title].filter(Boolean).join(", ");

/**
 * One row: the claim, the run, and the fixture it is going into.
 *
 * THE CLAIM CARRIES ITS OWN SUBJECT, via streakClaim — "Reading win 6+" and "Arsenal
 * concede under 4" are opposite bets and the verb is the only thing separating them. On a
 * one-line row there is no second line to put the subject on, so it goes inside the
 * phrase or it is simply missing, which is how the browse row once published a conceded
 * run as though it were an attacking one.
 */
export const roundRow = (r, { time = null } = {}) => {
  const claim = streakClaim({ team: r?.team, subject: r?.subject,
                              label: r?.line_label });
  const run = num(r?.run) || 0;
  const when = time ? time(r?.date) : "";
  const against = r?.opponent ? `v ${r.opponent}` : "";
  const tail = [against, when].filter(Boolean).join(" ");
  return [`${markFor(run)} ${claim}`,
          run >= 2 ? `${run} in a row` : "",
          tail].filter(Boolean).join(" · ");
};

/**
 * The post, as a function of row count, for fitToPost.
 *
 * A FUNCTION RATHER THAN A STRING because fitting a post means REBUILDING it at fewer
 * rows, not truncating one: the "+N more" tail has to keep agreeing with the list above
 * it, and only the builder knows what N is.
 *
 * THE HEADER SAYS HOW MANY GAMES ARE IN THE ROUND, not how many rows are printed. Those
 * are different numbers — twelve games, four of them carrying a run worth naming — and
 * printing the row count as the game count would undersell a full card.
 */
export const roundPost = ({ round, minRun = ROUND_MIN_RUN } = {}) => (limit) => {
  if (!round) return "";
  const rows = (round.rows || []).slice(0, Math.max(1, limit));
  const window = roundWindow(round);
  const games = (round.games || []).length;
  const head = `${flagBullet(round.league_id)} ${roundName(round)} — `
             + `${games} ${games === 1 ? "game" : "games"}${window ? ` ${window}` : ""}`;
  if (!rows.length) {
    // NOT AN EMPTY POST. A round with a full card and no long run is a real answer and
    // the only honest one; a share button that opens a blank composer looks broken.
    return `${head}\n\nNo run of ${minRun}+ going into any of them.`;
  }
  const held = (round.rows || []).length - rows.length;
  const tail = held > 0 ? `\n+${held} more on the site` : "";
  return `${head}\n\n${rows.map((r) => roundRow(r)).join("\n")}${tail}`;
};
