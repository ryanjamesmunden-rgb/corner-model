/**
 * Routing a block of bookmaker text to the right game and the right market.
 *
 * The failure this guards against is not a crash. It is a price silently landing on the
 * WRONG fixture — which produces a board that looks priced, shows an edge, and is about a
 * different game. Everything here is about lines refusing to be placed rather than being
 * placed on a guess.
 */
import { parsePriceLine, matchFixture, parseBulk, nameHit, STANDARD_KEYS } from "./pastePrices";

const FIXTURES = [
  { fixture_id: "f1", home_name: "Club Brugge KV", away_name: "Antwerp" },
  { fixture_id: "f2", home_name: "Juventus", away_name: "Sassuolo" },
  { fixture_id: "f3", home_name: "Bodø/Glimt", away_name: "Rosenborg" },
];

describe("reading one line", () => {
  const at = (raw, extra) => parsePriceLine(raw,
    { homeName: "Club Brugge KV", awayName: "Antwerp", ...extra });

  test("'5+' and 'Over 4.5' land on the same market, not two", () => {
    expect(at("Club Brugge 5+ 1.40").key).toBe("home_over_4.5");
    expect(at("Club Brugge Over 4.5 1.40").key).toBe("home_over_4.5");
  });

  test("routes by team name, then by the word total, then by the fallback", () => {
    expect(at("Antwerp 4+ 2.10").group).toBe("away");
    expect(at("Total 10.5 1.90").group).toBe("total");
    expect(at("Over 4.5 1.80", { target: "total" }).group).toBe("total");
  });

  test("takes the LAST number as the price, whatever is in between", () => {
    // Bookmaker rows carry volume, movement, all sorts. The line leads and the price ends.
    expect(at("Club Brugge Over 5.5 (1,204 bets) 2.05").price).toBe(2.05);
  });

  test("refuses anything that is not a price", () => {
    // 1.0 is how a blank cell scrapes, and below evens is not a bet — both would be
    // stored as a real number to bet into.
    expect(at("Club Brugge 5+ 1.00")).toBeNull();
    expect(at("Club Brugge 5+ 0.90")).toBeNull();
    expect(at("Club Brugge corners")).toBeNull();
    expect(at("")).toBeNull();
  });
});

describe("finding which game a line belongs to", () => {
  test("both sides named is a heading", () => {
    expect(matchFixture("Club Brugge KV v Antwerp", FIXTURES).fixture_id).toBe("f1");
    expect(matchFixture("Juventus vs Sassuolo — Sun 18:45", FIXTURES).fixture_id).toBe("f2");
  });

  test("one side named is a heading only when it carries no price", () => {
    // "Juventus" alone is a heading. "Juventus 6+ 2.10" is a price line for whichever
    // game is already open, and treating it as a heading would silently switch fixtures
    // mid-block.
    expect(matchFixture("Juventus", FIXTURES).fixture_id).toBe("f2");
    expect(matchFixture("Juventus 6+ 2.10", FIXTURES)).toBeNull();
  });

  test("survives the shortening bookmakers do to names", () => {
    expect(nameHit("bodo glimt v rosenborg", "Bodø/Glimt")).toBe(true);
    expect(matchFixture("Bodo Glimt v Rosenborg", FIXTURES).fixture_id).toBe("f3");
  });

  test("a two-letter prefix does not match half the league", () => {
    expect(nameHit("fc porto 5+ 1.9", "FC Basel")).toBe(false);
  });
});

describe("a whole paste", () => {
  const keys = () => ["home_over_4.5", "home_over_5.5", "away_over_3.5", "total_over_9.5"];

  test("a heading switches the game the prices go to", () => {
    const { entries } = parseBulk(`
      Club Brugge KV v Antwerp
      5+ 1.40
      Antwerp 4+ 2.10
      Juventus v Sassuolo
      Total 10 1.85
    `, FIXTURES, () => null);
    expect(entries).toHaveLength(2);
    const [a, b] = entries;
    expect(a.fixture.fixture_id).toBe("f1");
    // "5+" on its own names no team, so it falls back to the match total rather than
    // being attributed to whichever side happens to be listed first.
    expect(a.odds["home_over_4.5"]).toBeUndefined();
    expect(a.odds["total_over_4.5"]).toBe(1.4);
    expect(a.odds["away_over_3.5"]).toBe(2.1);
    expect(b.fixture.fixture_id).toBe("f2");
    expect(b.odds["total_over_9.5"]).toBe(1.85);
  });

  test("prices before any heading are unmatched, never guessed", () => {
    // The first thing in a paste is as likely to be a column header as a price, and
    // attaching it to a fixture nobody named is how a board ends up priced wrong.
    const { entries, unmatched } = parseBulk("Over 4.5 1.80\nOver 5.5 2.20", FIXTURES);
    expect(entries).toHaveLength(0);
    expect(unmatched).toHaveLength(2);
  });

  test("a market the fixture does not have is unmatched, not stored", () => {
    const { entries, unmatched } = parseBulk(`
      Club Brugge KV v Antwerp
      Club Brugge 5+ 1.40
      Club Brugge 30+ 51.00
    `, FIXTURES, keys);
    expect(entries[0].odds).toEqual({ "home_over_4.5": 1.4 });
    expect(unmatched.some((u) => u.includes("30+"))).toBe(true);
  });

  test("a heading that also carries a price keeps both", () => {
    const { entries } = parseBulk("Club Brugge KV v Antwerp 10 1.90", FIXTURES, keys);
    expect(entries).toHaveLength(1);
    expect(entries[0].odds["total_over_9.5"]).toBe(1.9);
  });

  test("counts what it placed, so the UI can report it honestly", () => {
    const { entries } = parseBulk(`
      Club Brugge KV v Antwerp
      Club Brugge 5+ 1.40
      Club Brugge 6+ 1.95
    `, FIXTURES, keys);
    expect(entries[0].count).toBe(2);
  });

  test("nothing in, nothing out", () => {
    expect(parseBulk("", FIXTURES)).toEqual({ entries: [], unmatched: [] });
    expect(parseBulk(null, FIXTURES).entries).toHaveLength(0);
  });
});

test("a market the model does not price is refused by DEFAULT, not on request", () => {
  // Found by rendering the page and pasting a realistic block: "Shots on target 4.5 2.20"
  // was stored as a corners total of 4.5, a market that does not exist, on a board that
  // would then have shown an edge on it. The guard has to be free, not opt-in.
  const { entries, unmatched } = parseBulk(`
    Club Brugge KV v Antwerp
    Club Brugge 5+ 1.40
    Shots on target 4.5 2.20
  `, FIXTURES);
  expect(entries[0].odds).toEqual({ "home_over_4.5": 1.4 });
  expect(unmatched.some((u) => u.includes("Shots"))).toBe(true);
});

test("the standard ladders are the ones the model actually prices", () => {
  expect(STANDARD_KEYS).toContain("total_over_9.5");
  expect(STANDARD_KEYS).toContain("home_over_4.5");
  expect(STANDARD_KEYS).toContain("away_over_6.5");
  expect(STANDARD_KEYS).not.toContain("total_over_4.5");   // below the real total ladder
  expect(STANDARD_KEYS).not.toContain("home_over_9.5");    // above the real team ladder
});
