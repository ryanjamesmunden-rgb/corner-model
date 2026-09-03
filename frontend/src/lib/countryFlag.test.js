/**
 * The flags go out on Telegram and X, where a wrong one is a claim about the wrong
 * country's football and nobody can see the league name to catch it. What's worth
 * pinning is the two ways this can go wrong quietly:
 *
 *   - the home nations need subdivision flags, not GB, and not the letters "gbeng";
 *   - an unknown league must fall back to the bullet, never print an empty gap or a
 *     flag built out of whatever three characters the id happened to start with.
 */
import { flagFor, flagBullet, withFlag } from "./countryFlag";

// Written as codepoints so the expectations survive an editor that mangles emoji.
const NO = "\u{1F1F3}\u{1F1F4}";
const ENGLAND = "\u{1F3F4}\u{E0067}\u{E0062}\u{E0065}\u{E006E}\u{E0067}\u{E007F}";
const SCOTLAND = "\u{1F3F4}\u{E0067}\u{E0062}\u{E0073}\u{E0063}\u{E0074}\u{E007F}";

describe("the flag for a league", () => {
  test("comes from the id's country prefix, not the tier", () => {
    expect(flagFor("nor-el")).toBe(NO);
    expect(flagFor("nor-d1")).toBe(NO);
  });

  test("is a subdivision flag for the home nations", () => {
    expect(flagFor("eng-pl")).toBe(ENGLAND);
    expect(flagFor("sco-pl")).toBe(SCOTLAND);
    expect(flagFor("eng-pl")).not.toBe(flagFor("sco-pl"));
  });

  test("tells apart leagues that share a NAME across borders", () => {
    // "Bundesliga" is Germany and Austria; "Super League" is Switzerland and Greece.
    expect(flagFor("ger-bl")).not.toBe(flagFor("aut-bl"));
    expect(flagFor("sui-sl")).not.toBe(flagFor("gre-sl"));
  });

  test("is empty for a league we don't know", () => {
    expect(flagFor("zzz-xx")).toBe("");
    expect(flagFor(undefined)).toBe("");
    expect(flagFor("")).toBe("");
  });
});

describe("what a shared line opens with", () => {
  test("the flag replaces the bullet rather than joining it", () => {
    expect(flagBullet("nor-el")).toBe(NO);
    expect(flagBullet("nor-el")).not.toContain("•");
  });

  test("an unknown league still gets a bullet, not a blank", () => {
    expect(flagBullet("zzz-xx")).toBe("•");
  });

  test("withFlag leaves an unflagged name exactly as it was", () => {
    expect(withFlag("nor-el", "Bodø/Glimt")).toBe(`${NO} Bodø/Glimt`);
    expect(withFlag("zzz-xx", "Bodø/Glimt")).toBe("Bodø/Glimt");
  });
});
