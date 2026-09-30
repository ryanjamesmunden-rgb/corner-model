// What is actually CONSISTENT across a team's recent games.
//
// THE PROBLEM THIS SOLVES. The fixture page's bottom section is a ten-column table of raw
// per-game numbers. Everything needed to judge a side is in it and none of it is legible:
// deciding whether a team reliably clears 5 corners means reading a column downwards,
// holding five numbers in your head and comparing each to 5. Readers do that by eye, and
// by eye is where a miscount comes from — the row that looks like a pattern is the row
// with one big number in it.
//
// So this states it instead of leaving it to be worked out. The same games, the same
// split, the same window the reader already chose — reduced to the one thing a corner bet
// turns on: which line did they clear EVERY time, and where does that stop being true.
//
// THE FLOOR IS THE HEADLINE, not the average. An average of 5.4 is true of a side that
// goes 5,5,6,5,6 and of one that goes 1,2,9,6,9, and only the first is worth a line at 5.
// "4+ in all five" is a claim a reader can size up in one glance and act on without
// re-deriving it; a mean is not.
//
// AND IT IS DESCRIPTION, NOT PREDICTION. measure_chase_board.py replayed four orderings
// walk-forward and could not separate any from a shuffled control, so what a side has done
// is not a forecast of what it will do. Every label here is past tense on purpose.

// The three things worth laddering on a corner page, and where each lives on a game row.
//
// `short` is what fits the switcher on a phone; `noun` is what completes "4+ ___" in the
// caption. Both are here rather than in the component so the chart, the sentence and the
// screen-reader label cannot end up calling the same subject three different things.
// `claim` is the whole phrase for a share image, and it exists because composing one from a
// verb and a noun produces nonsense on the conceded subject: "cleared 5+ conceded" says the
// opposite of what a conceded record is. A side does not CLEAR corners it shipped. Each
// subject therefore owns its own sentence rather than being fed through one template.
export const SUBJECTS = [
  { key: "won", label: "Corners won", short: "Won", noun: "corners won",
    claim: (line) => `cleared ${line}+ corners`,
    pick: (m) => m.won, tone: "for" },
  { key: "conceded", label: "Corners conceded", short: "Conceded", noun: "conceded",
    claim: (line) => `conceded ${line}+ corners`,
    pick: (m) => m.conceded, tone: "against" },
  { key: "total", label: "Match total", short: "Total", noun: "in the match",
    claim: (line) => `${line}+ corners in the match`,
    pick: (m) => m.total, tone: "total" },
  // SHOTS, AND A ZERO HERE MEANS "NOT REPORTED" RATHER THAN "TOOK NONE.
  //
  // sync_real coerces a missing shot count to 0 on purpose — the live lambda consumes it
  // and must not start seeing null — so an uncovered fixture and a shotless one are the
  // same value in the database. They are not the same thing: a side taking literally zero
  // shots in a match essentially does not happen, while the provider not reporting shots
  // happens often. Drawn as a real zero it puts a floor of 0 on the panel and drags the
  // whole claim down, which is the one number on this chart worth protecting.
  //
  // So the pick returns null for 0 and the game is dropped, exactly as an uncovered game
  // is everywhere else. The cost is that a genuine 0-shot match would vanish; the benefit
  // is that a dozen unreported ones do not silently rewrite the floor.
  { key: "shots", label: "Shots", short: "Shots", noun: "shots",
    claim: (line) => `had ${line}+ shots`,
    pick: (m) => (m.shots_for ? m.shots_for : null), tone: "shots" },
];

// The windows the panel offers, smallest first. A window is only offered when the split
// actually holds that many games — "Last 20" over fourteen games is a label that lies, and
// team history is capped at 20 so it will only ever appear on the overall split.
export const WINDOWS = [3, 5, 10, 20];

// The shortest window worth offering. Two games is a pair of results, not a window.
export const MIN_WINDOW = 3;

/**
 * The window to actually use, given what the pool holds.
 *
 * ONE PLACE, because it is applied twice on a team card — once by the price ladder and once
 * by the chart under it — and those two must never disagree about which games they mean.
 * A chosen window larger than the pool SHRINKS to the pool rather than returning it
 * unchanged: the alternative is a chart drawing four bars under a label reading "Last 10".
 */
export function clampWindow(chosen, pool, min = MIN_WINDOW) {
  const max = Math.max(min, pool || 0);
  // null AND undefined BOTH MEAN "not chosen", and null has to be said out loud because
  // `Number(null)` is 0 and finite — so a card that had not been touched clamped its window
  // to zero games and drew nothing. The same trap as the shots column, in the same file.
  const chose = chosen !== null && chosen !== undefined && Number.isFinite(Number(chosen));
  const want = chose ? Number(chosen) : Math.min(10, max);
  return Math.max(1, Math.min(want, max, pool || max));
}

/** Which of WINDOWS this pool can honestly support, always at least the smallest. */
export function windowsFor(pool = []) {
  const fits = WINDOWS.filter((w) => pool.length >= w);
  return fits.length ? fits : [WINDOWS[0]];
}

// How many rungs to print above the floor. Three is enough to show where reliability runs
// out and short enough to stay one glanceable row on a phone.
export const RUNGS = 3;

// null AND undefined BOTH HAVE TO BE REJECTED EXPLICITLY, because `Number(null)` is 0 and
// finite. A game the provider did not cover carries null, and letting it through as a zero
// drags the floor to 0 — which silently destroys the strongest claim on the panel and
// leaves a number that looks like a measurement.
const num = (v) => {
  if (v === null || v === undefined || typeof v === "boolean") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** The values for one subject across the games shown, missing ones dropped. */
export function valuesFor(games = [], pick) {
  return (games || []).map((m) => num(pick(m || {}))).filter((v) => v !== null);
}

/**
 * The highest line every one of these games cleared.
 *
 * That is just the minimum, and naming it "floor" rather than "min" is the point: as a
 * betting line it reads "they have not been below this", which is the sentence a reader
 * wants. Returns null on no games, never 0 — a floor of 0 is a real and meaningful
 * result (a side kept to nothing once), so it must not be the same value as "no data".
 */
export function floorOf(values = []) {
  return values.length ? Math.min(...values) : null;
}

/** How many of these games reached `line`, with the count it was out of. */
export function hitsAt(values = [], line) {
  const n = values.length;
  const hits = values.filter((v) => v >= line).length;
  return { line, hits, n, pct: n ? Math.round((hits / n) * 100) : 0 };
}

/**
 * The ladder to print: the floor first, then the next few rungs up.
 *
 * STARTS AT THE FLOOR, so the first rung is always 100% and the reader's eye lands on the
 * claim that holds. Rungs above it are where it stops holding, which is the other half of
 * the same question — a side that is 5/5 at 4+ and 4/5 at 5+ is a different bet from one
 * that is 5/5 and 1/5.
 *
 * A floor of 0 starts at 1 instead. "0+ in all five" is true of every team that has ever
 * played and says nothing; the ladder should open on the lowest line that is a claim.
 */
export function ladderFor(values = [], rungs = RUNGS) {
  if (!values.length) return [];
  const start = Math.max(1, floorOf(values));
  const top = Math.max(...values);
  const out = [];
  for (let line = start; line <= start + rungs && line <= Math.max(top, start); line += 1) {
    out.push(hitsAt(values, line));
  }
  return out;
}

/**
 * One subject, reduced to what the strip prints.
 *
 * `every` is the line they never went below AS A CLAIM — null when the floor is 0, because
 * there is no line to name. `range` is there because two sides with the same floor and the
 * same average can still be 4,4,5,5 and 4,9,4,9, and the second is not the same bet.
 */
export function consistencyRow(games, subject) {
  const values = valuesFor(games, subject.pick);
  if (!values.length) return null;
  const floor = floorOf(values);
  const high = Math.max(...values);
  const avg = values.reduce((s, v) => s + v, 0) / values.length;
  return {
    key: subject.key,
    label: subject.label,
    tone: subject.tone,
    n: values.length,
    // The headline claim, or null when the floor is 0 and there is nothing to claim.
    every: floor > 0 ? floor : null,
    low: floor,
    high,
    range: high - floor,
    avg: Math.round(avg * 10) / 10,
    ladder: ladderFor(values),
  };
}

/** All three subjects for the games currently on screen. */
export function consistencyRows(games = []) {
  return SUBJECTS.map((s) => consistencyRow(games, s)).filter(Boolean);
}

// ------------------------- The chart the panel draws -------------------------
//
// SAME GRAMMAR AS THE PROBABILITY CHART AT THE TOP OF THE PAGE, deliberately: one vertical
// bar per column, brand cyan for the ones inside the claim and slate for the ones outside,
// a line picker under it, and the split named in words. A reader who has understood one of
// the two charts has understood both.
//
// AND IT IS THE OPPOSITE CONTENT, which is why the heading has to say so. The chart above
// draws the MODEL'S distribution — one bar per possible corner count, a forecast. This
// draws the GAMES THAT HAPPENED — one bar per match, a record. Identical styling over
// opposite meanings is only safe while each says which it is.

/** How many rungs either side of the floor the line picker offers. */
export const LINE_SPREAD = 3;

/**
 * One bar per game, OLDEST FIRST.
 *
 * The page's `recent` array is newest-first, and a chart read left to right has to run the
 * other way — the same direction as the distribution's ascending axis above it. Reversing
 * here rather than in the component keeps the order testable and stops the two charts
 * disagreeing about which end is "now".
 *
 * A game the provider did not cover is dropped, not drawn as a zero bar. A phantom empty
 * column would read as a game they were kept to nothing in.
 */
export function gameBars(games = [], pick, currentSeason) {
  return (games || [])
    .map((m, i) => ({ value: num(pick(m || {})), game: m || {}, i }))
    .filter((b) => b.value !== null)
    .reverse()
    .map(({ value, game, i }) => ({
      value,
      opponent: game.opponent || "",
      home: Boolean(game.home),
      date: game.date || null,
      season: game.season ?? null,
      // Marked rather than dropped, so the chart can say "this one is from last season"
      // without the window silently shrinking under the reader. See the season note below.
      prior: isPriorSeason(game, currentSeason),
      key: `${game.date || "?"}-${i}`,
    }));
}

/**
 * The lines worth offering, as buttons.
 *
 * CENTRED ON THE FLOOR rather than on the average, because the floor is the claim the
 * panel is built around and the picker should open on it. Never below 1 — "0+" is true of
 * every game ever played — and never above the highest value, which would offer a line
 * nothing in the window reached.
 */
export function lineWindow(values = [], spread = LINE_SPREAD) {
  if (!values.length) return [];
  const floor = Math.max(1, floorOf(values));
  const top = Math.max(...values);
  const lo = Math.max(1, floor - 1);
  const hi = Math.min(Math.max(top, lo), floor + spread);
  return Array.from({ length: Math.max(0, hi - lo + 1) }, (_, i) => lo + i);
}

/**
 * Where the picker starts: the line they never went below.
 *
 * So the chart opens fully lit, and the first thing a reader sees is the claim that holds
 * rather than one they have to go looking for.
 */
export function defaultLine(values = []) {
  return values.length ? Math.max(1, floorOf(values)) : null;
}

/**
 * The sentence for one subject: "4+ every game · 5+ in 4 of 5".
 *
 * Two facts, not five. The floor is what holds and the next rung is where it stops, and a
 * strip that printed the whole ladder in words would be the per-game table again with
 * more characters.
 */
export function consistencyLabel(row) {
  if (!row) return "";
  if (row.every === null) return `as low as 0 · up to ${row.high}`;
  const parts = [`${row.every}+ every game`];
  const next = row.ladder.find((l) => l.line === row.every + 1 && l.hits > 0);
  if (next) parts.push(`${next.line}+ in ${next.hits} of ${next.n}`);
  return parts.join(" · ");
}

/**
 * One line for the whole side: the two floors that matter, won and conceded.
 *
 * Sits on the panel header so the section says something before it is read. Match total is
 * left out deliberately — it is derived from the other two, and a header of three claims
 * is a paragraph.
 */
export function consistencyHeadline(rows = []) {
  const won = rows.find((r) => r.key === "won");
  const conc = rows.find((r) => r.key === "conceded");
  const bits = [];
  if (won?.every) bits.push(`wins ${won.every}+ every game`);
  if (conc?.every) bits.push(`concedes ${conc.every}+ every game`);
  if (!bits.length) return rows.length ? "no line held in every game" : "";
  return bits.join(" · ");
}

// ------------------------- Where last season starts -------------------------
//
// THE PROBLEM, IN THE NUMBER THAT PROMPTED IT. "Plymouth won 5+ in 7 of 10" — and two of
// those ten were last April. This season it is 5 of 7, which is a different claim about a
// different team: same badge, new manager, new formation, a third of the squad turned over,
// and a three-month gap in the middle where nothing was measured.
//
// WHY THE POOL MIXES SEASONS AT ALL, because it is not a bug to be removed. sync_real tops
// up from the previous season while the current one has produced fewer than STATS_CAP
// finished games. Without it a side has three games of history in August and every number on
// the site is noise. With it they have twenty and some of them are stale. Both readings are
// useful and only one of them was visible.
//
// SO IT IS SPLIT AND LABELLED, NOT DROPPED. The window the reader chose still shows what it
// shows; the games from before the break are marked, counted, and the this-season figure is
// stated beside the headline. A panel that silently discarded them would jump from ten games
// to five with no explanation, which is a worse surprise than the one it fixes.
//
// AN UNKNOWN SEASON IS TREATED AS CURRENT. Rows synced before the season stamp shipped carry
// none, and marking every one of them as stale would put a "last season" flag on a whole
// board for a week after deploy. The flag is therefore conservative: it appears only where
// the data positively says the game is older.

/** Is this game from a season before `current`? Unknown counts as current — see above. */
export function isPriorSeason(game, current) {
  const s = game?.season;
  if (s === null || s === undefined || current === null || current === undefined) return false;
  return Number(s) < Number(current);
}

/**
 * The window, split at the season boundary.
 *
 * `current` are the games from the season in progress and `prior` everything older, both
 * keeping the order they arrived in. `crosses` is the only thing most callers need: it says
 * whether this window reaches back past the break at all.
 */
export function splitSeasons(games = [], current) {
  const prior = (games || []).filter((g) => isPriorSeason(g, current));
  return {
    current: (games || []).filter((g) => !isPriorSeason(g, current)),
    prior,
    crosses: prior.length > 0,
  };
}

/**
 * The same claim over this season only, for a window that crosses the break.
 *
 * Returns null when the window does not cross one, because then it is the same number as the
 * headline and printing it twice invites the reader to look for a difference.
 */
export function thisSeasonOnly(games, subject, line, current) {
  const { current: recent, crosses } = splitSeasons(games, current);
  if (!crosses) return null;
  const values = valuesFor(recent, subject.pick);
  if (!values.length) return null;
  return { ...hitsAt(values, line), games: recent.length };
}

/**
 * The sentence that goes on the panel and on the share image.
 *
 * NAMES THE GAP, not just the count. "2 from last season" is a fact; "2 from last season —
 * squad and formation may have changed since" is the reason it matters, and it is the half a
 * reader acts on.
 */
export function seasonNote(games = [], current) {
  const { prior } = splitSeasons(games, current);
  if (!prior.length) return "";
  const n = prior.length;
  return `${n} of these ${n === 1 ? "is" : "are"} from last season`
    + " — squad and formation may have changed since";
}
