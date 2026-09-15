// The trial offer on the join page.
//
// The failure that matters is the page promising something checkout will not grant. Stripe
// decides the trial, from billing.trial_days_for, and these tests pin this module to the
// same rule: one trial per customer, and none at all when the backend has it switched off.

import { trialOffer, offerStillStands } from "./trialOffer.js";

describe("who gets offered a trial", () => {
  test("a new visitor, signed out", () => {
    // Not knowable whether they have subscribed before, and almost all of them have not.
    // The copy corrects itself on sign-in, which happens before checkout.
    expect(trialOffer({ trialDays: 10, user: null, stripeReady: true })).toMatchObject({
      eligible: true, days: 10, headline: "10 days free", cta: "Start 10 days free",
    });
  });

  test("a signed-in account that has never been billed", () => {
    expect(trialOffer({ trialDays: 10, user: { had_subscription: false }, stripeReady: true }).eligible).toBe(true);
  });

  test("but not one that has subscribed before", () => {
    // The same rule billing.trial_days_for applies. Without it the trial is an unlimited
    // free subscription with a ten-day chore attached.
    expect(trialOffer({ trialDays: 10, user: { had_subscription: true }, stripeReady: true }).eligible).toBe(false);
  });

  test("and someone who opened checkout and changed their mind still gets one", () => {
    // `has_billing` USED TO BE THE FIELD HERE, and it stopped meaning what this needs the
    // moment the Stripe customer started being created at checkout instead of at payment.
    // Reading it now would refuse a free week to everybody who reached the payment page
    // and thought better of it — which is a large share of the people who ever see it.
    expect(trialOffer({ trialDays: 10, stripeReady: true,
      user: { has_billing: true, had_subscription: false } }).eligible).toBe(true);
  });

  test("and not a current member", () => {
    // "Start your free trial" on a page someone is already paying for reads as a mistake
    // about who they are.
    expect(trialOffer({ trialDays: 10, user: { had_subscription: false }, member: true,
      stripeReady: true })
      .eligible).toBe(false);
  });

  test("nothing at all when the backend has the trial switched off", () => {
    // TRIAL_DAYS=0 on Render must silence the page in the same deploy that stops checkout
    // granting one — that is the whole reason the number comes from /api/config.
    expect(trialOffer({ trialDays: 0, user: null, stripeReady: true }).eligible).toBe(false);
    expect(trialOffer({ user: null, stripeReady: true }).eligible).toBe(false);
    expect(trialOffer({}).eligible).toBe(false);
  });

  test("a rubbish value is no offer rather than a broken one", () => {
    expect(trialOffer({ trialDays: "ten", user: null, stripeReady: true }).eligible).toBe(false);
    expect(trialOffer({ trialDays: null, user: null, stripeReady: true }).eligible).toBe(false);
  });

  test("the length follows the backend rather than being fixed here", () => {
    expect(trialOffer({ trialDays: 7, user: null, stripeReady: true }).headline).toBe("7 days free");
    expect(trialOffer({ trialDays: 14, user: null, stripeReady: true }).cta).toBe("Start 14 days free");
  });
});

describe("what it says", () => {
  test("the card and the charge are stated on the page, not left to Stripe", () => {
    // A trial page that mentions the card only inside checkout collects chargebacks and a
    // reputation. The person who felt tricked is the one who tells everybody.
    const note = trialOffer({ trialDays: 10, user: null, stripeReady: true }).note;
    expect(note).toContain("Card needed");
    expect(note).toContain("cancel");
    expect(note).toContain("10 days");
  });

});

describe("an offer that expires between the click and the checkout", () => {
  const eligible = { eligible: true, days: 7 };
  const not = { eligible: false, days: 0 };

  test("a trial click by somebody who turns out to have had one is held", () => {
    // The whole point. They pressed "start 7 days free" and would otherwise land on a
    // page asking for £20 today — a bait and switch to a person who has paid before.
    expect(offerStillStands({ clickedTrial: true, offer: not })).toBe(false);
  });

  test("a trial click by somebody genuinely new carries straight through", () => {
    // The auto-continue exists because the pause after signing in is where people leave.
    expect(offerStillStands({ clickedTrial: true, offer: eligible })).toBe(true);
  });

  test("somebody who never clicked a trial is never held", () => {
    // They pressed a plain Subscribe. Nothing about their terms has changed, so stopping
    // them would be friction invented for its own sake.
    expect(offerStillStands({ clickedTrial: false, offer: not })).toBe(true);
    expect(offerStillStands({ clickedTrial: false, offer: eligible })).toBe(true);
  });

  test("a missing offer is treated as the trial being gone", () => {
    // Fails towards telling them rather than towards a surprise charge.
    expect(offerStillStands({ clickedTrial: true, offer: null })).toBe(false);
    expect(offerStillStands({ clickedTrial: true })).toBe(false);
  });

  test("nothing clicked at all stands, so a bare call cannot block the page", () => {
    expect(offerStillStands({})).toBe(true);
    expect(offerStillStands()).toBe(true);
  });
});

describe("a trial nothing can actually grant", () => {
  test("no offer at all when Stripe checkout is not configured", () => {
    // FOUND LIVE. With no Stripe keys the join page falls back to a bare Payment Link,
    // which is configured in the Stripe dashboard, carries no trial, and cannot be tied
    // to an account. The page still had trial_days from the backend, so it advertised
    // seven free days above a button that went straight to a payment form.
    expect(trialOffer({ trialDays: 7, user: null, stripeReady: false }).eligible).toBe(false);
  });

  test("and the default is no offer, so forgetting to pass it under-promises", () => {
    // Not offering a trial that was available costs a conversion and is visible. Offering
    // one that is not costs trust and is not.
    expect(trialOffer({ trialDays: 7, user: null }).eligible).toBe(false);
  });

  test("with checkout configured it behaves as before", () => {
    expect(trialOffer({ trialDays: 7, user: null, stripeReady: true }).eligible).toBe(true);
  });
});
