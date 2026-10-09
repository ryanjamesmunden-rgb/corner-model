"""The chase-angle screen: a corner side that leaks goals, against a solid winner.

WHAT THIS PINS. Five legs have to agree, and the ones worth testing are the ones that
are easy to get subtly wrong rather than the ones that are a comparison:

  - the corner bars are LEAGUE-RELATIVE, so the same side passes in one division and
    fails in another. A fixed rung is the same rung for a side winning nine a game and
    a side winning three, and _browse_margin paid for that lesson twice.
  - every figure is the VENUE the sides are actually playing, not the season.
  - the opponent's win rate is over the games whose score was synced, not over all of
    them — an unsynced fixture is not a game they failed to win.
  - both sides of a fixture are tested, since the mechanism has nothing to do with
    which ground it is played on.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chase_angle as ca  # noqa: E402


def m(home, cf, ca_, gf, ga):
    return {"home": home, "corners_for": cf, "corners_against": ca_,
            "goals_for": gf, "goals_against": ga, "date": "2026-08-01"}


def side(name, league, rows):
    return {"team_id": name, "name": name, "league_id": league, "real_matches": rows}


# OUR SIDE: 9 corners a game at home in a division averaging 5, and ships two a game.
LEAKY = side("Leaky", "l", [m(True, 9, 6, 1, 2)] * 8 + [m(False, 5, 6, 1, 2)] * 8)
# THE OPPONENT: away, wins 5 of 8, concedes 0.5 a game, gives up 7 corners a game.
SOLID = side("Solid", "l", [m(False, 4, 7, 2, 0)] * 5 + [m(False, 3, 7, 0, 1)] * 3
                           + [m(True, 4, 7, 2, 0)] * 8)
# Filler so the division average is a real number: 5 for, 5 against.
FILLER = [side(f"Mid{i}", "l", [m(True, 5, 5, 1, 1), m(False, 5, 5, 1, 1)] * 5)
          for i in range(6)]
TEAMS = [LEAKY, SOLID] + FILLER
PARS = ca.league_pars(TEAMS)

FIXTURES = {"f1": {"_fixture": {"fixture_id": "f1", "home_team_id": "Leaky",
                                "away_team_id": "Solid"},
                   "date": "2026-10-11T15:00:00+00:00", "home": "Leaky", "away": "Solid",
                   "league_name": "Test", "lambda_home": 8.0, "lambda_away": 4.0}}


def scan(**kw):
    args = dict(corner_edge=ca.DEFAULT_CORNER_EDGE, min_leaking=ca.DEFAULT_MIN_LEAKING,
                min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                max_conceded=ca.DEFAULT_MAX_CONCEDED,
                opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE)
    args.update(kw)
    teams = {t["team_id"]: t for t in TEAMS}
    return ca.scan(FIXTURES, teams, PARS, **args)


class TestTheShapeIsFound:
    def test_the_fixture_that_fits_comes_back(self):
        rows = scan()
        assert [r["team"] for r in rows] == ["Leaky"]

    def test_and_it_is_our_side_being_backed_not_the_good_team(self):
        # The whole point: the row is about the side that is going to be losing.
        r = scan()[0]
        assert r["team"] == "Leaky" and r["opp"] == "Solid" and r["venue"] == "home"

    def test_the_numbers_on_it_are_the_venue_ones(self):
        # Leaky win 9 at home and 5 away; the season average is 7 and describes neither.
        r = scan()[0]
        assert r["my_corners"] == 9
        # Solid give up 7 corners away, and concede 3 goals over 8 away games.
        assert r["their_corners_against"] == 7
        assert r["their_goals_against"] == 0.375

    def test_the_goal_gap_is_printed_but_is_not_the_ordering(self):
        r = scan()[0]
        assert r["behind"] == r["my_leak"] - r["their_goals_against"] == 1.625
        assert r["edge"] == r["my_edge"] + r["their_edge"], "ranked on corners only"


class TestEachLegCanVetoIt:
    """Five legs, and the screen is only as good as the weakest one actually biting."""

    def test_a_side_without_the_corner_edge_is_out(self):
        assert scan(corner_edge=5.0) == []

    def test_a_side_that_does_not_leak_goals_is_out(self):
        # Leaky concede exactly 2.0 at home.
        assert scan(min_leaking=2.5) == []

    def test_an_opponent_that_does_not_win_is_out(self):
        # Solid win 5 of 8 away = 62.5%.
        assert scan(min_win_rate=0.7) == []

    def test_an_opponent_that_leaks_goals_itself_is_out(self):
        assert scan(max_conceded=0.25) == []

    def test_an_opponent_that_does_not_give_corners_up_is_out(self):
        # Solid give up 7 against a division average of 5, so +2.
        assert scan(opp_corner_edge=3.0) == []


class TestTheCornerBarsAreTheDivisionsNotAFixedRung:
    """A fixed rung is the same rung for a side winning nine a game and a side winning
    three. The same team must pass in a low-corner league and fail in a high one."""

    def test_the_same_side_fails_in_a_higher_corner_division(self):
        # Rebuild the division so the average is 9 instead of 5: our side's 9 a game is
        # now exactly par, and par is not an edge.
        busy = [side(f"Busy{i}", "l", [m(True, 9, 9, 1, 1), m(False, 9, 9, 1, 1)] * 5)
                for i in range(6)]
        pars = ca.league_pars([LEAKY, SOLID] + busy)
        teams = {t["team_id"]: t for t in [LEAKY, SOLID] + busy}
        rows = ca.scan(FIXTURES, teams, pars, corner_edge=ca.DEFAULT_CORNER_EDGE,
                       min_leaking=ca.DEFAULT_MIN_LEAKING,
                       min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                       max_conceded=ca.DEFAULT_MAX_CONCEDED,
                       opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE)
        assert rows == [], "nine a game is not an edge in a division that wins nine"

    def test_the_edge_is_reported_against_the_division_not_in_absolute_corners(self):
        r = scan()[0]
        assert r["my_edge"] == r["my_corners"] - PARS["l"]["for"]


class TestTheWinRateIsHonest:
    def test_it_is_over_the_games_whose_score_was_synced(self):
        # An unsynced fixture is not a game they failed to win — dividing by it would
        # punish the leagues our own goal backfill has not reached.
        rows = [m(False, 4, 7, 2, 0)] * 3 + [{"home": False, "corners_for": 4,
                                              "corners_against": 7, "date": "x"}] * 7
        rate, n = ca.win_rate(rows)
        assert (rate, n) == (1.0, 3)

    def test_no_scores_at_all_is_unknown_rather_than_zero(self):
        rate, n = ca.win_rate([{"home": False, "corners_for": 4, "date": "x"}])
        assert rate is None and n == 0

    def test_a_side_with_no_synced_scores_cannot_pass_the_screen(self):
        # None must not compare as "below the bar" or sail through as "above" it.
        blind = side("Blind", "l", [{"home": False, "corners_for": 7,
                                     "corners_against": 7, "date": "x"}] * 8)
        teams = {t["team_id"]: t for t in [LEAKY, blind] + FILLER}
        fx = {"f1": {**FIXTURES["f1"],
                     "_fixture": {"fixture_id": "f1", "home_team_id": "Leaky",
                                  "away_team_id": "Blind"}}}
        assert ca.scan(fx, teams, PARS, corner_edge=ca.DEFAULT_CORNER_EDGE,
                       min_leaking=ca.DEFAULT_MIN_LEAKING,
                       min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                       max_conceded=ca.DEFAULT_MAX_CONCEDED,
                       opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE) == []


class TestSampleSize:
    def test_a_side_with_too_few_venue_games_is_dropped(self):
        short = side("Short", "l", [m(True, 9, 6, 1, 2)] * 2)
        teams = {t["team_id"]: t for t in [short, SOLID] + FILLER}
        fx = {"f1": {**FIXTURES["f1"],
                     "_fixture": {"fixture_id": "f1", "home_team_id": "Short",
                                  "away_team_id": "Solid"}}}
        assert ca.scan(fx, teams, PARS, corner_edge=ca.DEFAULT_CORNER_EDGE,
                       min_leaking=ca.DEFAULT_MIN_LEAKING,
                       min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                       max_conceded=ca.DEFAULT_MAX_CONCEDED,
                       opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE) == []

    def test_a_thin_row_is_flagged_rather_than_mixed_in(self):
        # "a five-game average is EXTREME by construction, so thin rows do not merely
        # appear in the ranking, they lead it" — watchlist.py, via press_board.
        thin = side("Thinnish", "l", [m(True, 9, 6, 1, 2)] * 4 + [m(False, 5, 6, 1, 2)] * 8)
        teams = {t["team_id"]: t for t in [thin, SOLID] + FILLER}
        fx = {"f1": {**FIXTURES["f1"],
                     "_fixture": {"fixture_id": "f1", "home_team_id": "Thinnish",
                                  "away_team_id": "Solid"}}}
        rows = ca.scan(fx, teams, PARS, corner_edge=ca.DEFAULT_CORNER_EDGE,
                       min_leaking=ca.DEFAULT_MIN_LEAKING,
                       min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                       max_conceded=ca.DEFAULT_MAX_CONCEDED,
                       opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE)
        assert len(rows) == 1 and rows[0]["thin"] is True


def test_both_sides_of_a_fixture_are_tested():
    """The mechanism has nothing to do with which ground it is played on, so screening
    only home sides would silently halve the board."""
    # Same pair, venues swapped: Leaky away (5 corners, no edge) must NOT appear, and
    # the away-side branch must still have been walked — proven by a second fixture
    # where the AWAY team is the one that fits.
    away_leaky = side("AwayLeaky", "l", [m(False, 9, 6, 1, 2)] * 8 + [m(True, 5, 6, 1, 2)] * 8)
    home_solid = side("HomeSolid", "l", [m(True, 4, 7, 2, 0)] * 5 + [m(True, 3, 7, 0, 1)] * 3
                                        + [m(False, 4, 7, 2, 0)] * 8)
    teams = {t["team_id"]: t for t in [away_leaky, home_solid] + FILLER}
    fx = {"f2": {"_fixture": {"fixture_id": "f2", "home_team_id": "HomeSolid",
                              "away_team_id": "AwayLeaky"},
                 "date": "2026-10-11T15:00:00+00:00", "home": "HomeSolid",
                 "away": "AwayLeaky", "league_name": "Test",
                 "lambda_home": 4.0, "lambda_away": 8.0}}
    rows = ca.scan(fx, teams, ca.league_pars([away_leaky, home_solid] + FILLER),
                   corner_edge=ca.DEFAULT_CORNER_EDGE,
                   min_leaking=ca.DEFAULT_MIN_LEAKING,
                   min_win_rate=ca.DEFAULT_MIN_WIN_RATE,
                   max_conceded=ca.DEFAULT_MAX_CONCEDED,
                   opp_corner_edge=ca.DEFAULT_OPP_CORNER_EDGE)
    assert [r["team"] for r in rows] == ["AwayLeaky"]
    assert rows[0]["venue"] == "away"
