"""Promoted / relegated / new-to-league sides, from last season's squad lists."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import league_change  # noqa: E402

LEAGUES = [
    {"league_id": "eng-pl", "name": "Premier League", "country": "England", "tier": 1,
     "prev_season_team_ids": [1, 2, 3]},
    {"league_id": "eng-ch", "name": "Championship", "country": "England", "tier": 2,
     "prev_season_team_ids": [4, 5, 6]},
    {"league_id": "eng-l1", "name": "League One", "country": "England", "tier": 3,
     "prev_season_team_ids": [7, 8]},
    {"league_id": "nor-el", "name": "Eliteserien", "country": "Norway", "tier": 1,
     "prev_season_team_ids": [5]},
]


def team(tid, league, api, new=True):
    return {"team_id": tid, "league_id": league, "api_team_id": api, "new_to_league": new}


def test_direction_comes_from_the_league_they_were_in():
    m = league_change.change_map([
        team("pl-4", "eng-pl", 4),     # was in the Championship -> promoted
        team("ch-3", "eng-ch", 3),     # was in the Premier League -> relegated
        team("ch-7", "eng-ch", 7),     # was in League One -> promoted
        team("pl-1", "eng-pl", 1, new=False),
    ], LEAGUES)
    assert m["pl-4"]["status"] == "promoted" and m["pl-4"]["from_league"] == "Championship"
    assert m["ch-3"]["status"] == "relegated"
    assert m["ch-7"]["status"] == "promoted"
    assert "pl-1" not in m


def test_another_country_is_not_where_they_came_from():
    # api id 5 is in Norway's list too; only England's counts for an English side.
    m = league_change.change_map([team("pl-5", "eng-pl", 5)], LEAGUES)
    assert m["pl-5"]["from_league"] == "Championship"


def test_unknown_origin():
    m = league_change.change_map([team("pl-99", "eng-pl", 99), team("l1-99", "eng-l1", 98)], LEAGUES)
    assert m["pl-99"]["status"] == "promoted"     # nothing above a top flight
    assert m["l1-99"]["status"] == "new"


def test_annotate_marks_both_sides_of_a_fixture():
    changes = {"a": {"status": "promoted", "label": "newly promoted"}}
    rows = [{"team_id": "a", "name": "A", "next_fixture": {"opponent_team_id": "b", "opponent": "B"}},
            {"team_id": "b", "name": "B", "next_fixture": {"opponent_team_id": "a", "opponent": "A"}},
            {"team_id": "c", "next_fixture": {"opponent_team_id": "d"}}]
    league_change.annotate(rows, changes)
    assert rows[0]["league_change"]["status"] == "promoted"
    assert rows[1]["opponent_league_change"]["status"] == "promoted"
    assert "league_change" not in rows[2] and "opponent_league_change" not in rows[2]
    assert league_change.describe(rows[1]) == "A newly promoted"
