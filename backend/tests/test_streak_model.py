"""Unit tests for the streak model: over/under settlement, exact-line voids,
current/longest run tracking and the under price (push-adjusted). Pure functions —
no backend or database needed."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    LOSS, VOID, WIN, _streak_projection, pick_streak_line, settle_streak_leg,
    streak_legs, streak_line_label, streak_runs, streak_value,
)


def game(date, cf, ca=0, home=True):
    return {"date": date, "corners_for": cf, "corners_against": ca, "home": home,
            "opponent": "Opp", "shots_for": 12, "fh_goals_for": 0}


# --- settlement ---
def test_over_leg_never_voids():
    assert settle_streak_leg(4, 4, "over") == WIN      # "4+" == over 3.5
    assert settle_streak_leg(9, 4, "over") == WIN
    assert settle_streak_leg(3, 4, "over") == LOSS


def test_under_leg_voids_on_the_exact_line():
    assert settle_streak_leg(8, 9, "under") == WIN
    assert settle_streak_leg(9, 9, "under") == VOID
    assert settle_streak_leg(10, 9, "under") == LOSS


def test_streak_value_subject():
    m = game("2026-01-01", 4, 6)
    assert streak_value(m, "team") == 4
    assert streak_value(m, "match") == 10


def test_line_label():
    assert streak_line_label(5, "over") == "5+"
    assert streak_line_label(5, "under") == "under 5"


# --- runs ---
def test_void_does_not_break_or_extend_a_run():
    matches = [game("2026-01-01", 3), game("2026-01-08", 5), game("2026-01-15", 2)]
    runs = streak_runs(streak_legs(matches, 5, "under", "team"))
    assert runs["current"] == {"length": 2, "start_date": "2026-01-01", "last_date": "2026-01-15",
                               "voids": 1, "status": "active"}
    assert runs["longest"]["length"] == 2
    assert runs["longest"]["is_current"] is True


def test_current_run_reports_start_date_and_active_status():
    matches = [game(f"2026-01-{d:02d}", c) for d, c in
               ((1, 2), (8, 9), (15, 6), (22, 7), (29, 8))]
    runs = streak_runs(streak_legs(matches, 5, "over", "team"))
    assert runs["current"]["length"] == 4
    assert runs["current"]["start_date"] == "2026-01-08"
    assert runs["current"]["last_date"] == "2026-01-29"
    assert runs["current"]["status"] == "active"


def test_broken_run_has_zero_length_and_no_start_date():
    matches = [game(f"2026-01-{d:02d}", c) for d, c in ((1, 6), (8, 7), (15, 2))]
    runs = streak_runs(streak_legs(matches, 5, "over", "team"))
    assert runs["current"] == {"length": 0, "start_date": None, "last_date": None,
                               "voids": 0, "status": "broken"}
    assert runs["longest"]["length"] == 2
    assert runs["longest"]["start_date"] == "2026-01-01"
    assert runs["longest"]["end_date"] == "2026-01-08"
    assert runs["longest"]["is_current"] is False


def test_longest_run_beats_the_live_one():
    matches = [game(f"2026-01-{d:02d}", c) for d, c in
               ((1, 6), (8, 6), (15, 6), (22, 6), (29, 1), (30, 6))]
    runs = streak_runs(streak_legs(matches, 5, "over", "team"))
    assert runs["current"]["length"] == 1
    assert runs["longest"]["length"] == 4
    assert runs["longest"]["is_current"] is False


def test_runs_track_match_totals():
    matches = [game("2026-01-01", 4, 4), game("2026-01-08", 3, 6), game("2026-01-15", 6, 6)]
    runs = streak_runs(streak_legs(matches, 10, "under", "match"))
    # 8 under, 9 under, 12 over -> run of two, then broken
    assert runs["current"]["length"] == 0
    assert runs["longest"]["length"] == 2


# --- ladder ---
def test_under_ladder_picks_the_tightest_held_line():
    # under 7 also held, but under 6 is the tighter line still standing (the 6 pushes)
    assert pick_streak_line([4, 5, 6, 4, 5], "under", "team", 5) == 6


def test_over_ladder_picks_the_highest_cleared_line():
    assert pick_streak_line([6, 7, 6, 8, 6], "over", "team", 5) == 6


def test_ladder_ignores_a_line_carried_entirely_by_voids():
    # every game landed exactly on 5: under 5 is all voids, so the tightest real line is 6
    assert pick_streak_line([5, 5, 5, 5, 5], "under", "team", 5) == 6


def test_ladder_lets_voids_count_towards_min_hits():
    # under 6: four wins and one push — still a 5-game run
    assert pick_streak_line([5, 4, 6, 3, 5], "under", "team", 5) == 6


def test_match_ladder_reaches_beyond_team_lines():
    # a total of 20 is off the end of the team ladder (1-15) but on the match ladder
    assert pick_streak_line([18, 19, 20, 18, 19], "under", "match", 5) == 20


# --- projection ---
@pytest.fixture
def matchup():
    team = {"team_id": "t", "league_id": "lg", "name": "Team",
            "real_matches": [game(f"2026-01-{d:02d}", 5, 5) for d in range(1, 9)]}
    opp = {"team_id": "o", "league_id": "lg", "name": "Opp",
           "real_matches": [game(f"2026-01-{d:02d}", 5, 5, home=False) for d in range(1, 9)]}
    return team, opp


def test_under_projection_prices_the_settled_outcomes(matchup):
    team, opp = matchup
    p = _streak_projection(team, opp, "home", "away", 5, "under", "team", 12.0, {})
    assert p["market_key"] == "home_under_5"
    assert p["void_prob"] > 0
    # fair odds ignore the pushed stake: 1 / (p_win / (p_win + p_loss))
    implied = 1 / p["fair_odds"]
    assert implied == pytest.approx(p["prob"] / (100 - p["void_prob"]), abs=0.01)


def test_over_projection_keeps_the_half_line_market_key(matchup):
    team, opp = matchup
    p = _streak_projection(team, opp, "home", "away", 5, "over", "team", 12.0, {})
    assert p["market_key"] == "home_over_4.5"
    assert p["void_prob"] == 0.0
    assert p["fair_odds"] == pytest.approx(100 / p["prob"], abs=0.05)


def test_under_ev_credits_the_void_back(matchup):
    team, opp = matchup
    book = 2.0
    p = _streak_projection(team, opp, "home", "away", 5, "under", "team", 12.0,
                           {"home_under_5": book})
    p_win, p_void = p["prob"] / 100, p["void_prob"] / 100
    # probabilities come back rounded to 0.1%, so allow the recomputation to drift
    assert p["ev"] == pytest.approx((book * p_win + p_void - 1) * 100, abs=0.35)
    assert p["tier"] in ("strong", "small", "none")


def test_match_projection_uses_the_total_market(matchup):
    team, opp = matchup
    p = _streak_projection(team, opp, "home", "away", 10, "under", "match", 12.0, {})
    assert p["market_key"] == "total_under_10"
    assert p["lambda"] == pytest.approx(p["lambda_team"] + p["lambda_opp"], abs=0.01)
    assert p["opp_for"] == 5.0 and p["team_conceded"] == 5.0


def test_projection_needs_both_sides(matchup):
    team, _ = matchup
    assert _streak_projection(team, None, "home", "away", 5, "under", "team", 12.0, {}) is None
