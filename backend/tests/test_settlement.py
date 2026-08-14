"""Unit tests for settlement grading. Pure functions, no network or DB.

Runnable either with pytest or directly: `python tests/test_settlement.py`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settlement import (  # noqa: E402
    WON, LOST, VOID, HALF_WON, HALF_LOST,
    grade_line, grade_pick, is_quarter_line, pick_profit, resolve_market,
)


def test_quarter_line_detection():
    assert is_quarter_line(9.25) and is_quarter_line(9.75)
    assert is_quarter_line(-0.25)
    assert not is_quarter_line(9.0)
    assert not is_quarter_line(9.5)


def test_half_line_never_pushes():
    assert grade_line(10, 9.5, "over") == WON
    assert grade_line(9, 9.5, "over") == LOST
    assert grade_line(9, 9.5, "under") == WON
    assert grade_line(10, 9.5, "under") == LOST


def test_whole_line_pushes_on_exact_hit():
    assert grade_line(10, 10.0, "over") == VOID
    assert grade_line(10, 10.0, "under") == VOID
    assert grade_line(11, 10.0, "over") == WON
    assert grade_line(9, 10.0, "over") == LOST


def test_quarter_line_half_win_and_half_loss():
    # 9.25 over splits across 9.0 (push) and 9.5 (loss) when exactly 9 land.
    assert grade_line(9, 9.25, "over") == HALF_LOST
    assert grade_line(10, 9.25, "over") == WON
    assert grade_line(8, 9.25, "over") == LOST
    # 8.75 over splits across 8.5 (win) and 9.0 (push) when exactly 9 land.
    assert grade_line(9, 8.75, "over") == HALF_WON
    assert grade_line(8, 8.75, "over") == LOST
    assert grade_line(10, 8.75, "over") == WON


def test_quarter_line_under_mirrors_over():
    assert grade_line(9, 9.25, "under") == HALF_WON
    assert grade_line(9, 8.75, "under") == HALF_LOST
    assert grade_line(8, 9.25, "under") == WON
    assert grade_line(10, 8.75, "under") == LOST
    # Same total, same line, opposite sides: the two halves must be complements.
    assert grade_line(9, 9.25, "over") == HALF_LOST
    assert grade_line(9, 9.25, "under") == HALF_WON


def test_team_corners_plus_line():
    """'6+' means 6 or more — graded as Over 5.5, so it can never push."""
    pick = {"market": "team_corners", "line": 6}
    assert grade_pick(pick, team_corners=6, opp_corners=3)[0] == WON
    assert grade_pick(pick, team_corners=7, opp_corners=3)[0] == WON
    assert grade_pick(pick, team_corners=5, opp_corners=9)[0] == LOST


def test_match_total():
    pick = {"market": "match_total", "line": 9.5, "direction": "over"}
    assert grade_pick(pick, 5, 5)[0] == WON      # 10 total
    assert grade_pick(pick, 4, 5)[0] == LOST     # 9 total
    under = {"market": "match_total", "line": 10.0, "direction": "under"}
    assert grade_pick(under, 5, 5)[0] == VOID    # exactly 10 pushes


def test_asian_total_quarter():
    pick = {"market": "asian_total", "line": 10.25, "direction": "over"}
    assert grade_pick(pick, 5, 5)[0] == HALF_LOST   # 10 total
    assert grade_pick(pick, 6, 5)[0] == WON         # 11 total


def test_asian_handicap():
    """Team giving 1.5 corners must win the corner count by 2 or more."""
    pick = {"market": "asian_handicap", "line": -1.5}
    assert grade_pick(pick, 8, 6)[0] == WON       # margin +2 > 1.5
    assert grade_pick(pick, 7, 6)[0] == LOST      # margin +1
    # Receiving 0.25: wins outright, half-wins on a dead heat.
    plus = {"market": "asian_handicap", "line": 0.25}
    assert grade_pick(plus, 6, 6)[0] == HALF_WON
    assert grade_pick(plus, 7, 6)[0] == WON
    assert grade_pick(plus, 5, 6)[0] == LOST


def test_unsupported_market_is_reported_not_guessed():
    status, err = grade_pick({"market": "first_half_corners", "line": 4}, 5, 4)
    assert status is None and "unsupported market" in err
    assert resolve_market({"market": "team_corners"}, 5, 4) is None  # no line


def test_profit_at_flat_1u():
    assert pick_profit(WON, 2.5) == 1.5
    assert pick_profit(HALF_WON, 2.5) == 0.75
    assert pick_profit(LOST, 2.5) == -1.0
    assert pick_profit(HALF_LOST, 2.5) == -0.5
    assert pick_profit(VOID, 2.5) == 0.0
    # Losses and pushes don't depend on a price being known.
    assert pick_profit(LOST, None) == -1.0
    assert pick_profit(VOID, None) == 0.0
    # A win at an unknown price has no computable return.
    assert pick_profit(WON, None) is None
    assert pick_profit(HALF_WON, None) is None
    assert pick_profit("pending", 2.0) is None


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc or 'assertion failed'}")
    print(f"\n{'FAILED' if failures else 'ALL PASSED'} ({failures} failure(s))")
    sys.exit(1 if failures else 0)
