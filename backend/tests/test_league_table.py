"""The league table rebuilt from fixture_stats.

WHAT THIS PINS. The order (points, then goal difference, then goals scored), that an
unscored game is skipped rather than counted as a 0-0, that a doubled document is counted
once, and that a side with no game on file gets no position at all rather than a made-up
one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import league_table  # noqa: E402


def g(fid, h, a, hg, ag):
    return {"_id": fid, "home_id": h, "away_id": a, "home_goals": hg, "away_goals": ag}


def test_points_then_goal_difference_then_goals():
    docs = [g(1, 10, 20, 2, 0),   # 10 win
            g(2, 30, 40, 1, 0),   # 30 win
            g(3, 20, 30, 1, 1),   # draw
            g(4, 40, 10, 3, 3)]   # draw
    t = league_table.build_table(docs)
    assert [r["team_id"] for r in t] == [10, 30, 40, 20]  # 40 and 20 level on points; 40 better on GD
    top = t[0]
    assert (top["played"], top["won"], top["drawn"], top["lost"]) == (2, 1, 1, 0)
    assert (top["gf"], top["ga"], top["gd"], top["points"], top["position"]) == (5, 3, 2, 4, 1)


def test_unscored_games_are_skipped_not_counted_as_draws():
    t = league_table.build_table([g(1, 10, 20, None, None), g(2, 10, 20, 1, 0)])
    row = league_table.position_of(t, 20)
    assert row["played"] == 1 and row["drawn"] == 0 and row["lost"] == 1


def test_the_same_fixture_twice_counts_once():
    t = league_table.build_table([g(1, 10, 20, 1, 0), g(1, 10, 20, 1, 0)])
    assert league_table.position_of(t, 10)["played"] == 1


def test_position_carries_the_table_size():
    t = league_table.build_table([g(1, 10, 20, 0, 1), g(2, 30, 40, 0, 0)])
    row = league_table.position_of(t, 20)
    assert row["position"] == 1 and row["of"] == 4


def test_a_side_not_on_file_has_no_position():
    t = league_table.build_table([g(1, 10, 20, 1, 0)])
    assert league_table.position_of(t, 99) is None
    assert league_table.position_of(t, None) is None
    assert league_table.position_of([], 10) is None
