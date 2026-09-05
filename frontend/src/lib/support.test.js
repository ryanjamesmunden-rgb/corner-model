/**
 * The refund route is the one piece of copy a disputing customer quotes back at you, so
 * what is worth pinning here is the failure that costs money rather than the happy path:
 *
 *   - nothing configured must produce NO route at all, so the UI falls back to saying
 *     where to go instead of rendering a mailto that bounces;
 *   - an address must never be invented or half-built — a "mailto:?subject=..." with no
 *     recipient looks like a working link and goes nowhere;
 *   - a handle pasted as "@name" or as a full t.me URL is the same handle.
 */
import { supportRoutes, supportPhrase, hasSupport, supportSubject } from "./support";

const EMAIL = { support_email: "help@example.com" };
const TG = { support_telegram: "cornermodel" };

describe("with nothing configured", () => {
  test("offers no routes at all rather than a dead link", () => {
    expect(supportRoutes({}, "refund")).toEqual([]);
    expect(supportRoutes({ support_email: "  ", support_telegram: "" })).toEqual([]);
    expect(hasSupport({})).toBe(false);
  });

  test("has no phrase, so the sentence supplies its own fallback", () => {
    expect(supportPhrase({})).toBe("");
  });
});

describe("an email route", () => {
  const [route] = supportRoutes(EMAIL, "refund", { email: "buyer@example.com" });

  test("addresses the configured mailbox", () => {
    expect(route.href.startsWith("mailto:help@example.com?")).toBe(true);
  });

  test("carries the account so the request can be matched to a subscriber", () => {
    expect(decodeURIComponent(route.href)).toContain("buyer@example.com");
  });

  test("names the topic in the subject", () => {
    expect(decodeURIComponent(route.href)).toContain(supportSubject("refund"));
  });

  test("still works signed out, without claiming an account", () => {
    const [anon] = supportRoutes(EMAIL, "refund");
    expect(decodeURIComponent(anon.href)).toContain("(not signed in)");
  });
});

describe("a Telegram route", () => {
  test("reduces a handle to one form however it was pasted", () => {
    const bare = supportRoutes(TG)[0].href;
    expect(supportRoutes({ support_telegram: "@cornermodel" })[0].href).toBe(bare);
    expect(bare).toBe("https://t.me/cornermodel");
  });

  test("sits behind email, which is the one that leaves a record", () => {
    expect(supportRoutes({ ...EMAIL, ...TG }, "refund").map((r) => r.kind))
      .toEqual(["email", "telegram"]);
  });
});

describe("the inline phrase", () => {
  test("names both routes when both exist", () => {
    expect(supportPhrase({ ...EMAIL, ...TG }))
      .toBe("message @cornermodel on Telegram or email help@example.com");
  });

  test("names only what is configured", () => {
    expect(supportPhrase(EMAIL)).toBe("email help@example.com");
    expect(supportPhrase(TG)).toBe("message @cornermodel on Telegram");
  });
});
