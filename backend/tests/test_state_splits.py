"""Unit tests for corners-by-match-state.

The thing these mostly guard is honesty about what the numbers are: full-match corners
in games where the team was in a given state, with the sample size attached, and a
missing goal never quietly classified as a draw."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _match_state, team_state_splits  # noqa: E402


def game(cf, ca, fh_for=0, fh_against=0, gf=None, ga=None, home=True):
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "fh_goals_for": fh_for, "fh_goals_against": fh_against,
            "goals_for": gf if gf is not None else fh_for,
            "goals_against": ga if ga is not None else fh_against,
            "opponent": "X", "date": "2026-01-01"}


# --- state derivation ---
def test_half_time_state():
    assert _match_state(game(5, 5, fh_for=0, fh_against=1), "ht") == -1
    assert _match_state(game(5, 5, fh_for=1, fh_against=1), "ht") == 0
    assert _match_state(game(5, 5, fh_for=2, fh_against=0), "ht") == 1


def test_full_time_state_is_independent_of_half_time():
    m = game(5, 5, fh_for=0, fh_against=1, gf=3, ga=1)      # behind at HT, won the game
    assert _match_state(m, "ht") == -1
    assert _match_state(m, "ft") == 1


def test_missing_goals_are_unknown_not_a_draw():
    """The trap: a blank must not be read as 0-0 and counted as level."""
    m = {"home": True, "corners_for": 5, "corners_against": 5}
    assert _match_state(m, "ht") is None
    assert _match_state(m, "ft") is None
    m2 = game(5, 5)
    m2["fh_goals_against"] = None
    assert _match_state(m2, "ht") is None


# --- aggregation ---
def test_splits_group_corners_by_state():
    matches = [
        game(8, 3, fh_for=0, fh_against=1),      # trailing at HT
        game(6, 4, fh_for=0, fh_against=2),      # trailing at HT
        game(4, 6, fh_for=1, fh_against=0),      # leading at HT
    ]
    s = team_state_splits(matches)
    assert s["ht"]["trailing"]["games"] == 2
    assert s["ht"]["trailing"]["won"] == 7.0            # (8+6)/2
    assert s["ht"]["trailing"]["conceded"] == 3.5       # (3+4)/2
    assert s["ht"]["trailing"]["total"] == 10.5
    assert s["ht"]["leading"]["games"] == 1
    assert s["ht"]["level"]["games"] == 0
    assert s["ht"]["level"]["won"] is None              # no games, not a zero


def test_full_time_buckets_use_result_labels():
    matches = [game(5, 5, gf=2, ga=1), game(6, 6, gf=0, ga=0), game(7, 7, gf=0, ga=3)]
    s = team_state_splits(matches)
    assert s["ft"]["won"]["games"] == 1
    assert s["ft"]["drew"]["games"] == 1
    assert s["ft"]["lost"]["games"] == 1
    assert s["ft"]["lost"]["won"] == 7.0                # corners won in games they lost


def test_unclassifiable_games_are_counted_not_hidden():
    matches = [game(5, 5, fh_for=0, fh_against=1), {"home": True, "corners_for": 9,
                                                    "corners_against": 1}]
    s = team_state_splits(matches)
    assert s["played"] == 2
    assert s["ht"]["unknown_games"] == 1
    assert sum(s["ht"][k]["games"] for k in ("trailing", "level", "leading")) == 1


def test_splits_respect_venue_and_window():
    matches = [game(9, 1, fh_for=0, fh_against=1, home=True),
               game(3, 7, fh_for=0, fh_against=1, home=False),
               game(5, 5, fh_for=0, fh_against=1, home=True)]
    assert team_state_splits(matches, "home")["ht"]["trailing"]["won"] == 7.0   # (9+5)/2
    assert team_state_splits(matches, "away")["ht"]["trailing"]["won"] == 3.0
    assert team_state_splits(matches, "overall", 1)["played"] == 1


def test_empty_history():
    s = team_state_splits([])
    assert s["played"] == 0
    assert s["ht"]["trailing"]["games"] == 0 and s["ht"]["trailing"]["won"] is None
