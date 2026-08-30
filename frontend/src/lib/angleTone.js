// STREAKS CARRY THE COLOUR. Everything else gets out of their way.
//
// Three schemes have been tried. Five colours keyed to angle TYPE said nothing about
// whether an angle was worth having. One green for "strong" fixed that but painted an
// over and an under identically, so a row appeared to back both sides of a game. Colour
// then went direction-first, which fixed that but spent the three most legible colours on
// distinctions the reader did not need.
//
// Now the vivid colours are a STRENGTH LADDER on streaks, because a streak is what the
// board is mostly made of and how good it is, is the thing worth knowing at a glance:
//
//     ORANGE  a live streak — running, but short
//     CYAN    a strong streak — a real run behind it
//     GREEN   a solid pick — long enough to actually back
//
// Two things stay outside the ladder:
//
//     RED     an under streak, AT ANY STRENGTH. Direction is not a confidence level, and
//             mistaking an under for an over is the expensive error. It never goes green.
//     MUTED   mismatch and chase, in grey and white. They are real signals but the weaker
//             evidence — a mismatch is two averages pointed at each other with no hit rate
//             behind it — so they recede and let the streaks dominate the page.
//
// Pure and separate from the component so it can be tested without a DOM or a router.

// A run at or above this is a solid pick rather than merely a strong streak. Double
// BOARD_MIN_RUN (3), which is only the bar for being a run at all.
export const SOLID_RUN = 6;

export const TONE = {
  solid: { on: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10",
           off: "text-emerald-400/50 border-emerald-500/20 bg-transparent" },
  strong: { on: "text-cyan-400 border-cyan-500/40 bg-cyan-500/10",
            off: "text-cyan-400/50 border-cyan-500/20 bg-transparent" },
  live: { on: "text-amber-400 border-amber-500/40 bg-amber-500/10",
          off: "text-amber-400/50 border-amber-500/20 bg-transparent" },
  under: { on: "text-red-400 border-red-500/40 bg-red-500/10",
           off: "text-red-400/50 border-red-500/20 bg-transparent" },
  // deliberately low-contrast: present, readable, not competing with a streak
  mismatch: { on: "text-zinc-400 border-zinc-500/30 bg-zinc-500/10",
              off: "text-zinc-500/60 border-zinc-600/20 bg-transparent" },
  chase: { on: "text-zinc-200 border-zinc-400/30 bg-zinc-400/10",
           off: "text-zinc-300/50 border-zinc-500/20 bg-transparent" },
};

/**
 * Tone for one angle.
 *
 * `strong` is the backend's qualify flag (a run of BOARD_MIN_RUN or more); `streakLen` is
 * the length of the run that is actually alive. The ladder needs both, because "cleared
 * the bar" and "cleared it by a mile" are different claims and the binary flag cannot
 * tell them apart.
 */
export function toneFor(kind, strong, streakLen = 0) {
  if (kind === "chase") return TONE.chase;
  if (kind === "mismatch") return TONE.mismatch;
  if (String(kind).startsWith("under")) return TONE.under;
  if (!strong) return TONE.live;
  return (streakLen || 0) >= SOLID_RUN ? TONE.solid : TONE.strong;
}

/** The class string actually applied, given the angle's strength. */
export const toneClass = (kind, strong, streakLen) =>
  (strong ? toneFor(kind, strong, streakLen).on : toneFor(kind, strong, streakLen).off);

/** What the chip means, in one word — for the legend and the title attribute. */
export function toneLabel(kind, strong, streakLen = 0) {
  if (kind === "chase") return "chase spot";
  if (kind === "mismatch") return "mismatch";
  if (String(kind).startsWith("under")) return "under streak";
  if (!strong) return "live streak";
  return (streakLen || 0) >= SOLID_RUN ? "solid pick" : "strong streak";
}
