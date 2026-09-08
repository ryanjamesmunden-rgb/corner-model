// WHAT THE COLOURS MEAN. One definition, used by every screen.
//
// Four schemes have been tried. Five colours keyed to angle TYPE said nothing about
// whether an angle was worth having. One green for "strong" painted an over and an under
// identically, so a row appeared to back both sides of a game. A strength ladder across
// green/cyan/orange fixed that, but spent three hues on one idea and left mismatches in a
// grey nobody looked at — which defeated the point of putting them on the board.
//
// Now there are FOUR meanings, and colour carries meaning only:
//
//     STRONG  green   solid, well-evidenced — the closest thing to a pick
//     STREAK  amber   a run that is live but wants watching
//     UNDER   rose    the bet is that something does NOT happen
//     EDGE    violet  a mismatch — the OPPONENT is the reason this is here
//
// How strong a strong thing is, is an ORDINAL question, so it is answered with intensity
// inside one hue rather than by spending a second hue on it. A long run is a filled chip;
// a shorter one is the same green, softer. That is the change that freed up a colour for
// mismatches, which now have their own.
//
// Cyan is NOT in this list on purpose. It is the brand and the interface — links, focus
// rings, the highlighted region of a chart. A colour cannot mean "this is a strong streak"
// on one part of the page and "this is a button" on another.
//
// COLOUR IS NEVER ALONE. The palette was validated against this surface and its worst
// all-pairs separation under deuteranopia is 6.9 (green vs rose — the one pair colour
// cannot fix). That is legal only alongside a second channel, so every tone carries an
// `icon` and a `label`, and every chip must render at least one of them. Do not add a
// fifth hue without re-running the validator.

// A run at or above this is a solid pick rather than merely a live one. Double
// BOARD_MIN_RUN (3), which is only the bar for being a run at all.
export const SOLID_RUN = 6;

export const TONE = {
  strong: {
    key: "strong", label: "solid pick", icon: "flame",
    on: "text-tone-strong-fg border-tone-strong/50 bg-tone-strong/15",
    off: "text-tone-strong-fg/60 border-tone-strong/25 bg-transparent",
    bar: "bg-tone-strong", dot: "bg-tone-strong-fg",
  },
  streak: {
    key: "streak", label: "live streak", icon: "flame",
    on: "text-tone-streak-fg border-tone-streak/50 bg-tone-streak/15",
    off: "text-tone-streak-fg/60 border-tone-streak/25 bg-transparent",
    bar: "bg-tone-streak", dot: "bg-tone-streak-fg",
  },
  under: {
    key: "under", label: "under streak", icon: "shield",
    on: "text-tone-under-fg border-tone-under/50 bg-tone-under/15",
    off: "text-tone-under-fg/60 border-tone-under/25 bg-transparent",
    bar: "bg-tone-under", dot: "bg-tone-under-fg",
  },
  edge: {
    key: "edge", label: "mismatch", icon: "swords",
    on: "text-tone-edge-fg border-tone-edge/50 bg-tone-edge/15",
    off: "text-tone-edge-fg/60 border-tone-edge/25 bg-transparent",
    bar: "bg-tone-edge", dot: "bg-tone-edge-fg",
  },
};

/**
 * Tone for one angle.
 *
 * `strong` is the backend's qualify flag (a run of BOARD_MIN_RUN or more); `streakLen` is
 * the length of the run actually alive. Both are needed, because "cleared the bar" and
 * "cleared it by a mile" are different claims and the binary flag cannot tell them apart.
 */
export function toneFor(kind) {
  if (kind === "mismatch" || kind === "chase") return TONE.edge;
  if (String(kind).startsWith("under")) return TONE.under;
  return TONE.strong;
}

/**
 * The tone an angle actually wears. An over-angle that has not cleared the run bar is a
 * live streak (amber) rather than a weak green — "not proven yet" is its own state, not a
 * dimmer version of proven.
 */
export function toneOf(kind, strong, streakLen = 0) {
  const base = toneFor(kind);
  if (base === TONE.strong && !strong) return TONE.streak;
  return base;
}

/** The class string actually applied. Filled once the evidence is there, outlined before. */
export function toneClass(kind, strong, streakLen = 0) {
  const t = toneOf(kind, strong, streakLen);
  const filled = t === TONE.strong ? (streakLen || 0) >= SOLID_RUN : !!strong;
  return filled ? t.on : t.off;
}

/** What the chip means, in a few words — for the legend and the title attribute. */
export function toneLabel(kind, strong, streakLen = 0) {
  if (kind === "chase") return "chase spot";
  if (kind === "mismatch") return "mismatch";
  if (String(kind).startsWith("under")) return "under streak";
  if (!strong) return "live streak";
  return (streakLen || 0) >= SOLID_RUN ? "solid pick" : "strong streak";
}

/** Icon name for the tone — the second channel that makes the colour legal. */
export const toneIcon = (kind, strong, streakLen = 0) => toneOf(kind, strong, streakLen).icon;
