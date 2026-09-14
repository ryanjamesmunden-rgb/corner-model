// The trial offer on the join page.
//
// The failure that matters is the page promising something checkout will not grant. Stripe
// decides the trial, from billing.trial_days_for, and these tests pin this module to the
// same rule: one trial per customer, and none at all when the backend has it switched off.

import { trialOffer } from "./trialOffer.js";

describe("who gets offered a trial", () => {
  test("a new visitor, signed out", () => {
    // Not knowable whether they have subscribed before, and almost all of them have not.
    // The copy corrects itself on sign-in, which happens before checkout.
    expect(trialOffer({ trialDays: 10, user: null })).toMatchObject({
      eligible: true, days: 10, headline: "10 days free", cta: "Start 10 days free",
    });
  });

  test("a signed-in account that has never been billed", () => {
    expect(trialOffer({ trialDays: 10, user: { has_billing: false } }).eligible).toBe(true);
  });

  test("but not one that has subscribed before", () => {
    // The same rule billing.trial_days_for applies. Without it the trial is an unlimited
    // free subscription with a ten-day chore attached.
    expect(trialOffer({ trialDays: 10, user: { has_billing: true } }).eligible).toBe(false);
  });

  test("and not a current member", () => {
    // "Start your free trial" on a page someone is already paying for reads as a mistake
    // about who they are.
    expect(trialOffer({ trialDays: 10, user: { has_billing: false }, member: true })
      .eligible).toBe(false);
  });

  test("nothing at all when the backend has the trial switched off", () => {
    // TRIAL_DAYS=0 on Render must silence the page in the same deploy that stops checkout
    // granting one — that is the whole reason the number comes from /api/config.
    expect(trialOffer({ trialDays: 0, user: null }).eligible).toBe(false);
    expect(trialOffer({ user: null }).eligible).toBe(false);
    expect(trialOffer({}).eligible).toBe(false);
  });

  test("a rubbish value is no offer rather than a broken one", () => {
    expect(trialOffer({ trialDays: "ten", user: null }).eligible).toBe(false);
    expect(trialOffer({ trialDays: null, user: null }).eligible).toBe(false);
  });

  test("the length follows the backend rather than being fixed here", () => {
    expect(trialOffer({ trialDays: 7, user: null }).headline).toBe("7 days free");
    expect(trialOffer({ trialDays: 14, user: null }).cta).toBe("Start 14 days free");
  });
});

describe("what it says", () => {
  test("the card and the charge are stated on the page, not left to Stripe", () => {
    // A trial page that mentions the card only inside checkout collects chargebacks and a
    // reputation. The person who felt tricked is the one who tells everybody.
    const note = trialOffer({ trialDays: 10, user: null }).note;
    expect(note).toContain("Card needed");
    expect(note).toContain("cancel");
    expect(note).toContain("10 days");
  });

});
