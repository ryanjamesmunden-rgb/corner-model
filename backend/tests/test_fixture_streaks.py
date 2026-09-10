"""Streaks running INTO a fixture.

The streak board answers "which teams are on a run". This answers the other half —
"what is running into this game" — and it is what the fixture share posts. So what is
pinned here is that it describes the run it claims to: the right games, the right
direction, and nothing dressed up as a streak that is not one.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import live_streak, fixture_streaks, MIN_STREAK_LEN  # noqa: E402


def m(home, cf, ca, date):
    return {"home": home, "corners_for": cf, "corners_against": ca,
            "opponent": "X", "date": date}


def team(name, matches):
    return {"name": name, "team_id": "t-" + name, "real_matches": matches}


HOME_RUN = team("Derby", [
    m(True, 7, 3, "2026-08-01"),
    m(False, 2, 6, "2026-08-05"),      # an AWAY blank that must not break the home run
    m(True, 8, 4, "2026-08-10"),
    m(True, 6, 5, "2026-08-17"),
    m(True, 9, 2, "2026-08-24"),
])


def test_the_run_is_counted_on_the_venue_being_played():
    """"9 in a row" over a team's home games is a claim about its home games. Mixing the
    aways in would quietly describe a different streak from the one the board shows."""
    r = live_streak(HOME_RUN, "home", "team", "over")
    assert r["run"] == 4 and r["venue"] == "home"
    # The 2-corner away game sits in the middle of those four and is correctly ignored.
    assert live_streak(HOME_RUN, "away", "team", "over") is None


def test_it_keeps_the_most_demanding_line_at_the_same_run_length():
    """4 home games of 7, 8, 6, 9 all clear 3+ as well as 6+. Reporting 3+ would be true
    and worthless — the strongest true claim is the one worth posting."""
    assert live_streak(HOME_RUN, "home", "team", "over")["line"] == 6


def test_a_match_total_reads_both_teams_corners():
    r = live_streak(HOME_RUN, "home", "match", "over")
    assert r["subject"] == "match"
    assert r["line"] == 10          # totals were 10, 12, 11, 11


def test_a_broken_run_is_not_reported():
    """The current run has to be ALIVE. A team that cleared the line four times and then
    missed last week is not carrying anything into this game."""
    broken = team("X", [m(True, 8, 3, "2026-08-01"), m(True, 8, 3, "2026-08-08"),
                        m(True, 1, 3, "2026-08-15")])
    assert live_streak(broken, "home", "team", "over") is None


def test_a_single_game_is_not_a_streak():
    one = team("X", [m(True, 9, 3, "2026-08-01")])
    assert live_streak(one, "home", "team", "over") is None
    assert MIN_STREAK_LEN >= 2


def test_an_under_is_labelled_as_an_under():
    """A run of quiet games is the same kind of story as a run of busy ones, and posting
    it as an over would be a public, wrong claim about what is being suggested."""
    quiet = team("Y", [m(True, 1, 2, "2026-08-01"), m(True, 2, 1, "2026-08-08"),
                       m(True, 0, 2, "2026-08-15")])
    r = live_streak(quiet, "home", "team", "under")
    assert r["direction"] == "under"
    assert r["line_label"].startswith("under ")


def test_a_fixture_lists_both_sides_best_first():
    rows = fixture_streaks(HOME_RUN, HOME_RUN, "Derby", "West Brom")
    assert rows, "a fixture with live runs on both sides should return rows"
    assert [r["run"] for r in rows] == sorted([r["run"] for r in rows], reverse=True)
    # Trimming a share to fit drops the tail, so the tail has to be the weakest.
    assert {r["team"] for r in rows} <= {"Derby", "West Brom"}


def test_a_fixture_with_no_history_returns_nothing_rather_than_inventing_a_run():
    empty = team("New", [])
    assert fixture_streaks(empty, empty, "A", "B") == []


def test_a_line_too_low_to_mean_anything_is_never_suggested():
    """Every side clears "1+ corners" most weeks. A run at the bottom of the ladder is
    technically true and reads as a joke, so the same floor the streak board uses applies
    here — this test is what caught it being missing."""
    from server import OVER_LINE_FLOOR
    broken = team("X", [m(True, 8, 3, "2026-08-01"), m(True, 8, 3, "2026-08-08"),
                        m(True, 1, 3, "2026-08-15")])
    r = live_streak(broken, "home", "team", "over")
    assert r is None, f"suggested {r and r['line_label']} — below the floor"
    assert OVER_LINE_FLOOR["team"] >= 3


def test_an_under_too_loose_to_mean_anything_is_never_suggested():
    """The mirror: "under 15 corners" lands nearly every week for everyone."""
    from server import UNDER_LINE_CAP
    quiet = team("Y", [m(True, 1, 2, "2026-08-01"), m(True, 2, 1, "2026-08-08")])
    r = live_streak(quiet, "home", "team", "under")
    assert r is None or r["line"] <= UNDER_LINE_CAP["team"]
