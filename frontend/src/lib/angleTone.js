// COLOUR ENCODES DIRECTION FIRST, THEN STRENGTH.
//
// Two previous attempts failed in opposite ways. Five colours keyed to angle TYPE said
// nothing about whether an angle was worth having. Then one green for "strong" and faded
// for "weak" fixed that but created a worse problem: a fixture legitimately shows an over
// from one side's history and an under from the other's, and both rendered as the same
// green chip — the board appeared to recommend two opposing outcomes on one game, in
// identical colour.
//
// So direction is the first thing the colour carries, because it is the thing that must
// never be ambiguous:
//
//     GREEN   over streak that is SOLID — a real run, the reason the fixture is here
//     ORANGE  over streak that is running but not yet solid
//     RED     under streak — the other direction, never mistakable for an over
//     CYAN    mismatch — a corners-winning side against a leaky defence
//     WHITE   chase spot
//
// Strength is then carried WITHIN the hue: a solid angle is filled and bordered, a weak
// one keeps its colour and drops to a faded outline. Direction and confidence can be read
// separately, which the single-green scheme made impossible. Cyan for mismatch and white
// for chase match the Best Bets cards, so the two screens agree.
//
// Pure and separate from the component so it can be tested without a DOM or a router.
export const TONE = {
  over_solid: { on: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
                off: "text-emerald-400/50 border-emerald-500/20 bg-transparent" },
  over_live: { on: "text-amber-400 border-amber-500/40 bg-amber-500/10",
               off: "text-amber-400/50 border-amber-500/20 bg-transparent" },
  under: { on: "text-red-400 border-red-500/40 bg-red-500/10",
           off: "text-red-400/50 border-red-500/20 bg-transparent" },
  mismatch: { on: "text-cyan-400 border-cyan-500/40 bg-cyan-500/10",
              off: "text-cyan-400/50 border-cyan-500/20 bg-transparent" },
  chase: { on: "text-zinc-100 border-zinc-300/40 bg-zinc-300/10",
           off: "text-zinc-300/50 border-zinc-400/20 bg-transparent" },
};

/**
 * Tone for one angle. An UNDER stays red whether or not it is solid — direction outranks
 * confidence, because mistaking the direction is the expensive error and mistaking the
 * confidence is not.
 */
export function toneFor(kind, strong) {
  if (kind === "chase") return TONE.chase;
  if (kind === "mismatch") return TONE.mismatch;
  if (String(kind).startsWith("under")) return TONE.under;
  return strong ? TONE.over_solid : TONE.over_live;
}

/** The class string actually applied, given the angle's strength. */
export const toneClass = (kind, strong) => (strong ? toneFor(kind, strong).on
                                                   : toneFor(kind, strong).off);
