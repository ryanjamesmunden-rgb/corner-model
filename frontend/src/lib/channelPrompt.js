// Whether to nag a member about the channel they have paid for and not joined.
//
// THE FAILURE THIS EXISTS FOR. Paying and arriving are two events, and the site was
// treating them as one. Checkout returns to /account, the invite sits behind a button
// there, and a subscriber who closed the tab — or who read the page and did not press the
// thing — has bought the channel and never been handed it. One did exactly that, and
// nothing in the product knew.
//
// THE BOT CANNOT FIX THIS, and it is worth writing down why so nobody spends a week on it.
// To message somebody on Telegram you need their chat id. We learn a member's Telegram
// identity at exactly one moment: when they walk through an issued invite
// (record_channel_join). So the only people the bot can DM an invite to are the people who
// have already used one. The first link has to reach them somewhere they already are,
// which is the website.
//
// Kept out of the component so "should this show" is one tested decision rather than a
// chain of && in JSX, which is how a banner ends up shown to a non-member.

/**
 * Should this account be prompted to join the channel?
 *
 * MEMBERS ONLY, and `trialing` is a member — that is the point of the trial. A prompt to a
 * non-member is an advert dressed as a reminder, which is worse than no prompt: it teaches
 * people to dismiss the thing without reading it.
 */
export function shouldPrompt(user) {
  if (!user?.member) return false;
  return !user.vip_joined;
}

/**
 * How hard to push, given how long they have been a member without arriving.
 *
 * "quiet" is a line on the account page. "loud" is a banner that follows them, and it is
 * reserved for someone who has been paying for a while and still is not in — because at
 * that point the reminder is not noise, it is the only thing standing between them and the
 * thing they bought.
 *
 * ON A TRIAL IT IS LOUD IMMEDIATELY. A ten-day window spent not finding the channel is the
 * trial failing for a reason that has nothing to do with whether the picks are any good.
 */
export function promptLevel(user, now = Date.now()) {
  if (!shouldPrompt(user)) return null;
  if (user.subscription_status === "trialing") return "loud";
  const since = Date.parse(user.member_since || "");
  if (Number.isNaN(since)) return "loud";
  const hours = (now - since) / 3600000;
  return hours >= 1 ? "loud" : "quiet";
}

/** What the prompt says. One place, so the banner and the account page cannot drift. */
export function promptCopy(user) {
  const trial = user?.subscription_status === "trialing";
  return {
    title: user?.vip_invited
      ? "Your channel invite is waiting"
      : "You haven't joined the VIP channel yet",
    // NAMES WHAT THEY ARE MISSING, not what they should click. "Join the channel" is an
    // instruction; "the picks go out there" is a reason, and a reason is what gets
    // somebody to act on a banner they have already scrolled past once.
    body: trial
      ? "The picks go out on Telegram, and your trial is already running. Grab your invite — it takes a second and it's yours alone."
      : "The picks go out on Telegram. Your invite is one tap and it's yours alone.",
    cta: user?.vip_invited ? "Open my invite" : "Get my invite",
  };
}
