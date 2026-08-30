"""Unit tests for the home-page fixture board.

Two requirements live here, and both fail silently if they break.

The per-day CEILING: drop the wrong fixture and you simply never see the game you wanted.

The absolute BAR: `per_day` is a ceiling, not a quota. Sort-and-take-N always promotes
something, so a day with one fixture on would crown it by default. The bar cannot depend
on the rest of the day's card — the same fixture must pass or fail identically on a quiet
Tuesday and a ten-game Saturday."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    _angle_rank, angle_is_strong, board_days, board_reason, dedupe_angles,
    fixture_qualifies,
)


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
    assert _angle_rank({}) == (0, 0, 0, 0)


# --- the absolute bar ---
# `per_day` is a CEILING, not a quota. Sort-and-take-N always promotes something, so a
# quiet day would crown whatever happened to be on. These pin that it cannot.
def strong_streak(run=5):
    return {"kind": "over_team", "streak_len": run, "hits": 5, "line": 5}


def weak_streak(run=2):
    return {"kind": "over_team", "streak_len": run, "hits": 5, "line": 5}


def chase(rate):
    return {"kind": "chase", "streak_len": 0, "hits": int(rate * 5), "line": 5,
            "consistency_rate": rate}


def row(edge=1.2, games=12, angles=None):
    angles = [strong_streak()] if angles is None else angles
    for a in angles:
        a["strong"] = angle_is_strong(a)
    return {"date": "2026-09-01T15:00:00Z", "corner_edge": edge,
            "home_games": games, "away_games": games, "angles": angles}


def test_the_only_game_on_a_quiet_day_still_has_to_earn_it():
    """The complaint: a lone fixture must not be crowned just for being alone."""
    lone_weak = row(angles=[weak_streak()])
    assert fixture_qualifies(lone_weak) is False
    assert board_days([r for r in [lone_weak] if fixture_qualifies(r)], 5) == []


def test_the_same_fixture_qualifies_on_a_busy_day_and_a_quiet_one():
    """The bar is absolute — it cannot depend on the rest of the card."""
    good = row()
    assert fixture_qualifies(good) is True
    crowd = [good] + [row(edge=1.9) for _ in range(9)]
    assert fixture_qualifies(good) is True and len([r for r in crowd if fixture_qualifies(r)]) == 10


def test_a_present_angle_is_not_a_strong_one():
    assert angle_is_strong(weak_streak(run=2)) is False
    assert angle_is_strong(strong_streak(run=3)) is True


def test_a_chase_spot_needs_its_hit_rate_not_just_a_place_on_the_board():
    assert angle_is_strong(chase(0.6)) is False        # 3 of 5
    assert angle_is_strong(chase(0.8)) is True         # 4 of 5


def test_thin_history_fails_the_context_hurdle_however_good_the_angle():
    assert fixture_qualifies(row(games=3)) is False
    assert fixture_qualifies(row(games=6)) is True


def test_the_thinner_side_decides_context():
    r = row()
    r["home_games"], r["away_games"] = 20, 2
    assert fixture_qualifies(r) is False


def test_a_below_par_projection_fails_however_long_the_streak():
    assert fixture_qualifies(row(edge=0.92, angles=[strong_streak(run=9)])) is False


def test_a_pile_of_weak_angles_does_not_add_up_to_a_strong_one():
    assert fixture_qualifies(row(angles=[weak_streak(), weak_streak(), chase(0.4)])) is False


def test_one_strong_angle_among_weak_ones_is_enough():
    assert fixture_qualifies(row(angles=[weak_streak(), strong_streak(), chase(0.2)])) is True


def test_no_angles_at_all_never_qualifies():
    assert fixture_qualifies(row(angles=[])) is False


def test_the_bar_is_loosenable_for_a_thin_week():
    r = row(games=4, edge=0.95, angles=[weak_streak(run=2)])
    r["angles"][0]["strong"] = angle_is_strong(r["angles"][0], min_run=2)
    assert fixture_qualifies(r, min_games=4, min_edge=0.9) is True


def test_strong_angles_sort_above_weak_ones():
    angles = [weak_streak(run=2), strong_streak(run=3)]
    for a in angles:
        a["strong"] = angle_is_strong(a)
    assert max(angles, key=_angle_rank)["strong"] is True


# --------------------------------------------------------------------------------------
# Mismatches as a qualifying angle, and the reason line.
#
# The board could only see streaks and chase spots, so a strong matchup with nothing
# running was invisible — a game with a real reason to open it never appeared. And every
# fixture that DID appear left the reader to infer why from up to six chips, which is what
# made the colours confusing in the first place.

def test_a_mismatch_with_enough_sample_is_strong():
    """A mismatch has no run and no hit rate — sample is the only thing that can carry it."""
    assert angle_is_strong({"kind": "mismatch", "real_samples": 6})
    assert angle_is_strong({"kind": "mismatch", "real_samples": 20})


def test_a_mismatch_on_a_thin_sample_is_not():
    """Two averages over three games each is not evidence, however far apart they are."""
    assert not angle_is_strong({"kind": "mismatch", "real_samples": 3})
    assert not angle_is_strong({"kind": "mismatch", "real_samples": 0})
    assert not angle_is_strong({"kind": "mismatch"})


def test_a_mismatch_is_not_judged_on_run_length():
    """It carries streak_len 0 by construction; the streak rule would reject every one."""
    assert angle_is_strong({"kind": "mismatch", "real_samples": 9, "streak_len": 0})


def test_a_mismatch_alone_can_qualify_a_fixture():
    row = {"home_games": 10, "away_games": 10, "corner_edge": 1.1,
           "angles": [{"kind": "mismatch", "real_samples": 8, "strong": True}]}
    assert fixture_qualifies(row)


def test_a_thin_mismatch_alone_cannot():
    row = {"home_games": 10, "away_games": 10, "corner_edge": 1.1,
           "angles": [{"kind": "mismatch", "real_samples": 2, "strong": False}]}
    assert not fixture_qualifies(row)


def test_the_reason_names_the_signal_for_every_kind():
    """Every fixture on the board has a reason, and it has to read as a sentence."""
    cases = [
        ({"kind": "chase", "team": "Barnet", "line": 6, "consistency_rate": 0.8}, "80%"),
        ({"kind": "mismatch", "team": "Barnet", "line": 6, "team_for": 8.2,
          "opp_conceded": 4.67, "real_samples": 12}, "conceding 4.67"),
        ({"kind": "over_team", "team": "Barnet", "line": 6, "streak_len": 12}, "above"),
        ({"kind": "under_team", "team": "Bahia", "line": 7, "streak_len": 4}, "below"),
        ({"kind": "over_match", "team": "Wycombe", "line": 9, "streak_len": 7}, "match total"),
    ]
    for angle, fragment in cases:
        reason = board_reason(angle)
        assert reason and fragment in reason, (angle["kind"], reason)
        assert angle["team"] in reason


def test_no_strong_angle_means_no_reason_rather_than_an_invented_one():
    assert board_reason(None) is None


def test_an_under_reason_never_reads_as_an_over():
    """The point of the colour change: direction must never be ambiguous, and the sentence
    must not undo what the colour says."""
    under = board_reason({"kind": "under_team", "team": "Bahia", "line": 7, "streak_len": 4})
    assert "below" in under and "above" not in under


def test_a_mismatch_duplicating_a_streak_is_dropped():
    """Same team, same line, two chips proposing one bet — the exact confusion the colour
    change exists to end. The streak survives: it has a hit rate, the mismatch has not."""
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6},
              {"kind": "mismatch", "team": "Barnet", "line": 6}]
    kept = dedupe_angles(angles)
    assert [a["kind"] for a in kept] == ["over_team"]


def test_a_mismatch_on_a_different_line_survives():
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6},
              {"kind": "mismatch", "team": "Barnet", "line": 8}]
    assert len(dedupe_angles(angles)) == 2


def test_a_mismatch_on_the_other_team_survives():
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6},
              {"kind": "mismatch", "team": "Exeter", "line": 6}]
    assert len(dedupe_angles(angles)) == 2


def test_a_lone_mismatch_is_never_dropped():
    """Nothing else covers it, so it is the only reason the fixture is here."""
    angles = [{"kind": "mismatch", "team": "Bradford", "line": 4}]
    assert dedupe_angles(angles) == angles


def test_dedupe_never_drops_a_non_mismatch():
    """A chase and a streak on the same team and line are different bets, not duplicates."""
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6},
              {"kind": "chase", "team": "Barnet", "line": 6}]
    assert len(dedupe_angles(angles)) == 2
