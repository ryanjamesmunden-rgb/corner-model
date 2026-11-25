"""A cup tie's page should be able to show the competition's own games.

Open Inter v VfB Stuttgart in the Champions League and every game listed is Serie A,
because a cup has no teams of its own and the fixture points at the domestic rows. The
European results were in db.fixtures_played all along, keyed by the same team ids.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cup_form  # noqa: E402


def tie(fid, home_id, away_id, hc, ac, date, *, home_name="Inter", away_name="Feyenoord",
        hg=1, ag=0, known=True, finished="FT", rnd="League Stage - 4"):
    return {"fixture_id": fid, "league_id": "ucl", "round": rnd,
            "home_team_id": home_id, "away_team_id": away_id,
            "home_name": home_name, "away_name": away_name, "date": date,
            "home_corners": hc, "away_corners": ac,
            "total_corners": None if hc is None or ac is None else hc + ac,
            "home_goals": hg, "away_goals": ag,
            "corners_known": known, "finished_as": finished}


INTER = "ita-sa-505"
FEYE = "ned-ed-197"


# --- one side's games ----------------------------------------------------------------

def test_a_team_at_either_end_of_the_tie_is_found():
    played = [tie("a", INTER, FEYE, 7, 3, "2026-11-03T20:00:00Z"),
              tie("b", FEYE, INTER, 5, 4, "2026-10-21T20:00:00Z",
                  home_name="Feyenoord", away_name="Inter")]
    assert [g["fixture_id"] for g in cup_form.games_for(INTER, played)] == ["a", "b"]


def test_won_is_this_team_s_corners_whichever_end_it_was_at():
    # THE BUG THIS PREVENTS is the one the whole file exists to avoid: reading the home
    # column for an away side turns a good night into a bad one.
    played = [tie("b", FEYE, INTER, 5, 4, "2026-10-21T20:00:00Z",
                  home_name="Feyenoord", away_name="Inter")]
    got = cup_form.games_for(INTER, played)[0]
    assert got["won"] == 4 and got["conceded"] == 5
    assert got["home"] is False
    assert got["opponent"] == "Feyenoord"


def test_the_opponent_is_the_other_side_s_name():
    played = [tie("a", INTER, FEYE, 7, 3, "2026-11-03T20:00:00Z")]
    assert cup_form.games_for(INTER, played)[0]["opponent"] == "Feyenoord"


def test_newest_first_whatever_order_the_store_returned():
    played = [tie("old", INTER, FEYE, 2, 2, "2026-09-16T20:00:00Z"),
              tie("new", INTER, FEYE, 7, 3, "2026-11-03T20:00:00Z")]
    assert [g["fixture_id"] for g in cup_form.games_for(INTER, played)] == ["new", "old"]


def test_a_tie_nobody_fetched_the_corners_for_is_left_out():
    # corners_known False means no statistics call has been made, not nil-nil. On a list
    # this short one phantom zero moves the average more than any real game on it.
    played = [tie("x", INTER, FEYE, None, None, "2026-11-03T20:00:00Z", known=False),
              tie("y", INTER, FEYE, 6, 2, "2026-10-21T20:00:00Z")]
    assert [g["fixture_id"] for g in cup_form.games_for(INTER, played)] == ["y"]


def test_a_tie_flagged_known_but_missing_a_count_is_still_left_out():
    # Belt and braces: the flag and the numbers are written together, so if they ever
    # disagree the numbers win.
    played = [tie("x", INTER, FEYE, 6, None, "2026-11-03T20:00:00Z", known=True)]
    assert cup_form.games_for(INTER, played) == []


def test_a_goalless_corner_count_is_kept():
    # Zero corners is a real result and the easiest thing here to lose to a falsy check.
    played = [tie("a", INTER, FEYE, 0, 4, "2026-11-03T20:00:00Z")]
    got = cup_form.games_for(INTER, played)
    assert len(got) == 1 and got[0]["won"] == 0


def test_games_this_team_did_not_play_in_are_ignored():
    played = [tie("other", "eng-pl-42", "ger-bl-165", 9, 1, "2026-11-24T20:00:00Z")]
    assert cup_form.games_for(INTER, played) == []


def test_the_list_is_capped():
    played = [tie(str(i), INTER, FEYE, i, 1, f"2026-1{i % 2}-0{i % 9 + 1}T20:00:00Z")
              for i in range(12)]
    assert len(cup_form.games_for(INTER, played, limit=4)) == 4


def test_extra_time_rides_along_because_it_is_thirty_more_minutes_of_corners():
    played = [tie("a", INTER, FEYE, 11, 4, "2026-11-03T20:00:00Z", finished="AET")]
    assert cup_form.games_for(INTER, played)[0]["finished_as"] == "AET"


# --- the totals ----------------------------------------------------------------------

def test_the_summary_carries_its_denominator_and_its_range():
    played = [tie("a", INTER, FEYE, 7, 3, "2026-11-03T20:00:00Z"),
              tie("b", FEYE, INTER, 5, 3, "2026-10-21T20:00:00Z"),
              tie("c", INTER, FEYE, 2, 6, "2026-09-16T20:00:00Z")]
    s = cup_form.summarise(cup_form.games_for(INTER, played))
    # Inter won 7, 3 and 2 — the middle game is from the away column.
    assert s["games"] == 3
    assert s["avg_won"] == 4.0
    assert s["low"] == 2 and s["high"] == 7
    assert s["avg_conceded"] == round((3 + 5 + 6) / 3, 2)


def test_no_games_is_none_rather_than_a_row_of_zeroes():
    # "No game we hold a count for" and "averages nothing" are different statements.
    assert cup_form.summarise([]) is None


# --- the fixture ---------------------------------------------------------------------

def fixture(**over):
    base = {"fixture_id": "ucl-1", "league_id": "ucl", "cup": True,
            "home_team_id": INTER, "away_team_id": FEYE}
    return {**base, **over}


def test_both_sides_come_back_keyed_by_slot():
    played = [tie("a", INTER, FEYE, 7, 3, "2026-11-03T20:00:00Z")]
    out = cup_form.for_fixture(fixture(), played)
    assert out["home"]["summary"]["games"] == 1
    assert out["away"]["summary"]["games"] == 1
    assert out["home"]["games"][0]["won"] == 7
    assert out["away"]["games"][0]["won"] == 3


def test_a_side_with_no_games_in_the_competition_is_none_not_an_empty_shell():
    # An empty panel reads as "they have played none"; None lets the page say nothing.
    played = [tie("a", INTER, "other", 7, 3, "2026-11-03T20:00:00Z")]
    out = cup_form.for_fixture(fixture(), played)
    assert out["home"] is not None and out["away"] is None


def test_a_league_fixture_is_left_alone():
    # The domestic page already shows domestic games; there is nothing to add.
    out = cup_form.for_fixture(fixture(cup=False), [tie("a", INTER, FEYE, 7, 3, "x")])
    assert out == {"home": None, "away": None}
    assert cup_form.for_fixture(None, []) == {"home": None, "away": None}


def test_nothing_played_yet_is_two_nones():
    assert cup_form.for_fixture(fixture(), []) == {"home": None, "away": None}
