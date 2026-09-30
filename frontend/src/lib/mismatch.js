// A STRONG ATTACK AGAINST A LEAKY DEFENCE, on one fixture.
//
// The two boards this site already has each tell half of this. The team-corner streaks say
// who keeps winning corners; the conceded streaks say who keeps shipping them. Neither can
// say the thing you actually want, which is that THOSE TWO ARE PLAYING EACH OTHER — and
// working it out by hand means holding one board in your head while you scroll the other.
//
// So this pairs them on the fixture: one side's corners-won record against the other side's
// corners-conceded record, over the same window, at a line BOTH of them clear.
//
// THE SHARED LINE IS THE WHOLE IDEA. "Arsenal won 5+ in 5 of 5" and "Brighton conceded 5+
// in 4 of 5" is one claim about one number. Quoting each side at its own best line —
// Arsenal 6+, Brighton 4+ — would read as stronger and mean less, because the two halves
// would no longer be about the same bet.
//
// BOTH DIRECTIONS, ALWAYS CONSIDERED. The away side attacking a leaky home defence is the
// same angle pointed the other way, and it is the one a home-biased eye misses.
//
// AND IT IS DESCRIPTION, NOT A PRICE. measure_chase_board replayed the conceded ordering
// against a floor measured on data with no edge in it and it did not rank, so this is a way
// to FIND a spot and never a reason to weight one. Every label here is past tense.
import { hitsAt, valuesFor, SUBJECTS } from "./consistency";

// Both halves have to be this reliable before the pairing is worth a section. 0.8 is
// "4 of 5" — the shape the angle is usually described in — and it is applied as a rate so
// it means the same thing over a window of 5 and of 10.
export const MIN_RATE = 0.8;

// Below this, a rate is not a rate. Three games at 3 of 3 is 100% of nothing much, and the
// panel would be quoting a coincidence as a pattern.
export const MIN_GAMES = 4;

// The highest line worth pairing on. Above this the claim stops being a corner bet and
// starts being a curiosity — and a line nobody prices is not an angle.
export const MAX_LINE = 9;

// AND A FLOOR, which a test found the hard way. Without one, two quiet sides pair at "2+"
// — both halves 5 of 5, both perfectly true, and every team in the league wins 2+ corners
// most weeks. It renders as a mismatch and is a joke, which is precisely why the streak
// board already carries OVER_LINE_FLOOR = 3 for its own ladder. Same number, same reason:
// below this a line is not a claim.
export const MIN_LINE = 3;

const WON = SUBJECTS.find((s) => s.key === "won");
const CONCEDED = SUBJECTS.find((s) => s.key === "conceded");

/**
 * The best line both sides clear, or null.
 *
 * Walks DOWN from the highest candidate and takes the first line where both halves reach
 * MIN_RATE, so the strongest shared claim wins rather than the safest one. Climbing up
 * instead would stop at the first line that works and report 3+ where 5+ was also true.
 */
export function sharedLine(attackValues, defenceValues, minRate = MIN_RATE) {
  if (!attackValues.length || !defenceValues.length) return null;
  const top = Math.min(MAX_LINE, Math.max(...attackValues), Math.max(...defenceValues));
  for (let line = top; line >= MIN_LINE; line -= 1) {
    const a = hitsAt(attackValues, line);
    const d = hitsAt(defenceValues, line);
    if (a.n && d.n && a.hits / a.n >= minRate && d.hits / d.n >= minRate) return line;
  }
  return null;
}

/**
 * One direction of the pairing: `attacker` wins corners, `defender` ships them.
 *
 * Returns null unless both halves have enough games AND both clear the rate at a shared
 * line. Null is the normal case — most fixtures are not a mismatch, and a section that
 * rendered on every game would mean nothing when it rendered on the right one.
 */
export function direction(attackGames, defenceGames, attacker, defender,
                          { minRate = MIN_RATE, minGames = MIN_GAMES } = {}) {
  const attackValues = valuesFor(attackGames, WON.pick);
  const defenceValues = valuesFor(defenceGames, CONCEDED.pick);
  if (attackValues.length < minGames || defenceValues.length < minGames) return null;
  const line = sharedLine(attackValues, defenceValues, minRate);
  if (line === null) return null;
  const attack = hitsAt(attackValues, line);
  const defence = hitsAt(defenceValues, line);
  return {
    attacker,
    defender,
    line,
    attack,
    defence,
    // What both halves are worth together, for ordering the two directions. The line
    // dominates — a shared 6+ is a better find than a shared 4+ however clean the 4+ is —
    // and the hit rates only break ties.
    strength: line * 100 + (attack.hits / attack.n) * 10 + (defence.hits / defence.n) * 10,
    // The bars the panel and the share image draw, oldest last as the endpoint sends them.
    attackValues,
    defenceValues,
  };
}

/**
 * Both directions on a fixture, strongest first.
 *
 * `homeGames` / `awayGames` are each side's `recent` array off the fixture payload.
 */
export function mismatches(homeGames, awayGames, homeName, awayName, opts = {}) {
  return [
    direction(homeGames, awayGames, homeName, awayName, opts),
    direction(awayGames, homeGames, awayName, homeName, opts),
  ].filter(Boolean).sort((a, b) => b.strength - a.strength);
}

/** "Arsenal won 5+ in 5 of 5 · Brighton conceded 5+ in 4 of 5" — the claim, in full. */
export function claimLine(m) {
  if (!m) return "";
  return `${m.attacker} won ${m.line}+ in ${m.attack.hits} of ${m.attack.n}`
    + ` · ${m.defender} conceded ${m.line}+ in ${m.defence.hits} of ${m.defence.n}`;
}

/** The one-liner for a section header: what to look at, without the arithmetic. */
export function headline(m) {
  if (!m) return "";
  const both = m.attack.hits === m.attack.n && m.defence.hits === m.defence.n;
  return both
    ? `${m.attacker} ${m.line}+ every game, ${m.defender} conceding ${m.line}+ every game`
    : `${m.attacker} ${m.line}+ against a defence shipping ${m.line}+`;
}

/** Is there anything to show? Most fixtures are not a mismatch. */
export function hasMismatch(rows = []) {
  return rows.length > 0;
}
