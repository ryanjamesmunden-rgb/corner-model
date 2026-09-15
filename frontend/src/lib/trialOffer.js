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
export const trialOffer = ({ trialDays = 0, user = null, member = false,
                             stripeReady = false } = {}) => {
  const days = Number(trialDays) || 0;
  const none = { eligible: false, days: 0, headline: "", cta: "", note: "" };
  // A TRIAL IS SOMETHING ONLY THE REAL CHECKOUT CAN GRANT, and this caught it live. With
  // no Stripe keys configured the join page falls back to a bare Payment Link — which is
  // configured in the Stripe dashboard, carries no trial, and cannot be tied to an account
  // at all. The page still had trial_days from the backend, so it advertised seven free
  // days above a button that went straight to a payment form. Somebody pressed it.
  //
  // DEFAULTS TO FALSE, deliberately, so a caller that forgets to pass it under-promises
  // rather than over-promises. Not offering a trial that was available costs a conversion
  // and is visible; offering one that is not costs trust and is not.
  if (!stripeReady) return none;
  // Nothing to offer a member: they are already in, and "start your free trial" on a page
  // someone is paying to see reads as a mistake about who they are.
  if (days < 1 || member) return none;
  // The same rule as billing.trial_days_for. Without it the trial is an unlimited free
  // subscription with a weekly chore attached — subscribe, cancel on day six, repeat.
  //
  // `had_subscription`, NOT `has_billing`, and the difference now matters. The Stripe
  // customer is created when somebody OPENS checkout, so has_billing became true for
  // anyone who reached the payment page and changed their mind — and reading it here
  // would refuse them a free week they had never used. This field is written only when a
  // subscription has actually existed.
  if (user?.had_subscription) return none;
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

/**
 * Does the offer they clicked still apply, now that signing in has revealed who they are?
 *
 * THE GAP THIS NAMES. A signed-out visitor is shown the trial because nothing on the page
 * can tell whether they have had one, and refusing a genuinely new visitor on a guess is
 * the more expensive mistake. Signing in is the first moment the answer exists — and for a
 * returning ex-subscriber it is no.
 *
 * The join page carries a click through the sign-in and on to checkout, which is right for
 * somebody whose terms have not changed and wrong for somebody whose have: they pressed
 * "start 7 days free" and would land on a page asking for £20 today. That is a bait and
 * switch to a person who has paid you before, and it is why this is a named rule with a
 * test rather than a condition inside an effect.
 */
export const offerStillStands = ({ clickedTrial = false, offer = null } = {}) =>
  !clickedTrial || Boolean(offer?.eligible);
