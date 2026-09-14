// Which rows a reader may actually read, and how to draw the rest.
//
// The server sends the WHOLE board and takes the model's numbers off the rows beyond this
// reader's tier — see _preview in server.py. Those come back flagged `blurred: true`. That
// shape is deliberate: a count ("47 more for members") is an assertion, and forty-seven
// rows you can see the shape of is evidence. The rows do the selling.
//
// THE BLUR IS NOT THE GATE, and this file should not be read as though it were. The values
// behind it are already absent. This decides presentation only.

/** Is this row one the reader can actually read? */
export const isLocked = (row) => Boolean(row && row.blurred);

/** Class name for a row container, given the row. */
export const lockClass = (row, extra = "") =>
  `${extra} ${isLocked(row) ? "row-locked" : ""}`.trim();

/** How many of these rows are readable, and how many are not. */
export const lockCounts = (rows = []) => {
  const locked = rows.filter(isLocked).length;
  return { readable: rows.length - locked, locked, total: rows.length };
};

/**
 * The line under a board that says what is being held back and what unlocks it.
 *
 * TWO ASKS, because there are two states and they need different words. Signed out, the
 * next step is a free account — and saying so matters, because "members only" reads as
 * "pay me" and the actual next step costs nothing. Signed in, the next step is the
 * subscription.
 */
export const lockedPitch = ({ locked, signedIn, member }) => {
  if (member || !locked) return null;
  return signedIn
    ? { head: `${locked} more, blurred`,
        body: "Subscribing unlocks every row on every board, and the model's price beside each one." }
    : { head: `${locked} more, blurred`,
        body: "A free account shows you more of this board. Subscribing unlocks all of it." };
};
