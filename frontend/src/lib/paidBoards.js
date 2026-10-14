// Which boards are actually behind the paywall — the padlock's only source of truth.
//
// WHY THIS IS ITS OWN FILE WITH A TEST. It used to be a map inside Scanner.jsx and it went
// four entries out of date for a week without anything noticing. On 7 Oct the server set
// READABLE_ROWS = None ("no trim for anybody: the stats are public"), so Form, Streaks,
// Perfect Games and the Chase Board started returning every row, unblurred, to a
// signed-out visitor. The padlocks stayed. The site spent a week telling strangers that
// two thirds of it was locked while handing them all of it.
//
// THAT IS THE EXPENSIVE DIRECTION. A board that is open but looks shut gets no clicks, so
// it may as well not be there — and it makes "the site is free" a claim the owner cannot
// make while looking at his own front page. Nothing on the API side could have caught it,
// because the API was the half that was right.
//
// THE RULE, AND IT IS THE ONLY ONE: a padlock means `require_member` on the server. Not
// "this is valuable", not "this is nearly paid", not "this used to be trimmed". If a
// board is served in full to a guest it carries no lock, however much it is worth.
//
// WHAT WOULD MAKE THIS WRONG AGAIN: putting a number back in READABLE_ROWS, which turns
// the open boards into trimmed previews. A trimmed board is not a closed one and does not
// obviously deserve the same padlock, so that change means answering the question again
// rather than silently restoring this list.

/**
 * Server-enforced member gates, by Value Finder tab id.
 *
 * `value` alone: /value-board is the one route carrying `require_member`, and unlike the
 * others it has no preview — its first few rows ARE the best bets on it, so a taste would
 * be the product.
 */
export const PAID_BOARDS = Object.freeze({ value: true });

/** Does this tab need a paid membership? */
export const isPaidBoard = (tab) => Boolean(PAID_BOARDS[tab]);

/**
 * Should a padlock be drawn for this reader on this tab?
 *
 * MEMBERS SEE NO LOCKS AT ALL, including on the board they have paid for — a padlock on
 * something you own reads as a failure to recognise you.
 */
export const showsLock = (tab, member) => !member && isPaidBoard(tab);
