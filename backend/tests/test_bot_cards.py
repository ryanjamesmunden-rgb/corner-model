"""What the bot is allowed to say about the record.

WHAT THESE GUARD. A card is a claim made to paying subscribers, and the two ways to
overstate one are both easy and both invisible once posted:

  - a hit rate with no settled games behind it, which renders as "0%" and reads as a
    board that missed everything rather than a board nobody has graded yet;
  - a units total computed over the priced subset of a board and printed as though it
    covered all of it.

Both are already ruled out server-side — _tally answers `hit_rate: None` and
`units: None` rather than 0, and carries `priced`/`unpriced` beside the total — and both
would be reintroduced here by a formatter that reaches for `or 0`.

The residual tests are the other half: the gap against the board's own stated price is
the result, so a card that drops it says nothing about whether the board was right.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from bot_cards import (MAX_ROWS, TELEGRAM_LIMIT, board_card,  # noqa: E402
                       board_line, digest_card, perfect_card, plus_line,
                       results_card, settled_card, stale_warning, units_text,
                       value_card, value_rows, week_card)


def board(**kw):
    """A /results/boards row, with the fields _tally really puts on it."""
    b = {"key": "streaks", "label": "Streaks", "claims": 40, "landed": 24, "missed": 11,
         "settled": 35, "voided": 0, "pending": 5, "hit_rate": 68.6, "units": 3.21,
         "priced": 35, "unpriced": 0, "mean_prob": 64.0, "residual": 4.6}
    b.update(kw)
    return b


class TestARateNeedsSettledGames:
    def test_nothing_settled_says_so_rather_than_zero_percent(self):
        line = board_line(board(settled=0, landed=0, missed=0, hit_rate=None,
                                units=None, priced=0, unpriced=0, pending=40))
        assert "0%" not in line
        assert "none settled" in line
        assert "40 claims" in line

    def test_nothing_frozen_is_not_a_bad_record(self):
        line = board_line(board(claims=0, settled=0, landed=0, hit_rate=None, units=None))
        assert "nothing frozen" in line
        assert "%" not in line

    def test_a_graded_board_shows_the_denominator_with_the_rate(self):
        line = board_line(board())
        assert "24/35" in line and "69%" in line


class TestTheResidualIsTheResult:
    def test_the_claim_travels_with_the_outcome(self):
        line = board_line(board(hit_rate=68.6, mean_prob=64.0, residual=4.6))
        assert "64% claimed" in line

    def test_beating_the_claim_is_said_in_words_not_only_a_sign(self):
        line = board_line(board(residual=4.6))
        assert "beating" in line and "+5pts" in line

    def test_a_board_short_of_its_claim_is_not_dressed_up_by_a_high_rate(self):
        # 73% looks healthy and is a losing board when it promised 82%.
        line = board_line(board(landed=73, missed=27, settled=100, hit_rate=73.0,
                                mean_prob=82.0, residual=-9.0, priced=100))
        assert "short of its own claim" in line and "-9pts" in line

    def test_landing_as_claimed_is_neither_praised_nor_scolded(self):
        line = board_line(board(residual=0.4))
        assert "about as claimed" in line

    def test_no_stated_price_means_no_verdict_is_invented(self):
        line = board_line(board(mean_prob=None, residual=None))
        assert "claimed" not in line and "beating" not in line


class TestUnitsOnlyOverWhatWasPriced:
    def test_a_fully_priced_board_prints_the_total_plainly(self):
        assert units_text(board(units=3.21, priced=35, unpriced=0)) == "+3.21u"

    def test_a_partly_priced_board_says_what_the_total_covers(self):
        txt = units_text(board(units=3.21, priced=20, unpriced=15))
        assert "+3.21u" in txt and "20" in txt and "35" in txt

    def test_no_price_anywhere_means_no_units_line_at_all(self):
        # _tally answers None, not 0.0, when nothing was priced.
        assert units_text(board(units=None, priced=0, unpriced=35)) is None
        assert "u" not in board_line(board(units=None, priced=0, unpriced=35)).split("\n")[-1][-3:]

    def test_a_losing_total_keeps_its_sign(self):
        assert units_text(board(units=-4.40)).startswith("-4.40u")


class TestTheCard:
    def test_it_names_every_board_it_was_given(self):
        card = results_card({"weeks": 8, "boards": [
            board(key="streaks", label="Streaks"),
            board(key="perfect", label="Perfect games"),
            board(key="mismatch", label="Quick scan")]})
        for label in ("Streaks", "Perfect games", "Quick scan"):
            assert label in card

    def test_it_says_the_window_it_covers(self):
        assert "last 8 weeks" in results_card({"weeks": 8, "boards": [board()]})
        assert "last 1 week" in results_card({"weeks": 1, "boards": [board()]})

    def test_it_says_the_grading_was_frozen_before_kick_off(self):
        card = results_card({"weeks": 8, "boards": [board()]})
        assert "before kick-off" in card

    def test_an_empty_payload_is_an_honest_nothing_not_a_zero_record(self):
        for payload in ({}, None, {"boards": []}):
            card = results_card(payload)
            assert "No board has frozen a claim" in card
            assert "0%" not in card

    def test_a_malformed_row_cannot_take_the_card_down(self):
        card = results_card({"boards": [None, "x", {}, board()]})
        assert "Streaks" in card


class TestABoardOfTodaysRows:
    def rows(self, n):
        return [{"team": f"Team {i}", "opponent": "Opp", "line": 5, "is_home": True,
                 "prob": 0.72, "fair_odds": 1.39} for i in range(n)]

    def test_a_row_carries_the_line_the_opponent_and_the_price(self):
        card = board_card("⚽ Perfect games", self.rows(1))
        assert "Team 0 5+" in card and "v Opp" in card and "72%" in card
        assert "fair 1.39" in card

    def test_an_away_row_says_away(self):
        card = board_card("x", [{"team": "A", "opponent": "B", "venue": "away"}])
        assert "@ B" in card

    def test_a_long_board_is_trimmed_and_admits_it(self):
        card = board_card("x", self.rows(MAX_ROWS + 4))
        assert card.count("•") == MAX_ROWS
        assert f"{4} more" in card

    def test_a_short_board_claims_no_hidden_rows(self):
        assert "more on the site" not in board_card("x", self.rows(2))

    def test_an_empty_board_says_nothing_qualifies_not_an_error(self):
        assert "Nothing qualifies" in board_card("x", [])
        assert "Nothing qualifies" in board_card("x", None)


class TestValueNeedsAPrice:
    def test_the_best_edge_is_listed_first(self):
        card = value_card([{"team": "A", "line": 4, "ev": 3.1},
                           {"team": "B", "line": 5, "ev": 11.8},
                           {"team": "C", "line": 6, "ev": 7.2}])
        assert card.index("B") < card.index("C") < card.index("A")

    def test_a_row_shows_the_book_price_beside_the_fair_price(self):
        card = value_card([{"team": "A", "line": 4, "ev": 8.4,
                            "book_odds": 2.10, "fair_odds": 1.90}])
        assert "@ 2.10" in card and "fair 1.90" in card and "+8.4%" in card

    def test_a_feed_price_is_labelled_so_it_is_not_taken_for_a_chosen_one(self):
        # merge_prices stamps source; a human price and a scraped one are not the same
        # claim and the card must not present them as one.
        card = value_card([{"team": "A", "line": 4, "ev": 8.4, "odds_source": "api"}])
        assert "[api price]" in card
        plain = value_card([{"team": "A", "line": 4, "ev": 8.4, "odds_source": "manual"}])
        assert "[" not in plain

    def test_an_empty_board_distinguishes_no_edge_from_no_prices(self):
        card = value_card([])
        assert "no prices are stored" in card

    def test_a_row_without_an_ev_number_is_not_counted_as_an_edge(self):
        assert "no prices are stored" in value_card([{"team": "A", "ev": None},
                                                     {"team": "B"}])


class TestPerfectGamesShowsAllThreeLegs:
    def row(self, **kw):
        r = {"name": "Operário", "next_fixture": {"opponent": "CRB", "is_home": True},
             "streak": {"line": 5, "hits": 9, "settled": 10},
             "mismatch": {"line": 5, "prob": 71.4, "fair_odds": 1.40, "lambda": 6.8},
             "opp_leak": {"games": 10, "at_line": 8, "line": 5, "opponent": "CRB"}}
        r.update(kw)
        return r

    def test_the_run_the_opponent_and_the_price_all_appear(self):
        # Printing only the probability would make this the streak board with a new
        # heading — the agreement of three legs is the entire claim.
        card = perfect_card([self.row()])
        assert "9/10" in card, "the team's own run"
        assert "8/10" in card, "what the opponent has actually shipped"
        assert "fair 1.40" in card
        assert "Operário 5+ v CRB" in card

    def test_an_away_fixture_is_not_printed_as_a_home_one(self):
        card = perfect_card([self.row(next_fixture={"opponent": "CRB", "is_home": False})])
        assert "@ CRB" in card and " v CRB" not in card

    def test_an_empty_board_explains_the_bar_rather_than_apologising(self):
        card = perfect_card([])
        assert "three legs" in card
        assert "0%" not in card

    def test_a_row_missing_a_leg_still_prints_what_it_has(self):
        card = perfect_card([self.row(opp_leak={}, mismatch={})])
        assert "Operário" in card and "9/10" in card


class TestTheWeek:
    def day(self, d, n):
        return {"day": d, "fixtures": [
            {"home": f"H{i}", "away": f"A{i}",
             "best_angle": {"team": f"H{i}", "label": "5+ corners"}} for i in range(n)]}

    def test_each_day_lists_its_fixtures_with_the_angle(self):
        card = week_card({"fixtures": 2, "days": [self.day("2026-11-07", 2)]})
        assert "2026-11-07" in card
        assert "H0 v A0" in card and "H0 5+ corners" in card

    def test_a_day_that_qualified_nothing_is_printed_not_dropped(self):
        # An absent Thursday reads as missing data; an empty one reads as a quiet
        # Thursday. _fixture_board returns those days on purpose.
        card = week_card({"fixtures": 1, "days": [{"day": "2026-11-08", "fixtures": []},
                                                  self.day("2026-11-09", 1)]})
        assert "2026-11-08 — nothing qualified" in card
        assert "2026-11-09" in card

    def test_a_busy_day_is_trimmed_and_says_how_many_it_hid(self):
        card = week_card({"fixtures": 7, "days": [self.day("2026-11-07", 7)]})
        assert "…3 more" in card

    def test_it_does_not_imply_the_board_is_priced(self):
        card = week_card({"fixtures": 1, "days": [self.day("2026-11-07", 1)]})
        assert "not that it is priced" in card

    def test_an_empty_week_does_not_pretend_to_know_why(self):
        card = week_card({"days": [], "fixtures": 0})
        assert "calendar is empty or the data" in card


class TestWhatSettled:
    def rows(self):
        return [{"name": "Middlesbrough", "line": 6, "result": "win", "value": 9},
                {"name": "Hull", "line": 5, "result": "loss", "value": 3},
                {"name": "Stoke", "line": 4, "result": "pending", "value": None}]

    def test_each_row_carries_its_own_outcome(self):
        card = settled_card("2026-11-05", [
            {"label": "Streaks", "rows": self.rows(),
             "tally": {"landed": 1, "settled": 2, "units": 0.8,
                       "priced": 2, "unpriced": 0}}])
        assert "✅ Middlesbrough 6+" in card
        assert "❌ Hull 5+" in card
        assert "⏳ Stoke 4+" in card, "a pending row is pending, not a miss"

    def test_the_day_is_named_rather_than_called_yesterday(self):
        # A message read on Monday about "yesterday" is about the wrong day.
        card = settled_card("2026-11-05", [{"label": "Streaks", "rows": self.rows(),
                                            "tally": {"landed": 1, "settled": 2}}])
        assert "2026-11-05" in card
        assert "esterday" not in card

    def test_the_count_excludes_the_pending_row(self):
        card = settled_card("2026-11-05", [
            {"label": "Streaks", "rows": self.rows(),
             "tally": {"landed": 1, "settled": 2}}])
        assert "1/2" in card and "1/3" not in card

    def test_nothing_settled_refuses_to_guess_why(self):
        card = settled_card("2026-11-05", [{"label": "Streaks", "rows": [],
                                            "tally": {}}])
        assert "those are different" in card
        assert "0/0" not in card


class TestTheStoredLineIsNotTheLineWeSay:
    def test_a_stored_half_line_is_printed_as_the_plus_the_channel_says(self):
        # build_markets carries 4.5 and prices nb_ge(int(4.5)+1) = P(X>=5). The channel
        # posts say "5+". Printing "4.5+" names a different bet than the one priced.
        assert plus_line(4.5) == 5
        assert plus_line(9.5) == 10
        assert plus_line(13.5) == 14

    def test_a_bare_integer_is_handled_the_same_way(self):
        # Older stored rows and the seeders have carried both spellings.
        assert plus_line(4) == 5

    def test_a_missing_line_does_not_become_one(self):
        for bad in (None, "x", float("nan")):
            assert plus_line(bad) is None

    def test_the_card_quotes_the_line_it_priced(self):
        card = value_card(value_rows([{
            "status": "ok", "home_name": "Operário", "away_name": "CRB",
            "odds_source": "manual",
            "best": {"group": "home", "line": 4.5, "ev": 8.4,
                     "book_odds": 2.10, "fair_odds": 1.90}}]))
        assert "Operário 5+" in card
        assert "4+" not in card

    def test_the_away_side_gets_the_away_name(self):
        out = value_rows([{"status": "ok", "home_name": "H", "away_name": "A",
                           "best": {"group": "away", "line": 3.5, "ev": 2.0, "book_odds": 2.0}}])
        assert out[0]["team"] == "A" and out[0]["line"] == 4

    def test_a_match_total_is_named_as_the_fixture_not_a_team(self):
        out = value_rows([{"status": "ok", "home_name": "H", "away_name": "A",
                           "best": {"group": "total", "line": 9.5, "ev": 2.0, "book_odds": 2.0}}])
        assert out[0]["team"] == "H v A total" and out[0]["line"] == 10

    @pytest.mark.parametrize("status", ["kicked_off", "no_fixture", "below_floor",
                                        "outside_window", "no_market", "no_teams"])
    def test_a_row_that_is_not_a_pick_is_not_shown_as_one(self, status):
        # The board returns everything it examined, labelled, so a screen can explain an
        # absence. A card is not that screen.
        assert value_rows([{"status": status, "home_name": "H", "away_name": "A",
                            "best": {"group": "home", "line": 4.5, "ev": 20.0}}]) == []


class TestTheStalenessAlarm:
    def test_fresh_data_says_nothing(self):
        assert stale_warning(3, 12) is None
        assert stale_warning(12, 12) is None, "at the threshold is not past it"

    def test_stale_data_names_both_numbers(self):
        w = stale_warning(18.5, 12)
        assert "18h" in w and "12h" in w

    def test_it_says_the_boards_are_built_on_the_old_data(self):
        # The failure this exists for: a sync errored on all 36 competitions and the
        # boards kept rendering, looking current.
        assert "boards" in stale_warning(18.5, 12)

    @pytest.mark.parametrize("bad", [None, "x", float("nan")])
    def test_an_unreadable_clock_does_not_cry_wolf(self, bad):
        assert stale_warning(bad, 12) is None


class TestTheMorningDigest:
    def test_it_keeps_the_sections_it_is_given(self):
        card = digest_card("Friday 6 November", ["🎯 Perfect games\n• A 5+", "💰 EV\n• B"])
        assert "Friday 6 November" in card
        assert "Perfect games" in card and "💰 EV" in card

    def test_the_staleness_line_comes_first_and_is_never_dropped(self):
        # It is the one line that changes how everything below it should be read.
        warn = stale_warning(20, 12)
        card = digest_card("Friday", ["x" * 3000, "y" * 3000], stale=warn)
        assert card.index(warn) < card.index("x")

    def test_an_oversized_section_is_dropped_whole_and_declared(self):
        # send() trims to 4096 mid-word, so a section cut in half reads as a short board.
        card = digest_card("Friday", ["a" * 2000, "b" * 2000, "c" * 2000])
        assert len(card) <= TELEGRAM_LIMIT
        assert "wouldn't fit" in card
        assert card.count("c" * 2000) == 0

    def test_a_message_that_fits_claims_nothing_was_left_out(self):
        assert "wouldn't fit" not in digest_card("Friday", ["short", "also short"])

    def test_an_empty_morning_says_so_rather_than_sending_a_bare_heading(self):
        for sections in ([], None, ["", "   "]):
            card = digest_card("Friday", sections)
            assert "Nothing on the boards" in card


class TestNothingHereTouchesTheDatabase:
    def test_the_module_imports_no_client(self):
        import ast
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "bot_cards.py")) as fh:
            tree = ast.parse(fh.read())
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        for n in names:
            assert not any(b in n for b in ("motor", "pymongo", "httpx", "server")), n


class TestThePostingRule:
    """Lowest line priced 1.80+, sent only if THAT line clears the floor. Never the
    biggest EV further up the ladder — Reading 8+ at 10.00 with 5+ at 1.73 was the bug."""

    def ladder(self, *rungs, group="home"):
        return [{"group": group, "key": f"{group}_over_{l}", "line": l,
                 "book_odds": o, "ev": ev} for l, o, ev in rungs]

    def rows(self, ladder):
        return [{"status": "ok", "home_name": "Reading", "away_name": "X",
                 "best": max(ladder, key=lambda m: m["ev"] or -99), "ladder": ladder}]

    def test_reading_8_plus_at_10_is_not_sent(self):
        # 5+ 1.73 (too short), 6+ 2.40 is THE line but only +2%, 8+ 10.00 is +30%.
        lad = self.ladder((4.5, 1.73, 8.0), (5.5, 2.40, 2.0), (6.5, 4.5, 15.0), (7.5, 10.0, 30.0))
        assert value_rows(self.rows(lad), min_ev=5.0) == []

    def test_the_first_line_over_1_80_is_sent_when_it_clears(self):
        lad = self.ladder((4.5, 1.73, 8.0), (5.5, 2.40, 9.0), (7.5, 10.0, 30.0))
        out = value_rows(self.rows(lad), min_ev=5.0)
        assert [(r["line"], r["book_odds"]) for r in out] == [(6, 2.40)]

    def test_one_bet_per_side(self):
        lad = (self.ladder((4.5, 1.90, 6.0), (5.5, 2.6, 12.0))
               + self.ladder((3.5, 2.1, 7.0), group="away"))
        out = value_rows(self.rows(lad), min_ev=5.0)
        assert sorted((r["group"], r["line"]) for r in out) == [("away", 4), ("home", 5)]

    def test_a_long_shot_with_no_lower_price_is_not_a_safe_line(self):
        lad = self.ladder((7.5, 6.0, 25.0))
        assert value_rows(self.rows(lad), min_ev=5.0) == []

    def test_unpriced_rungs_are_skipped_not_anchors(self):
        lad = self.ladder((4.5, None, None), (5.5, 1.95, 6.0))
        out = value_rows(self.rows(lad), min_ev=5.0)
        assert [r["line"] for r in out] == [6]


class TestTheFreeChannel:
    def test_the_free_floor_is_1_60_and_nothing_below(self):
        lad = [{"group": "home", "key": "home_over_3.5", "line": 3.5, "book_odds": 1.55, "ev": 9.0},
               {"group": "home", "key": "home_over_4.5", "line": 4.5, "book_odds": 1.65, "ev": 7.0},
               {"group": "home", "key": "home_over_5.5", "line": 5.5, "book_odds": 2.30, "ev": 15.0}]
        rows = [{"status": "ok", "home_name": "H", "away_name": "A", "best": lad[2], "ladder": lad}]
        free = value_rows(rows, min_ev=5.0, min_odds=1.60)
        assert [(r["line"], r["book_odds"]) for r in free] == [(5, 1.65)]
        paid = value_rows(rows, min_ev=5.0)
        assert [(r["line"], r["book_odds"]) for r in paid] == [(6, 2.30)]

    def test_stakes_follow_the_edge_and_the_price(self):
        from bot_cards import free_stake
        assert free_stake(10, 2.20) == 1.0
        assert free_stake(30, 10.0) == 0.5, "a long price gets less, even at a big edge"
        assert free_stake(40, 1.70) == 2.0, "capped"
        assert free_stake(1, 4.0) == 0.25, "floored"
        assert free_stake(-3, 2.0) is None and free_stake(5, None) is None

    def test_results_card_reads_like_the_channel(self):
        from bot_cards import free_results_card
        rows = [
            {"result": "win", "price": 1.80, "stake": 1.0, "name": "Reading", "subject": "team", "line": 5},
            {"result": "loss", "price": 2.10, "stake": 0.5, "name": "Hull", "subject": "team", "line": 6, "value": 5},
            {"result": "pending", "price": 1.9, "stake": 1.0, "match": "A v B", "subject": "match", "line": 11},
        ]
        card = free_results_card("Wed 11 Nov", rows, {"settled": 2, "landed": 1, "missed": 1,
                                                       "hit_rate": 50.0, "units": 0.3, "roi": 20.0})
        assert "📈 PROFIT: +0.30u (1.5u staked)" in card
        assert "✅ Reading 5+ team @ 1.80: +0.80u" in card
        assert "❌ Hull 6+ team @ 2.10: -0.50u" in card and "ONE CORNER AWAY" in card
        assert "still to settle: A v B 11+ match corners" in card
        assert "1W-1L" in card and "ROI +20.0%" in card


def test_the_unit_note_appears_only_when_a_stake_does():
    from bot_cards import value_card, STAKE_NOTE
    row = {"team": "H", "subject": "H", "match": "H v A", "line": 5, "ev": 8.0,
           "book_odds": 1.9, "dedup_key": "f:1"}
    assert STAKE_NOTE not in value_card([row])
    assert STAKE_NOTE in value_card([{**row, "stake": 1.0}])
