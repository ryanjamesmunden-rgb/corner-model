import {
  cupLabel, edgeTitle, evidenceKind, fixtureCaveatTag, isCrossLeague, isCup, leaguePair,
  transferNote,
} from "./cupRow";
import { countryCodeFor, flagFor, withFlag } from "./countryFlag";

// A cup row renders exactly like a domestic one. Everything here is about the difference
// the reader cannot see: two records earned against different opposition, and a yardstick
// that belongs to neither league in the fixture.

const CROSS = {
  fixture_id: "ucl-1", league_id: "ucl", league_name: "Champions League",
  is_cup: true, cross_league: true,
  home_league_name: "Premier League", away_league_name: "Bundesliga",
  transfer_note: "Form is from each side's own league — Premier League and Bundesliga — "
    + "so the two records were earned against different opposition. Cup weeks also bring "
    + "rotation, which no corner count can see.",
  lambda_total: 11.2, league_avg_total: 10.0,
};

const ALL_ENGLISH = {
  fixture_id: "ucl-2", league_id: "ucl", league_name: "Champions League",
  is_cup: true, cross_league: false,
  home_league_name: "Premier League", away_league_name: "Premier League",
  transfer_note: "", lambda_total: 11.2, league_avg_total: 13.0,
};

const DOMESTIC = {
  fixture_id: "eng-pl-1", league_id: "eng-pl", league_name: "Premier League",
  is_cup: false, cross_league: false, transfer_note: "",
  lambda_total: 11.2, league_avg_total: 13.0,
};

describe("what kind of row this is", () => {
  test("a cup tie is a cup tie", () => {
    expect(isCup(CROSS)).toBe(true);
    expect(isCup(ALL_ENGLISH)).toBe(true);
    expect(isCup(DOMESTIC)).toBe(false);
  });

  test("an all-English tie in Europe is a cup but NOT cross-league", () => {
    // The distinction the whole warning hangs on. Both records are Premier League
    // records, directly comparable; warning about them would be a warning about nothing,
    // which is how a reader learns to scroll past the real ones.
    expect(isCup(ALL_ENGLISH)).toBe(true);
    expect(isCrossLeague(ALL_ENGLISH)).toBe(false);
  });

  test("nothing at all does not throw", () => {
    expect(isCup(null)).toBe(false);
    expect(isCrossLeague(undefined)).toBe(false);
    expect(cupLabel(null)).toBe("");
  });

  test("the label names the competition and is empty on a league game", () => {
    expect(cupLabel(CROSS)).toBe("Champions League");
    expect(cupLabel(DOMESTIC)).toBe("");
  });
});

describe("the transfer caveat", () => {
  test("it appears only on a cross-league tie", () => {
    expect(transferNote(CROSS)).toBeTruthy();
    expect(transferNote(ALL_ENGLISH)).toBe("");
    expect(transferNote(DOMESTIC)).toBe("");
  });

  test("it names both leagues", () => {
    expect(transferNote(CROSS)).toContain("Premier League");
    expect(transferNote(CROSS)).toContain("Bundesliga");
  });

  test("it mentions rotation, which nothing in the model can see", () => {
    expect(transferNote(CROSS).toLowerCase()).toContain("rotation");
  });

  test("it prefers the backend's own sentence over rebuilding one", () => {
    // Two copies of this warning would eventually drift, and then the page and a posted
    // pick would disagree about what the row means.
    expect(transferNote(CROSS)).toBe(CROSS.transfer_note);
  });

  test("an older payload with no note still gets a usable sentence", () => {
    const old = { ...CROSS, transfer_note: undefined };
    const note = transferNote(old);
    expect(note).toContain("Premier League");
    expect(note).toContain("Bundesliga");
  });

  test("and one with no league names falls back rather than printing undefined", () => {
    const bare = { is_cup: true, cross_league: true };
    const note = transferNote(bare);
    expect(note).toBeTruthy();
    expect(note).not.toContain("undefined");
  });
});

describe("the league pair tag", () => {
  test("it reads as the two competitions behind the evidence", () => {
    expect(leaguePair(CROSS)).toBe("Premier League v Bundesliga");
  });

  test("it is empty where it would say nothing", () => {
    expect(leaguePair(ALL_ENGLISH)).toBe("");
    expect(leaguePair(DOMESTIC)).toBe("");
    expect(leaguePair({ is_cup: true, cross_league: true })).toBe("");
  });
});

describe("the edge tooltip", () => {
  test("a domestic row says what its league averages", () => {
    expect(edgeTitle(DOMESTIC)).toContain("this league averages 13");
  });

  test("a cross-league tie does NOT claim a league average", () => {
    // The tie belongs to neither league, so "this league averages 10" would be naming a
    // league that is not in the fixture — a sentence that reads perfectly and is false.
    const t = edgeTitle(CROSS);
    expect(t).not.toContain("this league averages");
    expect(t).toContain("midpoint");
  });

  test("both carry the projection itself", () => {
    expect(edgeTitle(CROSS)).toContain("11.2");
    expect(edgeTitle(DOMESTIC)).toContain("11.2");
  });
});

describe("how the evidence is described", () => {
  test("it is a word, never a number", () => {
    // A discount factor would need a measurement this app has never made — how much a
    // corners-won rate survives a change of opposition. A word cannot be multiplied by.
    expect(evidenceKind(CROSS)).toBe("cross-league");
    expect(evidenceKind(DOMESTIC)).toBe("domestic");
    expect(typeof evidenceKind(CROSS)).toBe("string");
  });
});

describe("the card's own marker", () => {
  // The card is a run plus the defence it is about to meet, and the corroboration comes
  // from how leaky that defence has been. In a European tie that was measured in a
  // different league — weaker evidence than the identical-looking row above it, on the
  // one screen people are paying for.
  test("a cross-league next fixture is marked", () => {
    expect(fixtureCaveatTag({ cross_league: true })).toBeTruthy();
  });

  test("a domestic one is not", () => {
    expect(fixtureCaveatTag({ cross_league: false })).toBe("");
    expect(fixtureCaveatTag({})).toBe("");
    expect(fixtureCaveatTag(null)).toBe("");
  });

  test("a row from before the flag existed is treated as domestic, not unknown", () => {
    // Every fixture in the database was domestic until cups arrived, so the absent field
    // has exactly one correct reading — and a tag saying "unknown" on thousands of league
    // games would be noise that buries the real ones.
    expect(fixtureCaveatTag({ opponent: "Stoke", is_home: true })).toBe("");
  });
});

describe("a cup has a badge even though it has no country", () => {
  test("the id is matched whole, not sliced to a country prefix", () => {
    // Every league id carries a three-letter country prefix and the flag lookup slices
    // it. "ucl" is three letters of COMPETITION — sliced, it matches no country, and the
    // row shares with a bare bullet while every line around it carries a flag.
    expect(flagFor("ucl")).toBeTruthy();
    expect(withFlag("ucl", "Champions League")).toContain("Champions League");
    expect(withFlag("ucl", "Champions League")).not.toBe("Champions League");
  });

  test("a country league is unaffected", () => {
    expect(flagFor("ger-bl")).toBe(flagFor("ger-bl2"));
    expect(flagFor("eng-pl")).toBeTruthy();
  });

  test("an unknown id still returns nothing rather than a wrong flag", () => {
    expect(flagFor("zzz-x")).toBe("");
    expect(withFlag("zzz-x", "Somewhere")).toBe("Somewhere");
  });

  test("there is no short country code for a cup, and none is invented", () => {
    // storyImage falls back to this where flag glyphs do not render. "UC" would read as
    // a country that does not exist; plain text is the honest answer.
    expect(countryCodeFor("ucl")).toBe("");
    expect(countryCodeFor("eng-pl")).toBe("ENG");
    expect(countryCodeFor("ger-bl")).toBe("DE");
  });
});
