// WHAT WOULD MAKE THIS LINE LAND, AND WHAT WOULD NOT.
//
// The page already argued about the game — who scores first, who chases, who gets carded.
// What it never argued about was the BET: a reader could see "6+ corners" priced and a list
// of things that might change the match, and had to join the two up themselves.
//
// So this takes a LINE and says what is for it and what is against it, out of evidence that
// is already on the page. Nothing here is fetched and nothing here is modelled — every row
// is a count of games that have been played, which is what lets it sit beside a measured
// price without competing with it.
//
// FOR AND AGAINST, NOT A SCORE. The temptation is to add these up and print a verdict, and
// that would be a new model with no measurement behind it — measure_chase_board spent a day
// showing that a plausible ordering of exactly this kind of evidence does not rank. Two
// lists let a reader weigh them; one number would be a claim nobody checked.
//
// THE MOST IMPORTANT ROW IS OFTEN AGAINST. A page that only lists reasons to bet is an
// advert, and the against side is where the useful ones live: a record leaning on last
// season, a sample too thin to carry a rate, a line sitting above what the model actually
// projects.

import { floorOf, hitsAt, valuesFor, SUBJECTS, splitSeasons } from "./consistency";

const WON = SUBJECTS.find((s) => s.key === "won");
const CONCEDED = SUBJECTS.find((s) => s.key === "conceded");

// A rate at or above this is worth calling support; at or below the floor it is worth
// calling a problem. Between them it is neither, and saying so would be padding.
export const STRONG = 0.7;
export const WEAK = 0.4;

// Below this a rate is not a rate — the same floor the rest of the site uses for a window.
export const MIN_SAMPLE = 5;

const pct = (h, n) => (n ? Math.round((h / n) * 100) : 0);

/**
 * Everything for and against `line` landing for this side.
 *
 * `games` and `oppGames` are each side's `recent` rows, already filtered to the venue and
 * window the reader is looking at — this does no selecting of its own, so the panel can
 * never disagree with the chart above it about which games it means.
 */
export function angleFactors({
  games = [], oppGames = [], line, lambda, currentSeason,
  teamName = "They", oppName = "The opponent",
} = {}) {
  const forIt = [];
  const against = [];
  if (!line) return { for: forIt, against };

  const values = valuesFor(games, WON.pick);
  const oppValues = valuesFor(oppGames, CONCEDED.pick);

  // --- THE RECORD AT THIS LINE. The single most direct piece of evidence there is. ---
  if (values.length) {
    const at = hitsAt(values, line);
    const rate = at.hits / at.n;
    const row = {
      key: "record",
      title: `${teamName} reached ${line}+ in ${at.hits} of ${at.n}`,
      detail: `${pct(at.hits, at.n)}% of the games shown above.`,
      games: at.n,
    };
    if (rate >= STRONG) forIt.push(row);
    else if (rate <= WEAK) against.push({ ...row, detail: row.detail
      + " This line is above what they usually manage." });

    // THE FLOOR IS A STRONGER CLAIM THAN THE RATE and deserves its own row: "never below 5"
    // is a different statement from "5+ in 8 of 10", and only one of them survives a bad day.
    const floor = floorOf(values);
    if (floor !== null && floor >= line && at.n >= MIN_SAMPLE) {
      forIt.push({
        key: "floor",
        title: `They have not been under ${line} once`,
        detail: `Their lowest in these ${at.n} games was ${floor}.`,
        games: at.n,
      });
    }
  }

  // --- THE DEFENCE THEY ARE MEETING. ---
  if (oppValues.length) {
    const at = hitsAt(oppValues, line);
    const rate = at.hits / at.n;
    if (rate >= STRONG) {
      forIt.push({
        key: "opp_leaky",
        title: `${oppName} concede ${line}+ in ${at.hits} of ${at.n}`,
        detail: "The defence on the other side has been giving this up regularly.",
        games: at.n,
      });
    } else if (rate <= WEAK) {
      against.push({
        key: "opp_solid",
        title: `${oppName} rarely concede ${line}+`,
        detail: `Only ${at.hits} of their last ${at.n}. Whatever this side usually does, they`
          + " have not been allowed to do it often against a defence like this.",
        games: at.n,
      });
    }
  }

  // --- WHERE THE LINE SITS AGAINST THE PROJECTION. ---
  //
  // Reads the model's own lambda rather than re-deriving one. A line a full corner above the
  // projection needs a better-than-usual game, and that is worth saying plainly next to a
  // record that might look convincing on its own.
  if (typeof lambda === "number" && lambda > 0) {
    if (line <= lambda - 1) {
      forIt.push({
        key: "line_low",
        title: "The line sits under the projection",
        detail: `The model projects about ${lambda.toFixed(1)} corners; this asks for ${line}.`,
      });
    } else if (line >= lambda + 0.5) {
      against.push({
        key: "line_high",
        title: "This asks for an above-average game",
        detail: `The model projects about ${lambda.toFixed(1)} corners and the line is ${line}.`
          + " It needs more than their usual.",
      });
    }
  }

  // --- WHAT THE RECORD IS MADE OF. Both of these are about whether the numbers above can
  //     carry the weight being put on them, which is why they are never on the FOR side. ---
  if (values.length && values.length < MIN_SAMPLE) {
    against.push({
      key: "thin",
      title: `Only ${values.length} games behind this`,
      detail: "Too few to read a rate from. Every percentage above moves a long way on one"
        + " result.",
      games: values.length,
    });
  }

  const { prior } = splitSeasons(games, currentSeason);
  if (prior.length) {
    against.push({
      key: "stale",
      title: `${prior.length} of these are from last season`,
      detail: "Squad, manager and formation may all have changed since. The record above is"
        + " not entirely about the side playing on the day.",
      games: prior.length,
    });
  }

  return { for: forIt, against };
}

/**
 * The backend's game-state and card factors, split the same way.
 *
 * They arrive already labelled `boost` or `risk`, which is the same distinction under
 * different words — so they are folded in rather than shown as a third list. `watch` and
 * anything unrecognised go to the against side, because an unclassified caveat is a reason
 * for care and never a reason for confidence.
 */
export function splitKeyFactors(rows = []) {
  const forIt = [];
  const against = [];
  (rows || []).forEach((f) => (f?.kind === "boost" ? forIt : against).push(f));
  return { for: forIt, against };
}

/** Both sources, merged, ready to render. */
export function anglePanel(opts = {}, keyFactorRows = []) {
  const a = angleFactors(opts);
  const b = splitKeyFactors(keyFactorRows);
  return { for: [...a.for, ...b.for], against: [...a.against, ...b.against] };
}
