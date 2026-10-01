/**
 * What the bets card may claim.
 *
 * This is the only card on the site that posts a profit figure, so most of what is pinned
 * here is about what it must NOT do: drop a loser on the re-draw, count a pending bet as a
 * flat result, show a team's corners against a match total, or print units for a bet whose
 * price nobody could get.
 */
import {
  cardFrom, cardPost, cardRow, betLabel, resultText, profitText,
  statusLabel, statusTone, MAX_CARD_ROWS,
} from "./betsCard.js";

const pick = (over = {}) => ({
  fixture_id: "f1", market_key: "home_over_5.5", subject: "team",
  home: "Arsenal", away: "Leeds", league_id: "eng-pl", league_name: "Premier League",
  kickoff: "2026-10-03T14:00:00Z", label: "Home Team Over 5.5",
  team: "Arsenal", line: 6, odds: 1.95, model_odds: 1.7, ev: 8.2,
  status: "pending", profit: null, ...over,
});

const won = (over = {}) => pick({
  status: "won", profit: 0.95, result_corners: 7, result_opp_corners: 4, ...over,
});

const lost = (over = {}) => pick({
  status: "lost", profit: -1, result_corners: 3, result_opp_corners: 6, ...over,
});

describe("a row says what the bet was and how it landed", () => {
  test("the bet names the team, not the side it happens to be playing on", () => {
    // The stored label is "Home Team Over 5.5", which is right on a fixture page and
    // useless on a card: the row already carries two club names and asks the reader to
    // work out which of them "Home Team" meant.
    expect(betLabel(pick())).toBe("Arsenal 6+ corners");
  });

  test("and the subject decides what the number means", () => {
    // A team line and a match total are roughly a factor of two apart.
    expect(betLabel(pick({ subject: "match", line: 9.5 })))
      .toBe("Over 9.5 match corners");
  });

  test("the stored label is the fallback when there is no line to build from", () => {
    expect(betLabel({ label: "Home Team Over 5.5" })).toBe("Home Team Over 5.5");
    expect(betLabel({})).toBe("");
  });

  test("a team bet shows the two sides' corners", () => {
    expect(resultText(won())).toBe("7-4 corners");
  });

  test("a match total shows the TOTAL, not one side of it", () => {
    // The bug this exists to stop: "WON 7" printed against a line of 9.5.
    expect(resultText(won({ subject: "match", result_total_corners: 11 })))
      .toBe("11 corners");
  });

  test("and an unsettled bet has no result to show", () => {
    expect(resultText(pick())).toBe("");
  });

  test("units read as units, with their sign", () => {
    expect(profitText(0.95)).toBe("+0.95u");
    expect(profitText(-1)).toBe("-1u");
    expect(profitText(0)).toBe("0u");
    expect(profitText(null)).toBe("");
  });

  test("a void is its own outcome, not a loss", () => {
    expect(statusLabel("void")).toBe("VOID");
    expect(statusTone("void")).toBe("void");
    expect(statusTone("lost")).toBe("loss");
  });

  test("an Asian half-win says so rather than rounding itself up to a win", () => {
    expect(statusLabel("half_won")).toBe("HALF WON");
    expect(statusTone("half_won")).toBe("win");
  });

  test("the row carries the price the bet was published at", () => {
    expect(cardRow(won()).price).toBe(1.95);
    expect(cardRow(won()).profitText).toBe("+0.95u");
  });
});

describe("the card", () => {
  test("nothing priced means no card at all", () => {
    // A card headed TODAY'S BETS with no rows reads as a broken job, not a quiet day.
    expect(cardFrom({ rows: [] })).toBeNull();
    expect(cardFrom({ rows: [pick({ odds: null })] })).toBeNull();
  });

  test("the biggest edge leads", () => {
    const card = cardFrom({ rows: [pick({ ev: 2 }), pick({ fixture_id: "f2", ev: 11 })] });
    expect(card.rows.map((r) => r.key)).toEqual(["f2-home_over_5.5", "f1-home_over_5.5"]);
  });

  test("losers stay on the card", () => {
    // THE ONE THAT WOULD MAKE THE EVENING CARD A LIE. Re-drawing the day's bets after the
    // results are in must show the same bets, not the ones that came in.
    const card = cardFrom({ rows: [won(), lost({ fixture_id: "f2" })] });
    expect(card.n).toBe(2);
    expect(card.rows.some((r) => r.tone === "loss")).toBe(true);
  });

  test("units count settled bets only, and the pending ones are counted separately", () => {
    const card = cardFrom({
      rows: [won(), lost({ fixture_id: "f2" }), pick({ fixture_id: "f3" })],
    });
    expect(card.settled).toBe(2);
    expect(card.pending).toBe(1);
    // 0.95 - 1, and the open bet contributes nothing rather than zero.
    expect(card.units).toBe(-0.05);
    expect(card.won).toBe(1);
    expect(card.lost).toBe(1);
  });

  test("a void counts as settled but stays out of the won/lost tally", () => {
    const card = cardFrom({
      rows: [won(), pick({ fixture_id: "f2", status: "void", profit: 0 })],
    });
    expect(card.voided).toBe(1);
    expect(card.won).toBe(1);
    expect(card.lost).toBe(0);
    expect(card.units).toBe(0.95);
  });

  test("a day with nothing settled says so instead of claiming a flat result", () => {
    const card = cardFrom({ rows: [pick(), pick({ fixture_id: "f2" })] });
    expect(card.hasResult).toBe(false);
    expect(card.pending).toBe(2);
  });

  test("the card is capped, and says how many it is holding back", () => {
    const rows = Array.from({ length: 9 }, (_, i) => pick({ fixture_id: `f${i}`, ev: i }));
    const card = cardFrom({ rows });
    expect(card.n).toBe(MAX_CARD_ROWS);
    expect(card.hidden).toBe(3);
  });

  test("kick-off times are stated in one fixed zone", () => {
    // Drawn on a runner in UTC and read in London: the card states which clock it means.
    const card = cardFrom({ rows: [pick({ kickoff: "2026-10-03T14:00:00Z" })] });
    expect(card.rows[0].time).toBe("15:00");
    expect(card.zone).toBeTruthy();
  });
});

describe("the post that goes with the picture", () => {
  test("it carries every row, its price and its result", () => {
    const card = cardFrom({ rows: [won(), lost({ fixture_id: "f2" })] });
    const out = cardPost({ card, site: "thecornermodel.com" });
    expect(out).toContain("Arsenal v Leeds — Arsenal 6+ corners @ 1.95");
    expect(out).toContain("WON 7-4 corners +0.95u");
    expect(out).toContain("LOST 3-6 corners -1u");
    expect(out).toContain("1 won · 1 lost");
    expect(out).toContain("thecornermodel.com");
  });

  test("an all-pending day does not print a result line", () => {
    const out = cardPost({ card: cardFrom({ rows: [pick()] }) });
    expect(out).toContain("1 bet · all pending");
    expect(out).not.toContain("won ·");
  });

  test("no card, no post", () => {
    expect(cardPost({ card: null })).toBe("");
  });
});
