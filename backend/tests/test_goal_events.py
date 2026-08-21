"""Unit tests for goal parsing and the match-state timeline.

The timeline is the part worth testing hard: it is the input to any future chase
measure, and an off-by-one in the segment maths would quietly bias every team."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from goal_events import (  # noqa: E402
    first_goal_minute, goal_summary, match_state_minutes, parse_goal_events, team_goal_sample,
)

HOME, AWAY = 101, 202


def ev(minute, team_id, detail="Normal Goal", player="P", type_="Goal", extra=None):
    return {"time": {"elapsed": minute, "extra": extra}, "team": {"id": team_id},
            "player": {"name": player}, "assist": {"name": None},
            "type": type_, "detail": detail}


def goals(*pairs):
    """(minute, side) -> the parsed shape the timeline consumes."""
    return [{"minute": m, "extra": 0, "side": s, "player": "P", "assist": None,
             "kind": "Normal Goal", "own_goal": False} for m, s in pairs]


# --- parsing ---
def test_parses_goals_and_ignores_other_events():
    events = [ev(10, HOME), {"type": "Card", "detail": "Yellow Card", "team": {"id": HOME},
                             "time": {"elapsed": 20}},
              ev(70, AWAY), {"type": "subst", "team": {"id": AWAY}, "time": {"elapsed": 60}}]
    g = parse_goal_events(events, HOME, AWAY)
    assert [(x["minute"], x["side"]) for x in g] == [(10, "home"), (70, "away")]


def test_missed_penalty_is_not_a_goal():
    """API-Football files these under type Goal — counting them would invent scorelines."""
    g = parse_goal_events([ev(30, HOME, detail="Missed Penalty")], HOME, AWAY)
    assert g == []


def test_own_goal_credits_the_side_that_benefits():
    g = parse_goal_events([ev(30, HOME, detail="Own Goal", player="Defender")], HOME, AWAY)
    assert len(g) == 1
    assert g[0]["side"] == "away"          # scoreline moves for the away team
    assert g[0]["player"] == "Defender"    # but the name is still the player who scored
    assert g[0]["own_goal"] is True


def test_goals_are_sorted_and_stoppage_time_orders_last():
    g = parse_goal_events([ev(90, AWAY, extra=4), ev(90, HOME), ev(12, AWAY)], HOME, AWAY)
    assert [(x["minute"], x["extra"]) for x in g] == [(12, 0), (90, 0), (90, 4)]


def test_event_with_no_minute_is_skipped():
    assert parse_goal_events([ev(None, HOME)], HOME, AWAY) == []


# --- timeline ---
def test_goalless_match_is_ninety_minutes_level():
    m = match_state_minutes([])
    assert m["home"] == {"leading": 0, "level": 90, "trailing": 0}
    assert m["away"] == {"leading": 0, "level": 90, "trailing": 0}


def test_single_goal_splits_the_match():
    m = match_state_minutes(goals((30, "home")))
    assert m["home"] == {"leading": 60, "level": 30, "trailing": 0}
    assert m["away"] == {"leading": 0, "level": 30, "trailing": 60}


def test_the_two_sides_always_mirror_each_other():
    m = match_state_minutes(goals((10, "away"), (55, "home"), (80, "home")))
    assert m["home"]["trailing"] == m["away"]["leading"]
    assert m["home"]["leading"] == m["away"]["trailing"]
    assert m["home"]["level"] == m["away"]["level"]
    for side in ("home", "away"):
        assert sum(m[side].values()) == 90


def test_equaliser_returns_the_match_to_level():
    m = match_state_minutes(goals((20, "away"), (60, "home")))
    assert m["home"] == {"leading": 0, "level": 50, "trailing": 40}   # 0-20 and 60-90 level


def test_stoppage_time_goal_does_not_invent_minutes():
    """A 90+3 winner must not add minutes beyond full time."""
    m = match_state_minutes(goals((30, "away"), (90, "home"), (90, "home")))
    assert sum(m["home"].values()) == 90
    assert m["home"]["trailing"] == 60          # behind from 30 to 90


def test_a_team_chasing_all_game_is_visible():
    """The measure that matters: 1-0 down early is not the same as conceding on 43."""
    early = match_state_minutes(goals((5, "away")))["home"]["trailing"]
    late = match_state_minutes(goals((43, "away")))["home"]["trailing"]
    assert early == 85 and late == 47


def test_first_goal_minute():
    g = goals((22, "away"), (44, "home"), (70, "home"))
    assert first_goal_minute(g, "home") == 44
    assert first_goal_minute(g, "away") == 22
    assert first_goal_minute([], "home") is None


# --- per-team sample ---
def test_team_sample_shape():
    s = goal_summary(goals((15, "away"), (60, "home")))
    home = team_goal_sample(s, "home")
    assert home["minutes_trailing"] == 45 and home["minutes_level"] == 45
    assert home["first_goal_min"] == 60 and home["opp_first_goal_min"] == 15
    assert home["scored_first"] is False
    assert [x["minute"] for x in home["scorers"]] == [60]
    away = team_goal_sample(s, "away")
    assert away["scored_first"] is True
    assert away["minutes_leading"] == 45


def test_goalless_sample_has_no_first_scorer():
    s = goal_summary([])
    for side in ("home", "away"):
        t = team_goal_sample(s, side)
        assert t["scored_first"] is None      # nobody scored — not False
        assert t["minutes_level"] == 90 and t["scorers"] == []


# --- the per-team aggregate the API serves ---
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
from server import goal_profile  # noqa: E402


def match(home=True, trailing=None, scorers=(), first=None, opp_first=None, first_side=None):
    m = {"date": "2025-01-01", "home": home, "corners_for": 5, "corners_against": 5}
    if trailing is not None:
        m.update({"minutes_trailing": trailing, "minutes_level": 90 - trailing,
                  "minutes_leading": 0, "first_goal_min": first,
                  "opp_first_goal_min": opp_first,
                  "scored_first": None if first_side is None else (first_side == "us"),
                  "scorers": [{"minute": mi, "player": p, "kind": "Normal Goal"}
                              for mi, p in scorers]})
    return m


def test_uncovered_matches_are_reported_as_uncovered_not_as_zero():
    """A team the backfill has not reached must not read as 'never trails'."""
    p = goal_profile([match(), match()])
    assert p["games"] == 0 and p["played"] == 2
    assert p["minutes"] == {} and p["scorers"] == []


def test_games_counts_covered_matches_only():
    p = goal_profile([match(), match(trailing=30, scorers=[(60, "A")])])
    assert (p["games"], p["played"]) == (1, 2)


def test_scorers_are_tallied_and_ranked():
    p = goal_profile([match(trailing=0, scorers=[(10, "A"), (70, "B")]),
                      match(trailing=0, scorers=[(20, "A")])])
    assert [(s["player"], s["goals"]) for s in p["scorers"]] == [("A", 2), ("B", 1)]
    assert p["scorers"][0]["minutes"] == [10, 20]


def test_goal_windows_bucket_by_minute_and_keep_stoppage_time_in_the_last_one():
    p = goal_profile([match(trailing=0, scorers=[(3, "A"), (47, "B"), (90, "C"), (95, "D")])])
    assert p["windows"]["1-15"] == 1 and p["windows"]["46-60"] == 1
    assert p["windows"]["76-90"] == 2          # 90 and 90+5 both land here


def test_minutes_trailing_is_averaged_over_covered_games():
    p = goal_profile([match(trailing=60), match(trailing=0)])
    assert p["minutes"]["trailing"] == 30.0 and p["minutes"]["level"] == 60.0


def test_first_goal_summary():
    p = goal_profile([match(trailing=0, first=20, opp_first=None, first_side="us"),
                      match(trailing=40, first=None, opp_first=50, first_side="them")])
    assert p["first_goal"]["scored_first_pct"] == 50.0
    assert p["first_goal"]["avg_first_scored_min"] == 20.0
    assert p["first_goal"]["avg_first_conceded_min"] == 50.0


def test_split_filters_by_venue():
    ms = [match(home=True, trailing=90), match(home=False, trailing=0)]
    assert goal_profile(ms, "home")["minutes"]["trailing"] == 90.0
    assert goal_profile(ms, "away")["minutes"]["trailing"] == 0.0
