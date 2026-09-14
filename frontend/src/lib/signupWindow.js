// Whether this visitor can subscribe today, and what to say when they cannot.
//
// THE SERVER DECIDES; THIS ONLY EXPLAINS. backend/signup.py enforces the window at
// checkout, which is the only place it counts — a hidden button stops nobody who calls the
// endpoint. What this is for is the difference between a door that is locked and a door
// that says when it opens, and that difference is most of whether somebody comes back.
//
// IT MIRRORS signup.blocks AND HAS TO KEEP MIRRORING IT. The two disagreeing is not a
// cosmetic bug in either direction: showing the button on a closed day sends somebody to a
// 409 after they have signed in, and hiding it on an open day is a shop that turned away
// custom it was ready for. The rule is four lines, which is exactly why it is worth pinning
// with tests rather than trusting to memory.

/**
 * Is this particular person blocked right now?
 *
 * `signup` is /api/config's `signup` object. `trialEligible` is whether they would be
 * starting a free trial — under SIGNUP_SCOPE="trial" the window gates the cohort only, and
 * somebody paying full price is let through on any day.
 */
export const signupBlocked = ({ signup = null, trialEligible = false } = {}) => {
  if (!signup?.enabled || signup.open) return false;
  return signup.scope === "all" ? true : Boolean(trialEligible);
};

/**
 * The closed-door block: a headline, the reason, and when it opens.
 *
 * THE REASON IS NOT DECORATION. "Signups open Monday" alone reads as a website being
 * difficult; the same sentence with "so the whole group starts the week together" reads as
 * a service that knows what it is doing — and it is also true, which is the only reason it
 * is worth saying. Returns null when nothing is blocked, so the caller branches once.
 */
export const closedNotice = ({ signup = null, trialEligible = false } = {}) => {
  if (!signupBlocked({ signup, trialEligible })) return null;
  return {
    // The day, because that is the thing to remember; the full sentence is underneath.
    headline: signup.day_name ? `Signups open on ${signup.day_name}s` : "Signups are closed",
    // Straight from the backend, so the page cannot drift from what checkout says when it
    // refuses — a visitor who sees one reason here and a different one in an error has
    // been told the site is guessing.
    reason: signup.message || "",
  };
};
