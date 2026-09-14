import { isLocked, lockClass, lockCounts, lockedPitch } from "./locked";

const open = { name: "Viking", prob: 74 };
const shut = { name: "Brann", blurred: true };

test("a row is locked only when the server said so", () => {
  // The flag comes from _preview, which has already REMOVED the numbers. Deciding this
  // client-side from "are the numbers missing" would lock a row whose model simply had
  // nothing to say.
  expect(isLocked(open)).toBe(false);
  expect(isLocked(shut)).toBe(true);
  expect(isLocked(null)).toBe(false);
  expect(isLocked({})).toBe(false);
});

test("the class is additive, never replacing what the row already had", () => {
  expect(lockClass(shut, "px-3 py-2")).toBe("px-3 py-2 row-locked");
  expect(lockClass(open, "px-3 py-2")).toBe("px-3 py-2");
  expect(lockClass(open)).toBe("");
});

test("counts split the board the way the pitch needs to describe it", () => {
  expect(lockCounts([open, open, shut, shut, shut]))
    .toEqual({ readable: 2, locked: 3, total: 5 });
  expect(lockCounts([])).toEqual({ readable: 0, locked: 0, total: 0 });
});

describe("what the strip underneath says", () => {
  test("signed out is asked for an account, not for money", () => {
    // "Members only" to someone with no account names the wrong next step: the thing
    // they have to do next is free, and saying "pay" loses the ones who would have.
    const p = lockedPitch({ locked: 12, signedIn: false, member: false });
    expect(p.body).toMatch(/free account/i);
    expect(p.head).toContain("12");
  });

  test("signed in is asked for the subscription", () => {
    const p = lockedPitch({ locked: 12, signedIn: true, member: false });
    expect(p.body).toMatch(/subscrib/i);
    expect(p.body).not.toMatch(/free account/i);
  });

  test("a member is never pitched, and neither is a full board", () => {
    expect(lockedPitch({ locked: 12, signedIn: true, member: true })).toBeNull();
    expect(lockedPitch({ locked: 0, signedIn: false, member: false })).toBeNull();
  });
});
