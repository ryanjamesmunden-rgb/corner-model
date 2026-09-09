// Whether the browser will still let us hand a file to the OS.
//
// THE PROBLEM THIS EXISTS FOR. `navigator.share()` may only be called while a user gesture
// is still "live" — Chrome gives about five seconds from the tap. Making a story VIDEO
// takes 5.3 of them, so by the time the file exists the tap has expired and the share is
// refused with "Must be handling a user gesture to perform a share request". The still
// image sneaks in because drawing a canvas is fast; the video never could.
//
// So the share has to happen on a SECOND tap, and these two functions decide when to ask
// for one. They are split out here because the rule is the whole fix, and a rule that
// only runs inside a component on a phone is a rule nobody can test.

/**
 * Is a user gesture still live right now?
 *
 * `navigator.userActivation` is the standards answer and Chrome — the browser this
 * actually breaks on — has it. Where it is missing (Safari, notably) we assume yes and
 * let the attempt fail, which `isGestureError` then catches: an optimistic try costs one
 * caught exception, while assuming NO would put a needless second tap in front of every
 * user on a browser that might not have needed one.
 */
export const hasLiveGesture = (nav = typeof navigator !== "undefined" ? navigator : null) => {
  const ua = nav && nav.userActivation;
  return ua && typeof ua.isActive === "boolean" ? ua.isActive : true;
};

/**
 * Did this failure happen because the gesture had expired, rather than for a real reason?
 *
 * Matched on BOTH the name and the wording because browsers disagree: Chrome throws
 * NotAllowedError, and the message is the only place the cause is actually stated. A
 * false negative here shows the user a red error for something a second tap would fix,
 * which is what they were seeing before this existed.
 */
export const isGestureError = (err) => {
  if (!err) return false;
  if (err.name === "NotAllowedError") return true;
  const msg = String(err.message || "").toLowerCase();
  return msg.includes("user gesture") || msg.includes("user activation")
      || msg.includes("transient activation");
};
