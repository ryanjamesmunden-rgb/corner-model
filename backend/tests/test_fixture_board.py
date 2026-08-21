"""Unit tests for the home-page fixture board.

The per-day cap is the requirement: 2-3 fixtures a day, never a wall of them. Dropping
the wrong one is a silent failure — you would simply never see the game you wanted — so
the grouping and capping are pure and pinned here."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import _angle_rank, board_days  # noqa: E402


def fx(fid, day, hour, edge, angles=1):
    return {"fixture_id": fid, "date": f"{day}T{hour:02d}:00:00Z",
            "corner_edge": edge, "angle_count": angles}


# --- the cap ---
def test_keeps_only_per_day_fixtures():
    rows = [fx(f"f{i}", "2026-09-01", 12 + i, 1.5 - i * 0.1) for i in range(8)]
    for cap in (2, 3):
        days = board_days(rows, cap)
        assert len(days) == 1
        assert len(days[0]["fixtures"]) == cap


def test_the_cap_drops_the_weakest_not_an_arbitrary_slice():
    rows = [fx("weak", "2026-09-01", 12, 1.01), fx("best", "2026-09-01", 20, 1.40),
            fx("mid", "2026-09-01", 15, 1.20)]
    kept = [r["fixture_id"] for r in board_days(rows, 2)[0]["fixtures"]]
    assert set(kept) == {"best", "mid"}


def test_narrowing_the_cap_is_a_subset_of_the_wider_one():
    """Going 3 -> 2 must remove one, never reshuffle into a different pair."""
    rows = [fx(f"f{i}", "2026-09-01", 12 + i, 1.5 - i * 0.07) for i in range(6)]
    three = {r["fixture_id"] for r in board_days(rows, 3)[0]["fixtures"]}
    two = {r["fixture_id"] for r in board_days(rows, 2)[0]["fixtures"]}
    assert two < three


def test_angle_count_breaks_a_tie_on_edge():
    rows = [fx("thin", "2026-09-01", 12, 1.20, angles=1),
            fx("rich", "2026-09-01", 13, 1.20, angles=5)]
    assert board_days(rows, 1)[0]["fixtures"][0]["fixture_id"] == "rich"


# --- reading order ---
def test_days_come_back_in_calendar_order():
    rows = [fx("c", "2026-09-03", 12, 1.1), fx("a", "2026-09-01", 12, 1.1),
            fx("b", "2026-09-02", 12, 1.1)]
    assert [d["day"] for d in board_days(rows, 3)] == ["2026-09-01", "2026-09-02", "2026-09-03"]


def test_within_a_day_fixtures_read_in_kickoff_order_not_score_order():
    """The board is a schedule. An 8pm game must not print above a 1pm one."""
    rows = [fx("late", "2026-09-01", 20, 1.40), fx("early", "2026-09-01", 13, 1.20)]
    got = [r["fixture_id"] for r in board_days(rows, 3)[0]["fixtures"]]
    assert got == ["early", "late"]


def test_considered_reports_the_full_day_not_the_capped_one():
    """So the UI can honestly say '3 of 9'."""
    rows = [fx(f"f{i}", "2026-09-01", 12 + i, 1.5 - i * 0.1) for i in range(9)]
    day = board_days(rows, 3)[0]
    assert day["considered"] == 9 and len(day["fixtures"]) == 3


def test_each_day_is_capped_separately():
    rows = ([fx(f"a{i}", "2026-09-01", 12 + i, 1.3) for i in range(5)]
            + [fx(f"b{i}", "2026-09-02", 12 + i, 1.3) for i in range(5)])
    assert [len(d["fixtures"]) for d in board_days(rows, 2)] == [2, 2]


def test_rows_without_a_date_are_dropped_rather_than_grouped_under_blank():
    rows = [fx("ok", "2026-09-01", 12, 1.2), {"fixture_id": "bad", "date": None,
                                              "corner_edge": 9.0, "angle_count": 9}]
    days = board_days(rows, 3)
    assert len(days) == 1 and [r["fixture_id"] for r in days[0]["fixtures"]] == ["ok"]


def test_empty_input_is_an_empty_board():
    assert board_days([], 3) == []


# --- which angle leads the row ---
def test_best_angle_is_the_longest_live_run():
    angles = [{"streak_len": 2, "hits": 5, "line": 4}, {"streak_len": 9, "hits": 5, "line": 3}]
    assert max(angles, key=_angle_rank)["streak_len"] == 9


def test_hits_break_a_tie_on_run_length():
    angles = [{"streak_len": 3, "hits": 5, "line": 4}, {"streak_len": 3, "hits": 8, "line": 4}]
    assert max(angles, key=_angle_rank)["hits"] == 8


def test_a_chase_angle_with_no_run_still_ranks():
    """Chase rows carry streak_len 0 — they must not blow up the sort."""
    angles = [{"kind": "chase", "streak_len": 0, "hits": 4, "line": 5},
              {"kind": "chase", "streak_len": 0, "hits": 2, "line": 5}]
    assert max(angles, key=_angle_rank)["hits"] == 4


def test_missing_keys_do_not_raise():
    assert _angle_rank({}) == (0, 0, 0)
