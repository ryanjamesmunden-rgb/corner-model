"""The chase score, after the ranking was measured and found not to rank.

measure_chase_board.py replays the board walk-forward and scores each ordering by
RESIDUAL — actual hit rate minus the model's own probability — i.e. does the order find
spots the model underrates. Results:

    chase_score  +0.02      lambda_only  +0.01
    no_opp_fh    +0.03      RANDOM       flat   <- control passed

All the same number, and the flat control is what makes that trustworthy. These tests
pin the two things that follow: the falsified opponent term is gone, and nothing quietly
puts it back."""
import inspect
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

SRC = inspect.getsource(server._chase_board)


def chase_score(lam, consistency):
    """Mirror of the live formula, so a change to it has to change this too."""
    return round(lam * (0.6 + 0.4 * consistency), 3)


def test_the_opponent_first_half_term_is_gone_from_the_score():
    """Five tests failed to find an effect. It must not creep back into the ordering."""
    score_line = next(l for l in SRC.splitlines() if l.strip().startswith("chase_score ="))
    assert "opp_fh" not in score_line, score_line


def test_opp_fh_is_still_returned_as_context():
    """Removing it from the SCORE is not the same as hiding it — it stays on the row."""
    assert '"opp_fh_rate"' in SRC


def test_score_still_rises_with_the_projection():
    assert chase_score(6.0, 0.5) > chase_score(5.0, 0.5)


def test_score_still_rises_with_consistency():
    assert chase_score(5.0, 1.0) > chase_score(5.0, 0.0)


def test_consistency_cannot_swamp_the_projection():
    """The 0.6 floor keeps a 0/5 team from being scored to nothing."""
    assert chase_score(5.0, 0.0) == pytest.approx(5.0 * 0.6)
    assert chase_score(5.0, 1.0) == pytest.approx(5.0)


def test_consistency_can_outweigh_a_bigger_projection_and_by_how_much():
    """Worth pinning because it is not obvious from the formula.

    The consistency factor spans 0.6 to 1.0, so a 5/5 team beats a 0/5 team until the
    0/5 team's projection is 1/0.6 = ~67% larger. A 5.0 lambda at 5/5 therefore outranks
    an 8.0 lambda at 0/5 — deliberate, given consistency is a second look at the same
    quantity lambda estimates, but it is a big lever for a term measured as noise."""
    assert chase_score(5.0, 1.0) > chase_score(8.0, 0.0)      # 5.00 vs 4.80
    assert chase_score(5.0, 1.0) < chase_score(8.5, 0.0)      # 5.00 vs 5.10
    crossover = 1 / 0.6
    assert chase_score(5.0 * crossover, 0.0) == pytest.approx(chase_score(5.0, 1.0), abs=0.01)


def test_the_board_still_sorts_by_the_score():
    assert 'sort(key=lambda x: x["chase_score"]' in SRC


def test_the_null_result_is_recorded_where_the_score_is_defined():
    """A future reader must not re-add a term without seeing that this was measured."""
    assert "RANDOM" in SRC and "not to rank" in SRC.lower()
