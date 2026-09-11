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

export const fixtureStreakShare = ({ fixture = {}, streaks = [], form = [],
                                     leagueName = "" }) => (limit) => {
  if (!streaks.length) return "";
  // THE SAME OPENING AS THE CHANNEL POST. Both are about one game and go out within an
  // hour of each other, so they name the day, the league and the fixture identically —
  // see postHeader. It costs a couple of rows' worth of characters on X, which fitToPost
  // absorbs by showing fewer streaks rather than by cutting one short.
  const head = postHeader({ fixture, leagueName }).join("\n");
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

// ----------------------------- The picks, reviewed -----------------------------
//
// Monday reports on the angles actually posted to the channel, which is a stronger claim
// than the streak board's: those were a person's picks, named in advance, and this says
// how they went. Evidence that the thing being sold works.
//
// ONLY WHAT WAS CLAIMED BEFORE KICK-OFF. The backend already splits posted angles into
// `claimed` and `recalled` by a server-clock stamp, and only the first can count — a rate
// you can add winners to afterwards is not a rate. This takes the claimed list and does
// not offer a way to pass the other one, so the split cannot be undone by a caller.
//
// THE LINE IS PUBLISHED HERE, unlike on the streak results post. That post withholds it
// because those runs are still live and the line is still the product. These are settled:
// the bet is over, the line has no value left, and a record whose rows cannot be checked
// against the actual game is an advert rather than a record. The site's own results page
// publishes it for exactly the same reason.

/** How long a Monday review looks back. A week, because that is what Monday reports on. */
export const REVIEW_DAYS = 7;

/**
 * "How the VIP picks landed — 4/6 last week", and the rows behind it.
 *
 * Counts and voids and unsettled games are all declared, same discipline as
 * streakResultShare: a week reported as 4/4 that was really 4/4 plus two stake-backs and
 * three still running is a different week, and the reader has no way to tell.
 */
export const picksReview = ({ rows = [], channel = "VIP", days = REVIEW_DAYS,
                              now = Date.now() } = {}) => (limit) => {
  const since = now - days * 86400000;
  const recent = rows.filter((r) => {
    const t = r.kickoff ? new Date(r.kickoff).getTime() : NaN;
    return Number.isFinite(t) && t >= since && t <= now;
  });
  const graded = recent.filter((r) => r.result === "win" || r.result === "loss");
  if (!graded.length) return "";

  const landed = graded.filter((r) => r.result === "win").length;
  const voided = recent.filter((r) => r.result === "void" || r.result === "push").length;
  const pending = recent.filter((r) => !r.result || r.result === "pending").length;

  // A TRIMMED RESULTS POST MUST STILL SHOW A MISS — the same rule, and the same reason:
  // the first N rows can happen to be all wins, and an honest "4/6" headline over a clean
  // sweep is a true count and a false impression.
  let shown = graded.slice(0, limit);
  const missed = graded.filter((r) => r.result === "loss");
  if (missed.length && !shown.some((r) => r.result === "loss")) {
    shown = [...shown.slice(0, Math.max(0, shown.length - 1)), missed[0]];
  }

  const mark = { win: "✅", loss: "❌" };
  const lines = shown.map((r) => {
    const line = r.line_label ? ` ${r.line_label}` : "";
    const got = r.value != null ? ` — ${r.value} corners` : "";
    return `${flagBullet(r.league_id)} ${r.name}${line}${got} ${mark[r.result]}`;
  });

  const voids = voided ? `\n${voided} void (exact line — stake back)` : "";
  const left = pending ? `\n${pending} still to settle` : "";
  return `How the ${channel} picks landed — ${landed}/${graded.length} last week:\n`
    + lines.join("\n") + more(graded.length, limit) + voids + left;
};

/** "Sat 11:30am" — inside a weekend card the month is noise; the day is not. */
export const postDayTime = (iso) => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  return `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${postTime(iso)}`;
};

/**
 * The whole weekend, sent to the paid channel on Friday.
 *
 * WHY THIS EXISTS SEPARATELY FROM THE DAILY POST. The public post goes out on the day of
 * the game, which is the worst moment to be told about it: by Saturday lunchtime the
 * market has had all week to find the same game and the price has gone. Someone paying
 * monthly should be looking at Sunday's card on Friday, while it is still there to take.
 * That is the product — not better information, EARLIER information.
 *
 * SO THIS CARRIES THE MODEL'S NUMBERS and the public posts do not. It goes to the people
 * who have bought exactly that number.
 *
 * NOT TRIMMED TO 280. Telegram has no limit, and this is a card to work from rather than
 * an advert, so every qualifying game goes in — ordered by KICK-OFF, which is the order
 * someone actually placing them needs, rather than by how good they are.
 */
export const weekendCard = ({ rows = [], generatedAt = null } = {}) => {
  const run = (r) => Number(r?.streak?.length) || 0;
  const live = (rows || []).filter((r) => r?.next_fixture?.date && run(r) >= 2);
  if (!live.length) return "";
  const sorted = [...live].sort(
    (a, b) => new Date(a.next_fixture.date) - new Date(b.next_fixture.date));

  const lines = sorted.map((r) => {
    const fx = r.next_fixture;
    const home = fx.is_home ? r.name : fx.opponent;
    const away = fx.is_home ? fx.opponent : r.name;
    const prob = Number(r.projection?.prob);
    const fair = Number(r.projection?.fair_odds);
    // "Not priced" and "no chance" are different facts, so an unpriced row says neither.
    const model = Number.isFinite(prob) && prob > 0
      ? ` · ${Math.round(prob)}%${Number.isFinite(fair) ? ` (${fair.toFixed(2)})` : ""}`
      : "";
    const when = postDayTime(fx.date);
    return `${flagBullet(r.league_id, "•")} ${home} v ${away}${when ? ` · ${when}` : ""}\n`
      + `   ${run(r) >= GAME_FIRE_RUN ? "🔥" : "🚩"} ${r.name} ${r.line_label || ""} — `
      + `${run(r)} in a row${model}`;
  });

  const stamp = generatedAt ? postDayTime(generatedAt) : "";
  return `🗓 Weekend corner card — ${sorted.length} angle${sorted.length === 1 ? "" : "s"}\n\n`
    + `${lines.join("\n\n")}\n\n`
    // THE FAIR PRICE IS A BAR, NOT A TIP. Said outright, because a card of percentages
    // read without it looks like a list of bets rather than a list of prices to beat.
    + "The number in brackets is the fair price — the model's own. Anything shorter than "
    + "that is not worth taking, however long the run is."
    + (stamp ? `\nBuilt ${stamp}, before the weekend's prices move.` : "");
};

// ----------------------------- One game, posted whole -----------------------------
//
// A board is a list; this is a game. The fixture boards fit six rows in a post by giving
// each one a single cramped line, which reads as a list of names and prices — fine for
// someone already looking for a bet, useless as an advert. One game across three lines
// has room to say when it is, who is playing, and why it is worth a look.
//
// WHAT MAKES IT THE GAME OF THE DAY is not the longest run. A streak is the hook, but a
// line that keeps landing and is still unlikely to land again is a bad advert: it goes out
// free, nobody sees a price next to it, and when it misses it just looks wrong. So the run
// only breaks ties among lines the model actually likes.

// Above this, a run is worth a fire rather than a flag. Same tier as FIRE_RUN — a run that
// stands out from the ones it would be listed beside.
export const GAME_FIRE_RUN = 8;
// A line the model makes more likely than not. Below this the run is carrying the post on
// its own, which is exactly the post that ages badly.
export const GAME_MIN_PROB = 50;

/**
 * The one row worth posting today.
 *
 * Prefers lines the model gives an even chance or better, ranked by how long the run is.
 * Where nothing clears that bar the ranking INVERTS — best probability first, run second —
 * because the reason to drop the bar is that there is no strong line today, and answering
 * that with the longest shot on the board would be the opposite of the intent.
 */
export const pickGame = (rows = [], minProb = GAME_MIN_PROB) => {
  const run = (r) => Number(r?.streak?.length) || 0;
  const prob = (r) => Number(r?.projection?.prob ?? 0);
  const live = (rows || []).filter((r) => r?.next_fixture?.date && run(r) >= 2);
  if (!live.length) return null;
  const strong = live.filter((r) => prob(r) >= minProb);
  const byRun = (a, b) => (run(b) - run(a)) || (prob(b) - prob(a));
  const byProb = (a, b) => (prob(b) - prob(a)) || (run(b) - run(a));
  return [...(strong.length ? strong : live)].sort(strong.length ? byRun : byProb)[0];
};

/**
 * That game, in three lines:
 *
 *   📅 Friday 11th September @ 11:00am
 *   🇯🇵 J-League / Kashima v Urawa
 *   🔥 Kashima 6+ corners in 9 straight / 🎯 averaging 8.2 a game
 *
 * NO PRICE, same rule as every other public post. The run and the average are facts about
 * games already played, which anyone could look up; the model's number is the product.
 */
export const gameShare = ({ row = {} } = {}) => () => {
  const fx = row?.next_fixture;
  if (!fx?.date) return "";
  const home = fx.is_home ? row.name : fx.opponent;
  const away = fx.is_home ? fx.opponent : row.name;
  if (!home || !away) return "";

  const day = postDate(fx.date);
  const time = postTime(fx.date);
  const when = [day, time].filter(Boolean).join(" @ ");
  const league = row.league_name || "";
  const where = `${flagBullet(row.league_id, "")} ${league}`.trim();

  const run = Number(row.streak?.length) || 0;
  const marks = [];
  if (run >= 2 && row.line_label) {
    marks.push(`${run >= GAME_FIRE_RUN ? "🔥" : "🚩"} ${row.name} ${row.line_label} `
      + `corners in ${run} straight`);
  }
  // Trending form, in the only sense this post is about: how many corners they are
  // actually winning. Dropped rather than guessed where the window never reported one.
  if (row.avg != null) marks.push(`🎯 averaging ${row.avg} a game`);

  // NO MODEL NUMBER HERE. It was added and taken back out on purpose: a probability and a
  // fair price are the same fact written two ways — 79% IS 1.26 — so printing the
  // percentage on a public post gives away the price, which is the thing the channel
  // sells. The run and the average stay, because those are facts about games already
  // played that anyone could count for themselves.
  //
  // It is still SHOWN to whoever is about to post, just not inside the post: the draft
  // carries the model's number in its own note line (see tools/social_draft.mjs), which
  // reaches the Telegram message header and never the tweet.
  return [when && `📅 ${when}`, `${where} / ${home} v ${away}`.trim(), marks.join(" / ")]
    .filter(Boolean).join("\n");
};
//
// The VIP channel gets a pick written to a fixed shape — date, league, fixture, line,
// price, model price, then the evidence. It was being typed out by hand every time, which
// is slow and, more to the point, is how the model price in the post drifts from the model
// price on the screen it was read off.
//
// TWO AUDIENCES, ONE SET OF FACTS. The channel post carries the price, the stake and the
// book; the X post carries neither. That split is the product — the reasoning is the
// advert and the price is the thing being sold — so it is enforced here, in the builder,
// rather than left to whoever is posting to remember at 1am.

const ORDINAL = (n) => {
  const t = n % 100;
  if (t >= 11 && t <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" })[n % 10] || "th"}`;
};

/** "Thursday 10th September" — the date line a pick opens with. */
export const postDate = (iso) => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  return `${d.toLocaleDateString("en-GB", { weekday: "long" })} `
    + `${ORDINAL(d.getDate())} ${d.toLocaleDateString("en-GB", { month: "long" })}`;
};

/** "12:30am" — the reader's own clock, same as everywhere else on the site. */
export const postTime = (iso) => {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-GB", { hour: "numeric", minute: "2-digit", hour12: true })
    .replace(/\s/g, "").toLowerCase();
};

/**
 * The lines EVERY fixture post opens with, wherever it is going.
 *
 *   📅 Thursday 10th September
 *   🇧🇷 Série B @ 12:30pm
 *   🏟️ Operario-PR v CRB
 *
 * Shared rather than written twice. The channel post and the X post are about the same
 * game and go out within an hour of each other, and two copies of this is exactly how one
 * of them ends up saying "Sat 15:00" while the other says "Thursday 10th September" — the
 * kind of difference a reader notices and cannot explain.
 *
 * Every line drops itself when it has nothing to say, so a fixture with no date or no
 * league still produces a header rather than a row of stray emoji.
 */
export const postHeader = ({ fixture = {}, leagueName = "" }) => {
  const day = postDate(fixture.date);
  const when = postTime(fixture.date);
  const league = leagueName || fixture.league_name || "";
  const where = `${flagBullet(fixture.league_id, "")} ${league}`.trim()
    + (when ? ` @ ${when}` : "");
  return [
    day && `📅 ${day}`,
    where || null,
    fixture.home_name && fixture.away_name
      && `🏟️ ${fixture.home_name} v ${fixture.away_name}`,
  ].filter(Boolean);
};

/** "6+" from a 5.5 line — how the line is said, not how it is stored. */
export const plusLine = (line) => `${Math.ceil(Number(line))}+`;

/** What the pick is, in words: "6+ Operario-PR corners", "10+ match corners". */
export const pickLabel = (market = {}, homeName = "", awayName = "") => {
  const plus = plusLine(market.line);
  if (market.group === "total") return `${plus} match corners`;
  return `${plus} ${market.group === "home" ? homeName : awayName} corners`;
};

// Which pool the ladder actually measured. corner_counts widens a thin venue split to all
// games and reports that it did — so the sentence names the venue only when the venue is
// what was counted.
const scopeWords = (scope) =>
  scope === "home" ? "at home" : scope === "away" ? "on the road" : "in their last games";

/**
 * "Operario-PR have won 4+ corners in 10/10 at home. 5+ in 9/10. 6+ in 7/10."
 *
 * Rungs that never landed are dropped rather than printed as 0/10: a ladder is evidence
 * for the pick, and "7+ in 0/10" is a line nobody was being offered anyway.
 */
export const wonLadder = (team, won = {}) => {
  const games = won.games || 0;
  const rungs = Object.entries(won.hits || {})
    .map(([line, hits]) => ({ line: Number(line), hits }))
    .filter((r) => r.hits > 0)
    .sort((a, b) => a.line - b.line);
  if (!games || !rungs.length) return "";
  const [first, ...rest] = rungs;
  return `🔥 ${team} have won ${first.line}+ corners in ${first.hits}/${games} `
    + `${scopeWords(won.scope)}.`
    + rest.map((r) => ` ${r.line}+ in ${r.hits}/${games}.`).join("");
};

// WHAT MAKES A GAME "OPEN". Both halves have to be true for the verdict to be earned: a
// defence that ships corners, and a side that scores early enough to stretch the game.
// A league team averages around 5 corners conceded, so 5.5 is "leakier than most"; 6 in 10
// first-half goals is a side that usually makes something happen before the break.
export const LEAKY_CONCEDED = 5.5;
export const EARLY_RATE = 0.6;

/**
 * The opponent's half of the case, and a verdict ONLY WHERE IT IS EARNED.
 *
 * The line in the channel reads "…so this should be an open, stretched game rather than a
 * dead one", which is a conclusion, not a statistic. Printed unconditionally it would sit
 * under a tight defence that never scores early and say the opposite of what the numbers
 * underneath it say. So the facts are always stated and the conclusion is attached only
 * when both halves clear their bar — and the ✅ goes with the conclusion, never with the
 * facts alone.
 */
export const openGameCase = (opponent, conceded = {}, fh = {}) => {
  const parts = [];
  const leaky = conceded.avg != null && conceded.avg >= LEAKY_CONCEDED;
  if (conceded.avg != null) parts.push(`concede ${conceded.avg} per game`);
  const early = fh.games > 0 && fh.hits / fh.games >= EARLY_RATE;
  // Stated only where it was measured: fh_goals_for is missing on leagues the sync has
  // not covered, and "score in the first half in 0/0" is a claim about the data.
  if (fh.games > 0) parts.push(`score in the first half in ${fh.hits}/${fh.games}`);
  if (!parts.length) return "";
  const both = leaky && early;
  const verdict = both
    ? " — so this should be an open, stretched game rather than a dead one."
    : ".";
  return `${both ? "✅" : "📊"} ${opponent} ${parts.join(" AND ")}${verdict}`;
};

const MODEL_WHO = { home: "for the hosts", away: "for the visitors", total: "in the match" };

/**
 * The pick as the VIP channel gets it.
 *
 * `result` is the settled outcome and is the ONLY thing that changes between the post
 * that goes out before kick-off and the one that goes out after — which is why it is a
 * parameter rather than a second builder. Two builders would drift, and the drift would
 * show up as a results post whose numbers disagree with the pick it is reporting on.
 */
export const telegramPick = ({
  fixture = {}, market = {}, card = {}, lambdas = {},
  price, book = "", stake, link = "", result = null,
}) => {
  const side = market.group === "total" ? null : (card[market.group] || null);

  const head = [
    ...postHeader({ fixture }),
    `🚩 ${pickLabel(market, fixture.home_name, fixture.away_name)}`,
  ];

  // The price line only exists if there IS a price. A pick posted without one is still a
  // pick; a line reading "[] via 💸 u" is just a broken post.
  const priced = price != null && price !== "";
  if (priced) {
    const mark = result === "win" ? " ✅" : result === "loss" ? " ❌"
      : result === "void" ? " ➖" : "";
    head.push(`📈 [${Number(price).toFixed(2)}]${book ? ` via ${book}` : ""}`
      + (stake ? ` 💸 ${stake}u` : "") + mark);
  }
  if (market.fair_odds != null) {
    // The EV tick is about the PRICE being worth taking, and is a different fact from
    // whether the bet won — so it stays on the model line even on a results repost.
    const ev = market.ev != null
      ? ` | EV: ${market.ev > 0 ? "+" : ""}${market.ev.toFixed(1)}%${market.ev > 0 ? " ✅" : " ❌"}`
      : "";
    // The price and the percentage are the same fact, and the channel gets both: the
    // price is what a bookmaker's number is compared against, the percentage is what it
    // means. Quoting only one leaves the reader converting in their head.
    const pct = market.prob != null ? ` (${Math.round(market.prob)}%)` : "";
    head.push(`📊 Model price: ${market.fair_odds.toFixed(2)}${pct}${ev}`);
  }

  const body = [];
  if (side) {
    const ladder = wonLadder(side.team, side.won);
    if (ladder) body.push(ladder);
    const opp = openGameCase(side.opponent, side.opp_conceded, side.opp_fh);
    if (opp) body.push(opp);
  }

  const lam = lambdas[market.group];
  const tail = lam != null
    ? `📊 Model: ${lam.toFixed(2)} expected corners ${MODEL_WHO[market.group] || ""}`.trim()
      + (link ? `  ${link}` : "")
    : (link || "");

  return [head.join("\n"), ...body, tail].filter(Boolean).join("\n\n");
};

// THERE IS NO PUBLIC VERSION OF THIS POST, and that is the product working as intended.
//
// A tease was built here that carried the reasoning — the ladder and the opponent's
// defending — with the price stripped out. That is the wrong half to keep. The reasoning
// IS the thing being sold: it is what a subscriber is paying to read, and posting it free
// on X leaves the channel selling only a price anyone can get from a bookmaker.
//
// What goes to X is the streak board (fixtureStreakShare above): a team, a line, how long
// it has been landing, and the game state around it. Enough to be worth a click, and
// nothing that answers "why" — the why is behind the subscription.
