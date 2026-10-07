"""What the press board may and may not claim.

The angle: an attack scoring freely at its venue against a defence that concedes almost
nothing at the other. The hazard is entirely about SAMPLE — "conceded 2 in 3 away games"
is a rate on three matches, and watchlist.py already paid for ranking thin rows beside
well-sampled ones. Most of what is pinned here is that a short split cannot lead the
board, and that the screen looks at the right venue on each side.
"""
import importlib.util
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_spec = importlib.util.spec_from_file_location(
    "press_board", os.path.join(_BACKEND, "press_board.py"))
press_board = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(press_board)


def match(home=True, goals_for=3, goals_against=0, corners_for=7, blocked=None):
    m = {"home": home, "goals_for": goals_for, "goals_against": goals_against,
         "corners_for": corners_for, "corners_against": 4}
    if blocked is not None:
        m["blocked_shots_for"] = blocked
    return m


def team(name, matches):
    return {"team_id": f"id-{name}", "name": name, "real_matches": matches}


def fixture(home, away, lam_home=7.5, lam_away=4.0):
    return {
        "fixture_id": "fx1", "date": "2026-10-10T14:00:00+00:00",
        "league_name": "Championship", "home": home["name"], "away": away["name"],
        "lambda_home": lam_home, "lambda_away": lam_away,
        "_fixture": {"home_team_id": home["team_id"], "away_team_id": away["team_id"]},
    }


def board(home, away, **kw):
    teams_by_id = {home["team_id"]: home, away["team_id"]: away}
    return press_board.scan({"fx1": fixture(home, away)}, teams_by_id,
                            kw.get("min_scoring", press_board.DEFAULT_MIN_SCORING),
                            kw.get("max_conceded", press_board.DEFAULT_MAX_CONCEDED))


# Reading: 12 goals in 4 home games. Bradford: 2 conceded in 3 away.
READING = team("Reading", [match(home=True, goals_for=3, corners_for=7)] * 4
                          + [match(home=False, goals_for=0, corners_for=3)] * 4)
BRADFORD = team("Bradford", [match(home=False, goals_for=0, goals_against=0)] * 2
                            + [match(home=False, goals_for=0, goals_against=2)]
                            + [match(home=True, goals_for=1, goals_against=3)] * 3)


def test_the_fixture_the_angle_was_written_from_is_found():
    rows = board(READING, BRADFORD)
    assert [r["team"] for r in rows] == ["Reading"]
    r = rows[0]
    assert r["scoring"] == 3.0 and r["scoring_games"] == 4
    assert round(r["conceded"], 2) == 0.67 and r["conceded_games"] == 3


def test_it_splits_by_VENUE_on_both_sides():
    """A season total hides the thing being looked for: a side can be resolute away and
    generous at home, and the average says neither. Bradford's three HOME games concede
    3 apiece and must not reach the away figure."""
    r = board(READING, BRADFORD)[0]
    assert r["conceded"] < 1          # away only, not the 1.83 a season total would give
    assert r["scoring"] == 3.0        # Reading's home games only, not the goalless aways


def test_a_generous_away_defence_is_not_this_angle():
    """The whole point is a defence good enough to survive the pressure. One that gets cut
    open ends the pressure early, and belongs to the mismatch board instead."""
    # Scoring nothing itself, so the only row this fixture could produce is the one
    # under test: Reading's attack against a defence that is not resolute.
    leaky = team("Leaky", [match(home=False, goals_for=0, goals_against=3)] * 5)
    assert board(READING, leaky) == []


def test_a_side_not_scoring_is_not_this_angle_either():
    quiet = team("Quiet", [match(home=True, goals_for=0)] * 6)
    assert board(quiet, BRADFORD) == []


def test_an_away_attack_counts_too():
    """The example is a home side; the mechanism is not. Screening only home attacks
    would silently halve the board."""
    travellers = team("Travellers", [match(home=False, goals_for=3, goals_against=1)] * 6)
    # Resolute at home and toothless with it, so it cannot qualify as an attack itself
    # and the only row left is the away one.
    stingy_at_home = team("Fortress", [match(home=True, goals_for=0, goals_against=0)] * 6)
    rows = board(stingy_at_home, travellers)
    assert [r["team"] for r in rows] == ["Travellers"]
    assert rows[0]["venue"] == "away"


def test_two_games_is_not_a_rate():
    """MIN_GAMES. Below it the row does not appear at all, however extreme it looks."""
    barely = team("Barely", [match(home=False, goals_against=0)] * 2)
    assert board(READING, barely) == []


def test_a_short_split_is_marked_thin_and_cannot_lead():
    """The watchlist lesson: a thin row does not merely appear in a ranking, it leads it.
    Bradford's three away games are under THIN_GAMES, so the row is set aside."""
    assert board(READING, BRADFORD)[0]["thin"] is True
    deep = team("Deep", [match(home=False, goals_against=0)] * press_board.THIN_GAMES)
    deep_reading = team("Reading", [match(home=True, goals_for=3)] * press_board.THIN_GAMES)
    assert board(deep_reading, deep)[0]["thin"] is False


def test_the_run_is_reported_and_never_screened_on():
    """A streak is one result from ending. Requiring one would drop the fixture in the
    week it stopped being a streak and started being a price."""
    patchy = team("Patchy", [match(home=True, goals_for=3, corners_for=9),
                             match(home=True, goals_for=3, corners_for=1)] * 3)
    rows = board(patchy, BRADFORD)
    assert rows, "a broken run must not remove the fixture"
    assert rows[0]["hits"] < rows[0]["played"]


def test_the_ordering_is_the_gap_and_the_model_rides_along():
    """`gap` orders; the model's own projection is on every row so the two can be
    compared. A row the model already rates high is not an edge, and nothing here has
    been measured against a control."""
    r = board(READING, BRADFORD)[0]
    assert r["gap"] == r["scoring"] - r["conceded"]
    assert r["lam"] == 7.5
    assert r["line"] == press_board.LINE_RULE(7.5)
    assert 0 < r["prob"] < 1
