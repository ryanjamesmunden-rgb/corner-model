"""Production prices from VENUE-SPLIT form; the harnesses pooled both venues.

That gap is not academic. It is what made `venue_delta` look like a +9.1 edge on the
chase-board rank test: the ranking was correcting an error only the HARNESS was making.
On synthetic data drawn from the model's own distribution — no market edge by
construction — venue_delta's spread fell from +17.3 to +3.1 (control -6.9) once lambda
was built the way production builds it.

These pin the property so the two cannot drift apart again."""
import inspect
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import expected_lambdas, team_split  # noqa: E402


def game(home, cf, ca=4):
    return {"date": "2026-01-01", "home": home, "corners_for": cf, "corners_against": ca,
            "opponent": "X", "shots_for": 12, "fh_goals_for": 0}


def skewed_team(name="T"):
    """Strong at home, weak away — the whole point of splitting by venue."""
    return {"team_id": name, "name": name, "league_id": "lg",
            "real_matches": [game(True, 9) for _ in range(8)]
                            + [game(False, 3) for _ in range(8)]}


# --- production ---
def test_production_prices_from_venue_split_form():
    """If this ever stops being true, the harness fix below is measuring the wrong thing."""
    src = inspect.getsource(expected_lambdas)
    assert 'team_split(_src(home), "home"' in src
    assert 'team_split(_src(away), "away"' in src


def test_a_venue_skew_actually_moves_the_split():
    t = skewed_team()
    assert team_split(t["real_matches"], "home", 0)["for_avg"] == 9.0
    assert team_split(t["real_matches"], "away", 0)["for_avg"] == 3.0
    assert team_split(t["real_matches"], "overall", 0)["for_avg"] == 6.0


def test_pooling_venues_would_misprice_a_skewed_team():
    """The error the old harness was making, quantified: 6.0 pooled vs 9.0 at home."""
    t = skewed_team()
    pooled = team_split(t["real_matches"], "overall", 0)["for_avg"]
    at_home = team_split(t["real_matches"], "home", 0)["for_avg"]
    assert at_home - pooled == 3.0          # what venue_delta was "finding"


def test_expected_lambdas_separates_home_and_away_for_the_same_team():
    strong_home, weak_away = skewed_team("A"), skewed_team("B")
    lam = expected_lambdas(strong_home, weak_away)
    assert lam["home"] > lam["away"], lam


def test_venue_split_falls_back_to_overall_with_no_games_there():
    """Production's `played == 0` fallback — the harness mirrors it."""
    away_only = {"team_id": "C", "name": "C", "league_id": "lg",
                 "real_matches": [game(False, 5) for _ in range(6)]}
    assert team_split(away_only["real_matches"], "home", 0)["played"] == 0
    lam = expected_lambdas(away_only, skewed_team("D"))
    assert lam["home"] > 0                  # priced, not zeroed


# --- the harness now mirrors it ---
def test_backtest_defaults_to_venue_form():
    sig = inspect.signature(server.backtest)
    assert sig.parameters["venue_form"].default is True


def test_backtest_keeps_a_pooled_escape_hatch():
    """So the old numbers can be reproduced rather than just asserted about."""
    assert "venue_form" in inspect.getsource(server.backtest)
    assert "pooled_same_sample" in inspect.getsource(server.backtest)


def test_row_eligibility_stays_on_pooled_history():
    """Both modes must score the SAME rows, or the comparison is between two samples."""
    src = inspect.getsource(server.backtest)
    assert "len(hist_for[h]) >= min_games" in src
    assert "Row eligibility stays on POOLED history" in src


def test_the_backtest_tracks_venue_keyed_history():
    src = inspect.getsource(server.backtest)
    for name in ("hist_for_v", "hist_against_v", "hist_shots_v", "hist_blocked_v"):
        assert name in src, name
