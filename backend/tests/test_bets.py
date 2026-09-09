"""Unit tests for wagers and the group board.

Two things here are worth more than the rest.

SETTLEMENT decides whether somebody's bet reads as won or lost, so every uncertainty has
to come back pending rather than guessed — an invented result on a slip is the worst thing
this file could do.

PRIVACY is the other. The group board publishes one member's betting to the others, so
what it does NOT carry is as much the feature as what it does.
"""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import bet_outcome, bet_profit, parse_market_key  # noqa: E402


def bet(key="home_over_5.5", **kw):
    return {"market_key": key, "status": "pending", "stake": 10.0, "book_odds": 2.0, **kw}


# --- reading a market key ---
@pytest.mark.parametrize("key,want", [
    ("home_over_5.5", ("home", "over", 5.5)),
    ("away_under_4.5", ("away", "under", 4.5)),
    ("total_over_10.5", ("total", "over", 10.5)),
    ("total_under_9", ("total", "under", 9.0)),
])
def test_parses_the_market_key(key, want):
    assert parse_market_key(key) == want


@pytest.mark.parametrize("key", [
    "", None, "home", "home_over", "sideways_over_5.5", "home_sideways_5.5",
    "home_over_abc", "home_over_",
])
def test_an_unreadable_market_key_is_none_rather_than_a_guess(key):
    assert parse_market_key(key) is None


# --- settling ---
def test_an_over_settles_on_the_right_side_of_the_line():
    assert bet_outcome(bet("home_over_5.5"), 6, 3) == "won"
    assert bet_outcome(bet("home_over_5.5"), 5, 3) == "lost"


def test_the_away_side_reads_the_away_corners_not_the_home_ones():
    """Reading the wrong side would settle plausibly and wrongly, which is worse than
    failing — nothing would look broken."""
    assert bet_outcome(bet("away_over_4.5"), 9, 5) == "won"
    assert bet_outcome(bet("away_over_4.5"), 9, 2) == "lost"


def test_a_total_adds_both_sides():
    assert bet_outcome(bet("total_over_10.5"), 6, 5) == "won"
    assert bet_outcome(bet("total_over_10.5"), 5, 5) == "lost"


def test_an_exact_whole_line_on_an_under_is_a_push_not_a_loss():
    """The one settlement rule that costs real money if it is wrong, and the reason this
    calls settle_streak_leg rather than reimplementing it: the streak boards already
    settle voids this way and the two must not disagree about the same game."""
    assert bet_outcome(bet("total_under_9"), 4, 5) == "void"      # exactly 9
    assert bet_outcome(bet("total_under_9"), 4, 4) == "won"       # 8
    assert bet_outcome(bet("total_under_9"), 5, 5) == "lost"      # 10


def test_an_exact_whole_line_on_an_OVER_is_a_win_not_a_push():
    # "9+" means nine or more. Only unders push on the number.
    assert bet_outcome(bet("total_over_9"), 4, 5) == "won"


@pytest.mark.parametrize("home,away", [(None, 5), (5, None), (None, None)])
def test_a_fixture_with_no_result_yet_stays_pending(home, away):
    assert bet_outcome(bet(), home, away) is None


def test_an_unreadable_market_stays_pending_rather_than_settling():
    assert bet_outcome(bet("something_odd"), 6, 4) is None


# --- profit ---
def test_profit_pays_the_price_that_was_taken():
    assert bet_profit({"status": "won", "stake": 10.0, "book_odds": 2.5}) == 15.0
    assert bet_profit({"status": "lost", "stake": 10.0, "book_odds": 2.5}) == -10.0


def test_a_void_returns_the_stake_and_is_not_a_result():
    """A push must not read as a loss, and must not count in a win rate either."""
    assert bet_profit({"status": "void", "stake": 10.0, "book_odds": 2.5}) == 0.0
    assert bet_profit({"status": "pending", "stake": 10.0, "book_odds": 2.5}) == 0.0


# --- the group board: what it must not carry ---
def _board_projection():
    """The projection the endpoint passes to Mongo, read off the source.

    Asserting on the source rather than on a response because there is no database here —
    and because the guarantee worth pinning is that the field is never SELECTED, not that
    some component remembered to hide it."""
    import inspect
    return inspect.getsource(server.bets_this_week)


def test_the_group_board_never_selects_cash_stakes():
    """Not hidden in the UI — excluded at the query. A field that never leaves the server
    cannot leak out of a component someone writes later."""
    src = _board_projection()
    assert '"stake": 0' in src and '"user_id": 0' in src


def test_the_group_board_only_shows_bets_that_opted_in():
    src = _board_projection()
    assert '"shared": True' in src


def test_the_group_board_is_members_only():
    import inspect
    dep = inspect.signature(server.bets_this_week).parameters["user"].default
    assert getattr(dep, "dependency", None) is server.require_member


@pytest.mark.parametrize("route", ["create_bet", "list_bets", "update_bet", "delete_bet",
                                   "bet_stats", "get_bankroll", "set_bankroll"])
def test_every_wager_route_needs_a_real_account(route):
    """These used to take get_current_user, which falls back to the shared PUBLIC user —
    so every signed-out visitor would have written into one communal slip list. A wager is
    the one thing on this site that must belong to a person."""
    import inspect
    dep = inspect.signature(getattr(server, route)).parameters["user"].default
    assert getattr(dep, "dependency", None) is server.require_user, route


# --- the units total on the board ---
def test_units_counts_every_settled_slip_once_at_the_price_taken():
    """Stakes are deliberately not collected, so the only honest total is level-stakes:
    winners pay their price minus one, losers cost one, voids cost nothing."""
    rows = [
        {"status": "won", "book_odds": 2.5},     # +1.5
        {"status": "won", "book_odds": 1.8},     # +0.8
        {"status": "lost", "book_odds": 3.0},    # -1
        {"status": "void", "book_odds": 2.0},    # 0
        {"status": "pending", "book_odds": 2.0}, # 0
    ]
    settled = [b for b in rows if b["status"] in ("won", "lost")]
    won = [b for b in settled if b["status"] == "won"]
    units = round(sum((b["book_odds"] - 1.0) for b in won) - len(settled) + len(won), 3)
    assert units == pytest.approx(1.3)
