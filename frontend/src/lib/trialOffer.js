// What the join page is allowed to promise about the free trial.
//
// THE PAGE AND THE CHECKOUT HAVE TO AGREE. The trial is granted by Stripe, from
// billing.trial_days_for, and the one failure worth designing against is a page advertising
// ten free days in front of a checkout that grants none. So the length comes from the
// backend's own TRIAL_DAYS rather than a constant in this bundle, and the eligibility rule
// here is the same rule billing.py applies: one trial per customer, keyed on whether a
// Stripe customer has ever existed for the account.
//
// THE SIGNED-OUT CASE IS A GENUINE UNKNOWN, and it is handled by being honest about what is
// known rather than by guessing. A visitor who is not signed in might be a returning
// customer who has already had a trial — nothing on the page can tell. Almost all of them
// are not, so the offer is shown; and because the copy is derived from `user`, it corrects
// itself the moment they sign in, which is before they ever reach payment. The promise is
// therefore never carried into a checkout that would break it.

/**
 * The offer for this visitor.
 *
 * `trialDays` is /api/config's `trial_days`. `user` is the signed-in account or null.
 * Returns `eligible: false` and empty copy whenever there is nothing to offer, so the
 * caller can render the block or not on one flag rather than assembling the rule again.
 */
export const trialOffer = ({ trialDays = 0, user = null, member = false } = {}) => {
  const days = Number(trialDays) || 0;
  const none = { eligible: false, days: 0, headline: "", cta: "", note: "" };
  // Nothing to offer a member: they are already in, and "start your free trial" on a page
  // someone is paying to see reads as a mistake about who they are.
  if (days < 1 || member) return none;
  // The same rule as billing.trial_days_for. Without it the trial is an unlimited free
  // subscription with a weekly chore attached — subscribe, cancel on day six, repeat.
  if (user?.has_billing) return none;
  return {
    eligible: true,
    days,
    headline: `${days} days free`,
    cta: `Start ${days} days free`,
    // WHAT HAPPENS ON DAY ELEVEN, SAID PLAINLY. A trial page that mentions the card only
    // in Stripe's checkout is how a service collects chargebacks and a reputation: the
    // person who felt tricked is the one who tells everybody. Saying it here costs a few
    // sign-ups and buys every one of them being a person who meant it.
    note: `Card needed to start. Nothing is charged for ${days} days — cancel before then `
      + "and you pay nothing at all.",
  };
};
