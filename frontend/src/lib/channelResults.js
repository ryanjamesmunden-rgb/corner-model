// The channel's monthly record — the numbers, in one place.
//
// WHY THIS IS ITS OWN FILE. The join page owned this list and the review card now needs the
// same months. Two copies of a results table is the one duplication that cannot be allowed
// here: they would disagree the first month somebody updated one of them, and the thing
// they would disagree about is what the account publicly claims it has made. The page and
// the card read this, or they read nothing.
//
// STATED FIGURES, NOT COMPUTED, AND THE LABEL SAYS SO. The site cannot verify these: its
// ledger holds the model's automated selections, not the picks actually sent out, so there
// is nothing here to check them against. Anything drawing these has to carry that line —
// a number a buyer cannot check is worth exactly what its source is worth, and dressing it
// as site-verified is the fastest way to lose someone.
//
// WHAT IS VERIFIABLE SITS BESIDE THEM, never merged into them: /api/results grades every
// streak the site published, before kick-off, off a frozen snapshot. That record is a hit
// rate with its denominator, not units, because those rows carry a line and no price. The
// two must stay visibly separate wherever they are shown together.
//
// EDIT THIS LIST EACH MONTH. It becomes computed — and checkable — once the picks actually
// sent out are logged through POST /api/picks with their prices.
//
// A MONTH STILL RUNNING CARRIES `partial: true`, which labels the row AND the total.
// September at +16 beside two closed months, with the total reading as final, is a true
// number arranged into a false impression. Drop the flag when the month closes.

/** Newest last, as the join page lists them. */
export const CHANNEL_RESULTS = [
  { period: "June - July", units: 17.14 },
  { period: "August", units: 20.73 },
  // CLOSED AT A LOSS, and it stays on the list. A results table that drops its losing
  // months is not a record, it is a selection — and the one month that proves the other
  // two are being reported honestly is the one that went the wrong way. The `partial` flag
  // is gone because the month is over; it read +16.00 month-to-date on 30 September and
  // finished here.
  { period: "September", units: -12.54 },
];

/** Where these came from, in one line, for anything that publishes them. */
export const SOURCE_NOTE = "Units as recorded in the channel. Every pick posted before "
  + "kick-off, at the price taken.";

/**
 * The most recent `n` periods, newest first — the shape a review card wants.
 *
 * NEWEST FIRST because a review leads on the month just gone; the join page's table reads
 * oldest first because it is showing a history. Same data, and neither reverses the other
 * in place.
 */
export const recentPeriods = (n = 3, rows = CHANNEL_RESULTS) =>
  [...(rows || [])].slice(-Math.max(1, n)).reverse();
