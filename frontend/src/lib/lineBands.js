// What each corner LINE has actually returned — read off the P&L, kept in one place.
//
// WHY THIS EXISTS. The streak board ranks by how high the line is and how long the run
// has lasted, and neither of those is how the bets have gone. Sorted by the board's own
// order, the first thing a digest offers is a 9+ on a nine-game run; sorted by what the
// book has paid, 9+ is the part of the sheet that has never won. The board is a measure of
// the FOOTBALL and this file is a measure of the BETTING, and the whole point of putting
// them beside each other is that they disagree.
//
// THE NUMBERS ARE STATED, NOT COMPUTED, AND EVERY CAPTION HAS TO SAY SO — the same rule
// channelResults.js keeps, for the same reason. These come from the P&L workbook, which is
// typed by hand: the site's ledger holds the model's automated selections, not the bets
// actually placed, so there is nothing here for the site to check them against. A number a
// reader cannot check is worth what its source is worth.
//
// WHAT THEY COVER, exactly, because the bands are useless if the scope is vague:
//
//   TEAM CORNER SINGLES ONLY — one side's own corners, bought on their own. 131 settled
//   bets, 21 June to 13 October 2026.
//
//   NOT bet builders (a builder settles as one bet and there is no honest way to charge
//   its P&L to one leg's line), NOT match totals (an "over 10+ corners" is not a 7+ team
//   line, and counting it as one is the mistake the first draft of this made: it put 11+
//   match totals in the 7+ band and reported that band at -36.7% on 27 bets instead of
//   -4.6% on 12), and NOT the side markets.
//
// BREAKEVEN IS STAKE-WEIGHTED — the strike rate the band's own average price needed, from
// total stake over total stake-times-price. A flat average of the odds would flatter the
// bands where the big bets were short.
//
// UPDATE THIS WHEN THE SHEET IS UPDATED, and move `asOf` with it. A band record that is
// three months stale reads exactly like a current one.

/** When the figures below were last read off the workbook. */
export const BANDS_AS_OF = "13 Oct 2026";

/** One line, for anything that publishes these. */
export const BANDS_SOURCE =
  `Your own P&L, team corner singles only, 21 Jun–${BANDS_AS_OF}. Typed by hand, not `
  + "graded by the site.";

/**
 * The three bands, in the order a digest should read them: the one that has paid first.
 *
 * `min`/`max` are inclusive and cover every line, so `bandOf` can never return nothing.
 * `verdict` is the one clause a reader needs if they read nothing else.
 */
export const LINE_BANDS = [
  {
    id: "money",
    min: 5,
    max: 6,
    label: "5+ and 6+",
    bets: 90,
    strike: 60.0,
    breakeven: 52.2,
    units: 48.47,
    verdict: "where the record is",
    // THE NOTE NEVER REPEATS `bandRecord`, which prints directly above it. The first
    // draft opened this one with "60% at a 52% breakeven" — the same clause, twice, two
    // lines apart — and a message that repeats itself is the one being replaced here.
    // What the note adds is the split the headline hides.
    note: "5+ is +25.98u on 45, 6+ is +22.49u on 45 — the two halves agree, which is the "
        + "main reason to believe the band.",
  },
  {
    id: "below",
    // FROM ZERO, not from 2. The board's own floor is 3, so a 2+ should never reach a
    // digest — but a band that does not cover every line means `bandOf` can return
    // nothing, and a row with no band is a row that gets rendered with no caption at all.
    min: 0,
    max: 4,
    label: "4+ and below",
    bets: 29,
    strike: 48.3,
    breakeven: 55.2,
    units: -12.9,
    verdict: "below the money band",
    // THE SPLIT INSIDE THIS BAND IS THE USEFUL PART. "Below the band" sounds like one
    // thing and is two: 4+ has broken even and 3+ is where the losses live. Nine bets is
    // nine, so this is a reason to look twice rather than a finding.
    note: "3+ is -12.24u on 9 at 33%; 4+ is +1.81u on 17 at 59%. Nearly all of the band's "
        + "loss is the 3+ rows.",
  },
  {
    id: "long",
    min: 7,
    max: Infinity,
    label: "7+ and up",
    bets: 12,
    strike: 33.3,
    breakeven: 43.9,
    units: -0.53,
    verdict: "too few to judge",
    // NOT "AVOID". Twelve bets at -0.53u is a rounding error, and calling it a losing
    // band would be reading a verdict off noise — the error the whole digest is meant to
    // stop. It is thin, it says it is thin, and it goes last because it is unproven
    // rather than because it is bad.
    note: "Not enough either way. Shown last because it is unproven, not because it is bad.",
  },
];

/** The band a line falls in. Never null — the bands cover every line. */
export const bandOf = (line) => {
  const n = Number(line);
  if (!Number.isFinite(n)) return null;
  return LINE_BANDS.find((b) => n >= b.min && n <= b.max) || null;
};

/** The band by id, for a caller that groups first and captions second. */
export const bandById = (id) => LINE_BANDS.find((b) => b.id === id) || null;

/**
 * The band's record as one line of prose, with its denominator attached.
 *
 * THE DENOMINATOR IS NOT OPTIONAL. "60% strike" is unfalsifiable; "60% of 90" can be
 * argued with, and the 7+ band only reads honestly because the 12 is right there next to
 * it. Same rule the record card keeps.
 */
export const bandRecord = (band) => {
  if (!band) return "";
  const sign = band.units >= 0 ? "+" : "";
  return `${band.bets} bets, ${band.strike.toFixed(0)}% at a `
       + `${band.breakeven.toFixed(0)}% breakeven, ${sign}${band.units.toFixed(2)}u`;
};
