/**
 * The rule behind the second tap.
 *
 * Recording a story video takes 5.3 seconds and a browser stops honouring a tap after
 * about five, so `navigator.share` was refused every time with "Must be handling a user
 * gesture to perform a share request" — a red error over a file that was perfectly fine.
 * These two decide when to ask for one more tap instead.
 */
import { hasLiveGesture, isGestureError } from "./userGesture";

describe("is the tap still live", () => {
  test("takes the browser's word for it when the browser has one", () => {
    expect(hasLiveGesture({ userActivation: { isActive: true } })).toBe(true);
    expect(hasLiveGesture({ userActivation: { isActive: false } })).toBe(false);
  });

  test("assumes yes where the browser cannot say", () => {
    // Safari has no userActivation. Assuming NO there would put a pointless second tap in
    // front of every share on that browser; assuming yes costs one caught exception in
    // the case where it was actually no, and isGestureError turns that into the same
    // recovery. Optimism is the cheaper mistake.
    expect(hasLiveGesture({})).toBe(true);
    expect(hasLiveGesture(null)).toBe(true);
    expect(hasLiveGesture({ userActivation: {} })).toBe(true);
  });
});

describe("was this failure just the expired gesture", () => {
  test("catches what Chrome actually throws", () => {
    const err = new Error("Failed to execute 'share' on 'Navigator': Must be handling a "
      + "user gesture to perform a share request.");
    err.name = "NotAllowedError";
    expect(isGestureError(err)).toBe(true);
  });

  test("catches it on the wording alone, without the name", () => {
    // The name is not guaranteed across browsers and the message is the only place the
    // cause is stated, so both are checked — missing this shows a red error for
    // something one more tap would fix, which is the bug this file exists for.
    expect(isGestureError({ message: "must be handling a user gesture" })).toBe(true);
    expect(isGestureError({ message: "requires transient activation" })).toBe(true);
    expect(isGestureError({ name: "NotAllowedError" })).toBe(true);
  });

  test("does NOT swallow a real failure", () => {
    // Offering "tap again to share" for a recording that produced nothing would promise
    // a share with nothing behind it, and hide the actual fault.
    expect(isGestureError(new Error("recording produced nothing"))).toBe(false);
    expect(isGestureError({ name: "AbortError" })).toBe(false);
    expect(isGestureError(null)).toBe(false);
    expect(isGestureError(undefined)).toBe(false);
  });
});
