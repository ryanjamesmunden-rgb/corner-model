"""When a positive-EV bet is worth sending, and when saying it again is noise.

WHY THIS IS A FILE OF ITS OWN. The value send hangs off the odds fetch, so every bet is
re-examined each time a price lands — several times on a matchday. Two opposite failures
sit either side of that, and both have happened in this repo: sending every row every
time is what produced "the bot sends me so many messages that are not value" (see
social_draft.yml's header), and suppressing a row for good is worse, because a bet whose
edge has doubled never gets mentioned and nothing reports that it did not.

So the rule is "new, or meaningfully better", and this pins the boundary.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot_cards  # noqa: E402

GAIN = 4.0


# --- a bet nobody has been told about ----------------------------------------------

def test_a_bet_never_sent_goes_out():
    assert bot_cards.worth_sending(6.0, None, GAIN) is True


def test_zero_ev_is_still_a_number_not_a_missing_one():
    """0.0 is falsy, and `previous_ev or None` would read it as never sent. A bet sent at
    0% and still at 0% must stay quiet."""
    assert bot_cards.worth_sending(0.0, 0.0, GAIN) is False


def test_a_negative_previous_is_not_treated_as_unsent():
    assert bot_cards.worth_sending(-2.0, -2.0, GAIN) is False


# --- the re-send boundary ----------------------------------------------------------

def test_the_same_price_is_not_sent_twice():
    assert bot_cards.worth_sending(6.0, 6.0, GAIN) is False


def test_a_drift_below_the_step_stays_quiet():
    assert bot_cards.worth_sending(9.9, 6.0, GAIN) is False


def test_exactly_the_step_goes_out():
    """>= rather than >, so the documented four points is the threshold that sends and
    not the one just past it."""
    assert bot_cards.worth_sending(10.0, 6.0, GAIN) is True


def test_a_real_move_goes_out():
    assert bot_cards.worth_sending(15.0, 5.0, GAIN) is True


def test_a_shrinking_edge_is_never_re_sent():
    """The first message already made the claim. A worse price does not need announcing,
    and a second message about it would read as a second recommendation."""
    assert bot_cards.worth_sending(1.0, 12.0, GAIN) is False


def test_a_gain_of_zero_sends_any_improvement():
    assert bot_cards.worth_sending(6.1, 6.0, 0.0) is True
    assert bot_cards.worth_sending(6.0, 6.0, 0.0) is True
    assert bot_cards.worth_sending(5.9, 6.0, 0.0) is False


# --- numbers that are not numbers ---------------------------------------------------

def test_a_non_finite_ev_is_never_sent():
    """The reason _pct exists: a NaN sailing through a `>=` comparison is how "nanh old"
    reached a message once already. NaN >= anything is False, so a naive test would
    silently drop a live bet instead of reporting the bad value."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert bot_cards.worth_sending(bad, None, GAIN) is False, bad


def test_a_missing_ev_is_never_sent():
    for bad in (None, "6.0", "", {}, [], True, False):
        assert bot_cards.worth_sending(bad, None, GAIN) is False, repr(bad)


def test_an_unreadable_previous_counts_as_never_sent():
    """One duplicate is recoverable; permanently silencing a live bet is not. So a stored
    value that cannot be read fails towards sending."""
    for bad in (float("nan"), "lots", {}, [], None, True):
        assert bot_cards.worth_sending(6.0, bad, GAIN) is True, repr(bad)


def test_an_unreadable_gain_falls_back_to_any_improvement():
    for bad in (None, "four", float("nan")):
        assert bot_cards.worth_sending(6.1, 6.0, bad) is True, repr(bad)
        assert bot_cards.worth_sending(5.9, 6.0, bad) is False, repr(bad)


def test_booleans_are_not_accepted_as_ev():
    """True == 1 in Python, so a bool reaching this would price a bet at 1% EV. _pct
    rejects it for the same reason everywhere else in this module."""
    assert bot_cards.worth_sending(True, None, GAIN) is False
    assert bot_cards.worth_sending(6.0, True, GAIN) is True


# --- the card it feeds --------------------------------------------------------------

def test_the_card_still_renders_what_survives_the_filter():
    """worth_sending decides WHICH rows go; value_rows/value_card decide how they read.
    This is the join between them, on the shape value_board actually returns."""
    board = [
        {"status": "ok", "fixture_id": "nor-el-1", "home_name": "Kristiansund BK",
         "away_name": "Valerenga", "odds_source": "api",
         "best": {"group": "away", "line": 5, "ev": 12.4,
                  "book_odds": 1.8, "fair_odds": 1.6, "key": "away_over_5"}},
        {"status": "below_floor", "fixture_id": "nor-el-2", "home_name": "A",
         "away_name": "B", "best": {"group": "home", "line": 5, "ev": 0.4,
                                    "book_odds": 2.0, "fair_odds": 2.0,
                                    "key": "home_over_5"}},
    ]
    kept = [r for r in board
            if r["status"] == "ok"
            and bot_cards.worth_sending(r["best"]["ev"], None, GAIN)]
    assert len(kept) == 1
    card = bot_cards.value_card(bot_cards.value_rows(kept))
    assert "Valerenga" in card
    assert "1.80" in card, "the book price has to be in the message to be tweetable"
    assert "6+" in card, "a line of 5 prices P(X>=6) and the post says 6+"


def test_an_empty_send_is_not_built_as_a_card():
    """The endpoint returns early rather than rendering value_card's empty state. That
    text explains an empty BOARD to someone who asked; sending it unprompted on every
    quiet fetch is the noise this whole design avoids."""
    assert "No positive-EV rows" in bot_cards.value_card([])
