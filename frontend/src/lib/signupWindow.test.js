// The join page's half of the signup window.
//
// backend/signup.py enforces it; this mirrors signup.blocks so the page can explain the
// closed door rather than let somebody discover it after signing in. The two disagreeing
// is a real bug in both directions: a visible button on a closed day sends a person to a
// 409 having already signed in, and a hidden one on an open day turns away custom the shop
// was ready for.

import { signupBlocked, closedNotice } from "./signupWindow.js";

const win = (o = {}) => ({
  enabled: true, open: false, scope: "all", day: 1, day_name: "Monday",
  next_open: "2026-09-21T00:00:00+01:00",
  message: "Signups open on Mondays, so the whole group starts the week together and the "
    + "week's results are the week you actually saw. Next window: Monday 21 September.",
  ...o,
});

describe("who is blocked", () => {
  test("nobody, when no window is configured", () => {
    expect(signupBlocked({ signup: win({ enabled: false }) })).toBe(false);
    expect(signupBlocked({ signup: null })).toBe(false);
    expect(signupBlocked({})).toBe(false);
  });

  test("nobody, on the open day", () => {
    expect(signupBlocked({ signup: win({ open: true }), trialEligible: true })).toBe(false);
    expect(signupBlocked({ signup: win({ open: true }), trialEligible: false })).toBe(false);
  });

  test("everybody, on a closed day when the scope is everything", () => {
    expect(signupBlocked({ signup: win(), trialEligible: true })).toBe(true);
    expect(signupBlocked({ signup: win(), trialEligible: false })).toBe(true);
  });

  test("only the trial, when the scope is the trial", () => {
    // Somebody paying full price on a Wednesday does not affect weekly tracking, and
    // turning them away is £20 a month refused for no measurement at all.
    const signup = win({ scope: "trial" });
    expect(signupBlocked({ signup, trialEligible: true })).toBe(true);
    expect(signupBlocked({ signup, trialEligible: false })).toBe(false);
  });

  test("an unknown scope gates the trial only, which is the safer way to be wrong", () => {
    // A typo costs a cohort, not a month's revenue.
    const signup = win({ scope: "nonsense" });
    expect(signupBlocked({ signup, trialEligible: false })).toBe(false);
    expect(signupBlocked({ signup, trialEligible: true })).toBe(true);
  });
});

describe("what the closed door says", () => {
  test("the day is the headline, because that is the thing to remember", () => {
    expect(closedNotice({ signup: win() }).headline).toBe("Signups open on Mondays");
  });

  test("the reason comes from the backend rather than being written twice", () => {
    // A visitor seeing one reason on the page and a different one in the 409 has been
    // told the site is guessing.
    const notice = closedNotice({ signup: win() });
    expect(notice.reason).toContain("starts the week together");
    expect(notice.reason).toContain("Monday 21 September");
  });

  test("it follows a renamed day rather than assuming Monday", () => {
    const notice = closedNotice({ signup: win({ day: 4, day_name: "Thursday" }) });
    expect(notice.headline).toBe("Signups open on Thursdays");
  });

  test("nothing at all when nothing is blocked", () => {
    expect(closedNotice({ signup: win({ open: true }) })).toBeNull();
    expect(closedNotice({ signup: win({ enabled: false }) })).toBeNull();
    expect(closedNotice({ signup: win({ scope: "trial" }), trialEligible: false })).toBeNull();
  });

  test("a window with no message still produces a usable notice", () => {
    // The backend always sends one, but a stale deploy might not, and an empty block with
    // no explanation is worse than the headline alone.
    const notice = closedNotice({ signup: win({ message: "" }) });
    expect(notice.headline).toBe("Signups open on Mondays");
    expect(notice.reason).toBe("");
  });
});
