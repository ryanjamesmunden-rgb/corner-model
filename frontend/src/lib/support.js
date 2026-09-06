// How someone reaches a human — refunds above all.
//
// The guarantee on /join and in the FAQ says a losing month is "refunded on request".
// Until now there was nowhere on the site to make that request: no address, no handle,
// no form. A promise with no route to claim it reads as a promise that isn't meant to
// be claimed, and the person who believes that doesn't email — they ask their bank,
// which costs the fee, a chargeback fee on top, and the dispute rate that decides
// whether Stripe keeps the account open.
//
// The addresses are RUNTIME CONFIG, never hardcoded. Publishing a personal inbox in the
// bundle is a decision for whoever runs the site to make deliberately, by setting
// SUPPORT_EMAIL / SUPPORT_TELEGRAM, not something this file assumes on their behalf.
// With neither set, `supportRoutes` returns nothing and the UI says the channel is the
// way through — an honest dead end beats a mailto that bounces.

const SUBJECTS = {
  refund: "Refund request",
  billing: "Billing question",
  access: "Can't get into my account",
  help: "Question about the site",
};

// Prefilled bodies, because the request that arrives complete is the one answered the
// same day. The month matters for a refund (the guarantee is measured per month) and
// the account email matters for all of them — a message from a Gmail alias that doesn't
// match any subscriber is a round trip before anything can happen.
const previousMonth = (now = new Date()) => {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
};

const BODIES = {
  refund: (who) =>
    `Hi,\n\nI'd like to claim the money-back guarantee for ${previousMonth()}.\n\n`
    + `Account: ${who}\n\nThanks`,
  billing: (who) => `Hi,\n\n\n\nAccount: ${who}`,
  access: (who) =>
    `Hi,\n\nI'm having trouble getting into my account.\n\nAccount: ${who}\n\nThanks`,
  help: (who) => `Hi,\n\n\n\nAccount: ${who}`,
};

export const supportSubject = (topic) => SUBJECTS[topic] || SUBJECTS.help;

/**
 * Contact routes for one topic, best first.
 *
 * @param config  the /api/config payload — support_email and support_telegram
 * @param topic   refund | billing | access | help
 * @param user    the signed-in user, so the message can identify the account
 * @returns {Array<{kind, href, label, hint}>} — empty when nothing is configured
 */
export const supportRoutes = (config = {}, topic = "help", user = null) => {
  const email = (config.support_email || "").trim();
  const handle = (config.support_telegram || "").trim().replace(/^@/, "");
  const who = user?.email || "(not signed in)";
  const out = [];

  if (email) {
    const subject = encodeURIComponent(`${supportSubject(topic)} — The Corner Model`);
    const body = encodeURIComponent((BODIES[topic] || BODIES.help)(who));
    out.push({
      kind: "email",
      href: `mailto:${email}?subject=${subject}&body=${body}`,
      label: `Email ${email}`,
      // Email leads even though Telegram usually answers quicker, because everything
      // that reaches this card is about money: a refund claim wants a record with a
      // date on it, and the address it arrives from is what matches it to a subscriber.
      hint: "Best for anything to do with money — it leaves a record",
    });
  }
  if (handle) {
    out.push({
      kind: "telegram",
      href: `https://t.me/${handle}`,
      label: `Message @${handle} on Telegram`,
      hint: "Quicker for a quick question",
    });
  }
  return out;
};

export const hasSupport = (config) => supportRoutes(config).length > 0;

/**
 * The same routes as a sentence fragment, for prose that has to name them inline —
 * the FAQ's refund answer, mainly. Empty when nothing is configured, and every caller
 * must handle that: the fallback wording belongs to the sentence, not to this helper.
 */
export const supportPhrase = (config = {}) => {
  const email = (config.support_email || "").trim();
  const handle = (config.support_telegram || "").trim().replace(/^@/, "");
  const tg = handle ? `message @${handle} on Telegram` : "";
  const mail = email ? `email ${email}` : "";
  if (tg && mail) return `${tg} or ${mail}`;
  return tg || mail;
};
