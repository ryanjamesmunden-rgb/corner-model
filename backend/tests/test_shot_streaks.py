"""Shots as a streak subject, on the same run machinery as corners.

WHY SHOTS AND NOT THE OTHER SHOT STATS. measure_features, run 11 November over 20,664
team-sides: total shots are 99.7% covered at a league average of 13.17 a side, while
shots on target and blocked shots sit at 69.9% and 69.8%. A run filter needs the stat in
EVERY game of its window, so a third of them missing turns "5 of the last 5" into a
question the data cannot answer. Shots also correlate with corners harder than either
(r=+0.221 against +0.182), which is why they are already an input to the production
lambda.

THE ONE HAZARD IS THAT ZERO MEANS MISSING. sync_real's _match_features coerces shots with
`mine or 0`, deliberately, because the live lambda consumes them and must not start seeing
None. So a game the provider filed no shots for is stored as 0 rather than as absent, and
a team does not take zero shots in a professional match. Read literally, every over run
would break on a coverage gap and every under run would collect a free win.
"""
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(HERE, "server.py")) as fh:
        return fh.read()


# server.py cannot be imported in this container — pymongo pulls in cryptography, which
# panics — so the pure run helpers are exercised through source slices, as
# test_value_snapshot and test_played_fixtures do. Two slices because the ladder registry
# sits several hundred lines above the functions that read it.
def _load():
    src = _src()
    ns = {"Optional": Optional, "List": List, "Dict": Dict,
          "WIN": "win", "VOID": "void", "LOSS": "loss"}
    ladders = src[src.index("STREAK_LADDERS = {"):src.index("MIN_STREAK_LEN = ")]
    exec(compile(ladders, "sliced:ladders", "exec"), ns)
    body = src[src.index("UNDER_LINE_CAP = {"):src.index("def live_streak_candidates(")]
    exec(compile(body, "sliced:streaks", "exec"), ns)
    return ns


NS = _load()
streak_value = NS["streak_value"]
settle = NS["settle_streak_leg"]
label = NS["streak_line_label"]
legs_of = NS["streak_legs"]
runs_of = NS["streak_runs"]
SHOT_KEYS = NS["STREAK_SHOT_KEYS"]
LADDERS = NS["STREAK_LADDERS"]
CAP = NS["UNDER_LINE_CAP"]
FLOOR = NS["OVER_LINE_FLOOR"]


def game(sf=14, sa=11, cf=6, ca=4, home=True, date="2026-11-01"):
    return {"home": home, "date": date, "corners_for": cf, "corners_against": ca,
            "shots_for": sf, "shots_against": sa}


# --- which number a shot subject measures ----------------------------------------------

def test_team_shots_reads_the_sides_own_shots():
    assert streak_value(game(sf=14), "shots") == 14


def test_shots_conceded_reads_the_shots_faced():
    assert streak_value(game(sa=11), "shots_conceded") == 11


def test_match_shots_is_both_sides_added():
    assert streak_value(game(sf=14, sa=11), "shots_match") == 25


def test_the_corner_subjects_are_untouched():
    """The whole point of adding a subject rather than a parameter is that nothing about
    the existing board moves."""
    g = game(cf=6, ca=4)
    assert streak_value(g, "team") == 6
    assert streak_value(g, "conceded") == 4
    assert streak_value(g, "match") == 10


# --- zero means missing, and that is the crux ------------------------------------------

def test_a_zero_shot_count_is_not_a_zero():
    """A team does not take zero shots in a professional match, and coverage is 99.7%, so
    a 0 here is _match_features' `mine or 0` standing in for absent data."""
    assert streak_value(game(sf=0), "shots") is None
    assert streak_value(game(sa=0), "shots_conceded") is None


def test_a_match_total_needs_both_sides_covered():
    """One side covered and the other absent totals to roughly half the shots in the game
    and reads as a real, quiet match — a plausible wrong number, which is worse than
    none."""
    assert streak_value(game(sf=14, sa=0), "shots_match") is None
    assert streak_value(game(sf=0, sa=11), "shots_match") is None


def test_a_missing_key_is_not_a_zero_either():
    g = game()
    del g["shots_for"]
    assert streak_value(g, "shots") is None


def test_a_boolean_is_refused():
    """isinstance(True, int) is True, so a bool would sail in as one shot."""
    assert streak_value(game(sf=True), "shots") is None


def test_a_genuine_zero_corner_count_still_counts():
    """The conflation is deliberate for shots and WRONG for corners: 0 corners happens and
    is a real result, so nothing here may make a corner subject nullable."""
    assert streak_value(game(cf=0), "team") == 0
    assert streak_value(game(cf=0, ca=0), "match") == 0


# --- an uncovered game voids, it does not break the run --------------------------------

def test_an_unknown_value_voids():
    assert settle(None, 12, "over") == "void"
    assert settle(None, 12, "under") == "void"


def test_a_run_reads_through_a_coverage_gap():
    """THE REASON None IS A VOID. streak_runs already skips voids, so one game the
    provider filed no shots for leaves the run intact. Scoring it a loss would end runs on
    a gap in somebody else's data; scoring it a win would invent them."""
    ms = [game(sf=14), game(sf=15), game(sf=0), game(sf=16), game(sf=14)]
    legs = legs_of(ms, 12, "over", "shots")
    assert [lg["result"] for lg in legs] == ["win", "win", "void", "win", "win"]
    cur = runs_of(legs)["current"]
    assert cur["length"] == 4 and cur["status"] == "active"
    assert cur["voids"] == 1


def test_a_line_carried_only_by_gaps_is_not_a_run():
    """Voids count towards the window but cannot be the whole of it — the existing
    `wins >= 1` rule, which matters far more now that gaps are possible."""
    legs = legs_of([game(sf=0), game(sf=0)], 12, "over", "shots")
    assert [lg["result"] for lg in legs] == ["void", "void"]
    assert runs_of(legs)["current"]["length"] == 0


def test_the_leg_reports_the_value_as_unknown_rather_than_zero():
    legs = legs_of([game(sf=0)], 12, "over", "shots")
    assert legs[0]["value"] is None


# --- the chip has to say what it is measuring ------------------------------------------

def test_a_shots_chip_names_its_unit():
    """"13+" beside a team reads as corners everywhere else on this site, and 13 is an
    ordinary corner line for a match total — so an unmarked shots chip is the same two
    characters meaning a different bet. Same hazard the `conc` prefix solves."""
    assert label(13, "over", "shots") == "13+ shots"
    assert label(10, "under", "shots_conceded") == "under 10 shots"
    assert label(26, "over", "shots_match") == "26+ shots"


def test_a_corner_chip_is_unchanged():
    assert label(5, "over") == "5+"
    assert label(5, "over", "team") == "5+"
    assert label(8, "under", "match") == "under 8"


# --- the ladders are on the shots scale, not the corner one ----------------------------

def test_every_shot_subject_has_a_ladder_a_floor_and_a_cap():
    """The endpoint whitelists on STREAK_LADDERS and then reads OVER_LINE_FLOOR and
    UNDER_LINE_CAP by subject. A subject in one and missing from the others would fall
    back to the CORNER numbers and offer a 3+ shots run."""
    for s in SHOT_KEYS:
        assert s in LADDERS, s
        assert s in CAP, s
        assert s in FLOOR, s


def test_the_over_floor_is_near_the_measured_average():
    """13.17 shots a side measured, so an over below about 9 describes the sport rather
    than the team — the same reasoning that puts the corner floor at 3 against ~5."""
    assert FLOOR["shots"] == 9 and FLOOR["shots_conceded"] == 9
    assert FLOOR["shots_match"] == 20


def test_the_shot_ladders_reach_higher_than_the_corner_ones():
    assert max(LADDERS["shots"]) > max(LADDERS["team"])
    assert max(LADDERS["shots_match"]) > max(LADDERS["match"])


# --- a shots run is not priced ---------------------------------------------------------

def test_the_projection_refuses_a_shot_subject():
    """Everything in _streak_projection is corners: _real_avg reads corners_for,
    live_lambda is the corner lambda, and the book price is looked up under a corner
    market key. Handed a shots line of 13 it would return a confident fair price for
    "13+ corners" and an EV against a corner quote. Asserted on the source because the
    function needs a database and a model; the guard is one line and must stay first."""
    src = _src()
    fn = src[src.index("def _streak_projection("):]
    fn = fn[:fn.index('t_for = _real_avg(team, team_venue, "corners_for")')]
    assert "if subject in STREAK_SHOT_KEYS:" in fn
    assert "return None" in fn


def test_shots_are_not_added_to_the_browse_board():
    """BROWSE_SUBJECTS drives the front door's streak filter, whose margin test compares a
    run against the division's average CORNERS. A shots subject there would be measured
    against a corner par — a comparison between two different units."""
    src = _src()
    line = next(l for l in src.splitlines() if l.startswith("BROWSE_SUBJECTS = "))
    for s in SHOT_KEYS:
        assert s not in line, f"{s} must not reach the browse margin test"
