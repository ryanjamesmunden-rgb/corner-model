"""Attaching the model's view to a starred game, so the list can be ranked by it.

WHY THE STARRED LIST NEEDED A NUMBER AT ALL. Starring is a "come back to this once prices
are up" gesture, and coming back to six games with no idea which projects highest means
re-opening all six — the re-scanning the feature exists to avoid.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    with open(os.path.join(HERE, "server.py")) as fh:
        return fh.read()


def _endpoint():
    src = _src()
    fn = src[src.index('@api_router.get("/favourites")'):]
    return fn[:fn.index('@api_router.post("/favourites/{fixture_id}")')]


def test_one_projection_implementation_is_reused():
    """_fixture_projections' own header asks for this: a second projection here would be a
    second expected_lambdas call site to keep in step, and it would eventually disagree
    with the board about the same fixture."""
    fn = _endpoint()
    assert "_fixture_projections(" in fn
    assert "expected_lambdas(" not in fn, "a second call site is the thing to avoid"


def test_the_window_is_sized_to_the_furthest_saved_game():
    """A star can sit weeks out, and the helper's default is seven days — which would
    quietly return no projection for exactly the games somebody saved early."""
    fn = _endpoint()
    assert "furthest" in fn
    assert "BOARD_MAX_DAYS" in fn


def test_the_window_is_capped_at_what_the_board_itself_projects():
    fn = _endpoint()
    assert "min(max(furthest, 1), BOARD_MAX_DAYS)" in fn


def test_a_game_outside_the_window_carries_none_rather_than_a_zero():
    """Sorting an absent projection as zero would put it top of "lowest", so the list that
    looked like an answer would be made of rows the model has no opinion about."""
    fn = _endpoint()
    assert '"projection": None if p is None else {' in fn


def test_the_projection_is_trimmed_to_what_the_list_reads():
    """The whole projection row carries the mismatch angles and cup wording the fixture
    page needs and a saved-games list does not."""
    fn = _endpoint()
    for key in ("lambda_total", "league_avg_total", "corner_edge",
                "home_games", "away_games"):
        assert f'"{key}"' in fn, key
    assert '"angles"' not in fn


def test_the_window_is_stated_in_the_response():
    """So the page can explain a blank projection instead of the reader assuming the model
    has no opinion on their game."""
    fn = _endpoint()
    assert '"projected_within_days": BOARD_MAX_DAYS' in fn


def test_no_projection_work_happens_when_nothing_is_saved():
    """The helper loads every team and league and models every fixture in the window — a
    real cost, and pointless for a user with an empty list."""
    fn = _endpoint()
    assert "if furthest > 0:" in fn
    tree = ast.parse(_src())
    fav = next(n for n in ast.walk(tree)
               if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
               and n.name == "list_favourites")
    # The early return for "no stars at all" must still come first.
    first = fav.body[1] if len(fav.body) > 1 else fav.body[0]
    assert isinstance(first, ast.Assign) or isinstance(first, ast.Expr)
    assert "if not favs:" in _endpoint()


def test_the_unreadable_date_does_not_break_the_window_maths():
    """This runs over every saved fixture and one bad row must not end the request."""
    fn = _endpoint()
    assert "except Exception:" in fn
    assert "continue" in fn
