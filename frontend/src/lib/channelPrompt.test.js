import { promptCopy, promptLevel, shouldPrompt } from "./channelPrompt";

// A subscriber paid, closed the tab after Stripe, and never came back to /account — where
// the invite lived behind a button. He had bought the channel and been handed nothing, and
// the product had no idea. This is the rule that decides who gets told.

const HOUR = 3600000;
const NOW = Date.parse("2026-09-16T12:00:00Z");

const member = (over = {}) => ({
  member: true, vip_joined: false, subscription_status: "active",
  member_since: new Date(NOW - 5 * HOUR).toISOString(), ...over,
});

describe("who gets prompted", () => {
  test("a member who has not arrived in the channel does", () => {
    expect(shouldPrompt(member())).toBe(true);
  });

  test("a member who is already in does not", () => {
    // Nobody needs a live invite minted at them on every page of a channel they are in.
    expect(shouldPrompt(member({ vip_joined: true }))).toBe(false);
  });

  test("a non-member never does", () => {
    // A prompt to someone who has not paid is an advert dressed as a reminder, which is
    // worse than no prompt — it teaches people to dismiss the banner without reading it.
    expect(shouldPrompt({ member: false, vip_joined: false })).toBe(false);
  });

  test("a signed-out visitor is not a crash", () => {
    expect(shouldPrompt(null)).toBe(false);
    expect(shouldPrompt(undefined)).toBe(false);
  });
});

describe("how hard to push", () => {
  test("a trial is loud immediately", () => {
    // A ten-day window spent not finding the channel is the trial failing for a reason
    // that has nothing to do with whether the picks are any good.
    const u = member({ subscription_status: "trialing",
                       member_since: new Date(NOW - 60000).toISOString() });
    expect(promptLevel(u, NOW)).toBe("loud");
  });

  test("a brand new subscriber is quiet for the first hour", () => {
    // They are probably mid-flow on the account page already; shouting at them there is
    // the same message twice.
    const u = member({ member_since: new Date(NOW - 10 * 60000).toISOString() });
    expect(promptLevel(u, NOW)).toBe("quiet");
  });

  test("and loud after it", () => {
    expect(promptLevel(member(), NOW)).toBe("loud");
  });

  test("an unreadable join date errs towards telling them", () => {
    // Silence is the failure being fixed. If we cannot tell how long they have been
    // waiting, assume too long.
    expect(promptLevel(member({ member_since: "nonsense" }), NOW)).toBe("loud");
  });

  test("nobody to prompt is no level at all", () => {
    expect(promptLevel(member({ vip_joined: true }), NOW)).toBeNull();
  });
});

describe("what it says", () => {
  test("it names what they are missing rather than what to click", () => {
    // "Join the channel" is an instruction; "the picks go out there" is a reason, and a
    // reason is what gets somebody to act on a banner they already scrolled past once.
    expect(promptCopy(member()).body).toMatch(/picks go out on Telegram/);
  });

  test("a trialist is told the clock is running", () => {
    const copy = promptCopy(member({ subscription_status: "trialing" }));
    expect(copy.body).toMatch(/trial is already running/);
  });

  test("an invite already minted reads as waiting, not as new work", () => {
    expect(promptCopy(member({ vip_invited: true })).title).toMatch(/waiting/);
    expect(promptCopy(member({ vip_invited: false })).title).toMatch(/haven't joined/);
  });

  test("it always offers a call to action", () => {
    expect(promptCopy(member()).cta).toBeTruthy();
    expect(promptCopy(null).cta).toBeTruthy();
  });
});
