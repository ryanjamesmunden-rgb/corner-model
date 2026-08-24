"""Unit tests for shot-volume feature capture: statistics parsing, the None-vs-zero
rule for uncovered fixtures, and the per-team aggregation. Pure functions — no API,
no database."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
os.environ.setdefault("API_FOOTBALL_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import SHOT_FEATURES, team_features  # noqa: E402
from sync_real import _feature_sample, _stat_int, parse_team_stats  # noqa: E402


def stats(**kwargs):
    """API-Football shape: a list of {"type": ..., "value": ...}."""
    return [{"type": k, "value": v} for k, v in kwargs.items()]


# --- value parsing ---
@pytest.mark.parametrize("raw,expected", [
    (11, 11), (0, 0), ("14", 14), ("45%", 45), (7.0, 7),
    (None, None), ("", None), ("n/a", None), (True, None),
])
def test_stat_int(raw, expected):
    assert _stat_int(raw) == expected


# --- statistics block parsing ---
def test_parses_the_four_features_plus_corners():
    parsed = parse_team_stats(stats(**{
        "Total Shots": 15, "Shots on Goal": 6, "Blocked Shots": 3,
        "Dangerous Attacks": 48, "Corner Kicks": 7, "Ball Possession": "58%",
    }))
    assert parsed == {"shots": 15, "shots_on_target": 6, "blocked_shots": 3,
                      "dangerous_attacks": 48, "corners": 7}


def test_missing_stat_is_none_not_zero():
    # the usual case for dangerous attacks: the provider simply doesn't cover it
    parsed = parse_team_stats(stats(**{"Total Shots": 9, "Corner Kicks": 4}))
    assert parsed["dangerous_attacks"] is None
    assert parsed["blocked_shots"] is None
    assert parsed["shots"] == 9


def test_a_reported_zero_survives_as_zero():
    parsed = parse_team_stats(stats(**{"Blocked Shots": 0, "Corner Kicks": 0}))
    assert parsed["blocked_shots"] == 0 and parsed["corners"] == 0


def test_type_labels_are_matched_loosely():
    # same stats under the provider's alternate labels/casing
    parsed = parse_team_stats(stats(**{
        "shots_on_target": 4, "SHOTS BLOCKED": 2, "attacks dangerous": 31, "corner kicks": 5,
    }))
    assert parsed["shots_on_target"] == 4
    assert parsed["blocked_shots"] == 2
    assert parsed["dangerous_attacks"] == 31


def test_null_value_falls_through_to_the_next_alias():
    parsed = parse_team_stats([{"type": "Shots on Goal", "value": None},
                               {"type": "Shots on Target", "value": 5}])
    assert parsed["shots_on_target"] == 5


def test_empty_statistics_block():
    assert parse_team_stats([]) == {"shots": None, "shots_on_target": None, "blocked_shots": None,
                                    "dangerous_attacks": None, "corners": None}


# --- per-match sample ---
def test_sample_carries_both_sides():
    own = {"shots": 12, "shots_on_target": 5, "blocked_shots": 2, "dangerous_attacks": 40}
    opp = {"shots": 8, "shots_on_target": 2, "blocked_shots": 1, "dangerous_attacks": 25}
    s = _feature_sample(own, opp)
    assert s["blocked_shots_for"] == 2 and s["blocked_shots_against"] == 1
    assert s["dangerous_attacks_for"] == 40 and s["dangerous_attacks_against"] == 25


def test_shots_stay_ints_but_new_features_keep_none():
    # the live v2 lambda already consumes shots_for and must never see None
    blank = {f: None for f in ("shots", "shots_on_target", "blocked_shots", "dangerous_attacks")}
    s = _feature_sample(blank, blank)
    assert s["shots_for"] == 0 and s["shots_against"] == 0
    assert s["blocked_shots_for"] is None and s["dangerous_attacks_for"] is None


# --- aggregation ---
def match(home=True, **feats):
    base = {"home": home, "corners_for": 5, "corners_against": 5}
    base.update(feats)
    return base


def test_features_average_only_the_covered_games():
    matches = [
        match(blocked_shots_for=2, blocked_shots_against=1, dangerous_attacks_for=40),
        match(blocked_shots_for=4, blocked_shots_against=3),          # no dangerous attacks
        match(),                                                       # nothing covered
    ]
    f = team_features(matches)
    assert f["played"] == 3
    assert f["blocked_shots_for"] == 3.0          # (2+4)/2, the blank is not a zero
    assert f["dangerous_attacks_for"] == 40.0
    assert f["covered"]["blocked_shots"] == 2
    assert f["covered"]["dangerous_attacks"] == 1


def test_uncovered_feature_is_none_with_zero_coverage():
    f = team_features([match(), match()])
    for name in SHOT_FEATURES:
        assert f[f"{name}_for"] is None and f[f"{name}_against"] is None
        assert f["covered"][name] == 0


def test_features_respect_venue_and_window():
    matches = [match(home=True, blocked_shots_for=2), match(home=False, blocked_shots_for=8),
               match(home=True, blocked_shots_for=4)]
    assert team_features(matches, "home")["blocked_shots_for"] == 3.0
    assert team_features(matches, "away")["blocked_shots_for"] == 8.0
    assert team_features(matches, "overall", 1)["blocked_shots_for"] == 4.0
    assert team_features(matches, "home", 1)["played"] == 1
