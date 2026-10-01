// WHY THE GAMES THAT HIT HIT, AND WHY THE OTHERS DID NOT.
//
// The chart says a side reached 6+ in eight of ten. It does not say what was different about
// the two that did not, and that is the question a reader actually has before backing it
// again: was the miss a quiet afternoon with no shots, or a game they led from the tenth
// minute and never had to chase?
//
// So this splits the same games by whether they cleared the line and compares the two groups
// on the things that plausibly drive a corner count — shot volume, and whether they were
// behind. Nothing is fetched: every field is already on the rows the chart draws.
//
// IT IS A COMPARISON, NOT A CORRELATION COEFFICIENT. An r over eight games is a number with a
// confident face and almost no information — the sample cannot support it, and printing one
// would invite exactly the over-reading this file exists to avoid. "Their 6+ games averaged
// 18 shots against 13 in the others" is the same fact, carries its own sample size, and
// cannot be mistaken for a model output.
//
// AND IT DESCRIBES, IT DOES NOT PREDICT. measure_chase_board replayed orderings built from
// this class of evidence against a null and none of them ranked. These sentences explain
// what happened; they are not a reason to weight the next one.

import { hitsAt, valuesFor, SUBJECTS } from "./consistency";

const WON = SUBJECTS.find((s) => s.key === "won");

// Below this in either group there is nothing to compare — one game is an anecdote and the
// difference between two averages of one is noise wearing a decimal point.
export const MIN_GROUP = 2;

// How far apart two averages have to be before the gap is worth a sentence. Shots run in the
// teens, so two is a real difference and half of one is rounding.
export const SHOT_GAP = 2;

const avg = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Split the games shown into the ones that reached `line` and the ones that did not. */
export function splitByLine(games = [], line) {
  const hit = [];
  const miss = [];
  (games || []).forEach((g) => {
    const v = num(WON.pick(g || {}));
    if (v === null) return;          // uncovered games belong to neither group
    (v >= line ? hit : miss).push(g);
  });
  return { hit, miss };
}

/**
 * Shot volume in the games that hit against the ones that did not.
 *
 * A ZERO SHOT COUNT IS NOT REPORTED, NOT ZERO SHOTS. sync_real coerces a missing count to 0
 * because the live lambda consumes it and must not see null — the same trap the shots column
 * on the chart has to dodge — so a 0 here would drag an average down and invent a difference
 * that is really a coverage gap.
 */
export function shotSplit(hit = [], miss = []) {
  const shots = (rows) => rows.map((g) => num(g?.shots_for)).filter((v) => v);
  const h = shots(hit);
  const m = shots(miss);
  if (h.length < MIN_GROUP || m.length < MIN_GROUP) return null;
  const hi = avg(h);
  const lo = avg(m);
  return {
    hit: Math.round(hi * 10) / 10,
    miss: Math.round(lo * 10) / 10,
    gap: Math.round((hi - lo) * 10) / 10,
    hitGames: h.length,
    missGames: m.length,
  };
}

/**
 * How often each group was behind at half-time.
 *
 * `ht_state` arrives as a word from the backend — "trailing", "level", "leading" — so this
 * reads the label rather than re-deriving a state from goals the page may not have.
 */
export function chaseSplit(hit = [], miss = []) {
  const trailing = (rows) => rows.filter((g) => g?.ht_state === "trailing").length;
  const known = (rows) => rows.filter((g) => g?.ht_state).length;
  const hk = known(hit);
  const mk = known(miss);
  if (hk < MIN_GROUP || mk < MIN_GROUP) return null;
  return {
    hitTrailing: trailing(hit), hitGames: hk,
    missTrailing: trailing(miss), missGames: mk,
  };
}

/**
 * The sentences the panel prints, in plain words.
 *
 * Returns an empty list where the groups are too small or the gaps too narrow, because a
 * panel that always finds something to say is one nobody believes the fourth time.
 */
export function whyItHit(games = [], line) {
  if (!line) return [];
  const { hit, miss } = splitByLine(games, line);
  const out = [];

  const shots = shotSplit(hit, miss);
  if (shots && Math.abs(shots.gap) >= SHOT_GAP) {
    const more = shots.gap > 0;
    out.push({
      key: "shots",
      title: more ? "They shoot more in the games that land"
                  : "Shot volume does not explain it",
      detail: more
        ? `${shots.hit} shots a game in the ${shots.hitGames} that reached ${line}+, against `
          + `${shots.miss} in the ${shots.missGames} that did not.`
        : `${shots.hit} shots in the games that reached ${line}+ against ${shots.miss} in the `
          + "ones that did not — the misses were not quiet afternoons.",
    });
  } else if (shots) {
    out.push({
      key: "shots_flat",
      title: "Shot volume looks the same either way",
      detail: `${shots.hit} a game in the games that reached ${line}+ and ${shots.miss} in the `
        + "rest. Whatever separates them, it is not how often they shot.",
    });
  }

  const chase = chaseSplit(hit, miss);
  if (chase) {
    const hitRate = chase.hitTrailing / chase.hitGames;
    const missRate = chase.missTrailing / chase.missGames;
    if (hitRate - missRate >= 0.3) {
      out.push({
        key: "chased",
        title: "The games that landed were games they were chasing",
        detail: `Behind at half-time in ${chase.hitTrailing} of the ${chase.hitGames} that `
          + `reached ${line}+, against ${chase.missTrailing} of ${chase.missGames} in the rest.`
          + " A side that has to come back takes corners.",
      });
    } else if (missRate - hitRate >= 0.3) {
      out.push({
        key: "led",
        title: "They landed it without needing to chase",
        detail: `Behind at half-time in only ${chase.hitTrailing} of the ${chase.hitGames} that `
          + `reached ${line}+. The corners came from being on top, not from coming back.`,
      });
    }
  }

  return out;
}
