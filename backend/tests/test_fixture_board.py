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
    BOARD_MAX_DAYS, _angle_rank, angle_is_strong, board_days, board_reason,
    angle_subject, dedupe_angles, fixture_qualifies, mismatch_angle,
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


def test_opposing_directions_on_one_team_collapse_to_the_better():
    """The reported bug: "Barnet 4+ corners" and "Barnet under 6 corners" on one row.
    Both true, but as two chips they tell a reader nothing to back."""
    angles = [{"kind": "over_team", "team": "Barnet", "line": 4, "strong": True, "streak_len": 12},
              {"kind": "under_team", "team": "Barnet", "line": 6, "strong": True, "streak_len": 3}]
    kept = dedupe_angles(angles)
    assert len(kept) == 1
    assert kept[0]["kind"] == "over_team"   # the 12-game run beats the bracketing under


def test_the_weaker_direction_loses_even_when_it_is_the_over():
    angles = [{"kind": "over_team", "team": "Bahia", "line": 4, "strong": False, "streak_len": 1},
              {"kind": "under_team", "team": "Bahia", "line": 7, "strong": True, "streak_len": 8}]
    kept = dedupe_angles(angles)
    assert [a["kind"] for a in kept] == ["under_team"]


def test_both_sides_of_a_fixture_survive():
    """An over from one team's history and an under from the other's are different
    subjects — this is the case the colours exist to keep legible, not a contradiction."""
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6, "strong": True, "streak_len": 12},
              {"kind": "under_team", "team": "Exeter", "line": 6, "strong": True, "streak_len": 5}]
    assert len(dedupe_angles(angles)) == 2


def test_team_corners_and_match_total_are_different_quantities():
    """One is about that side, one about the game — both can stand on the same team."""
    angles = [{"kind": "over_team", "team": "Wycombe", "line": 4, "strong": True, "streak_len": 7},
              {"kind": "over_match", "team": "Wycombe", "line": 9, "strong": True, "streak_len": 7}]
    assert len(dedupe_angles(angles)) == 2


def test_a_streak_beats_the_mismatch_that_merely_agrees_with_it():
    """A mismatch is two averages pointed at each other, with no hit rate behind it."""
    angles = [{"kind": "over_team", "team": "Barnet", "line": 6, "strong": True, "streak_len": 12},
              {"kind": "mismatch", "team": "Barnet", "line": 6, "strong": True, "streak_len": 0}]
    kept = dedupe_angles(angles)
    assert [a["kind"] for a in kept] == ["over_team"]


def test_a_lone_mismatch_still_survives():
    angles = [{"kind": "mismatch", "team": "Bradford", "line": 4, "strong": True, "streak_len": 0}]
    assert dedupe_angles(angles) == angles


def test_a_fixture_tops_out_at_four_chips():
    """Each side's own corners and each side's read on the match total. No more."""
    angles = []
    for team in ("Barnet", "Exeter"):
        for kind in ("over_team", "under_team", "mismatch", "over_match", "under_match"):
            angles.append({"kind": kind, "team": team, "line": 5, "strong": True, "streak_len": 4})
    assert len(dedupe_angles(angles)) == 4


def test_the_subject_split_is_by_quantity_not_direction():
    assert angle_subject("over_match") == "match"
    assert angle_subject("under_match") == "match"
    assert angle_subject("over_team") == "team"
    assert angle_subject("chase") == "team"
    assert angle_subject("mismatch") == "team"


# --------------------------------------------------------------------------------------
# Looking further ahead.
#
# Two limits made a month-long window pointless. The board clamped days to 14 while the
# UI offered a "Month" tab, so Month silently returned a fortnight. And every mismatch was
# read off _next_fixtures, which keeps only each team's FIRST upcoming game — so widening
# the window added fixtures but not one extra mismatch. Finding a strong side drawn
# against a leaky defence three weeks out was impossible by construction.

def _team(name, for_=8.0, against=8.0, n=12):
    """A team whose home and away splits both average `for_` won and `against` conceded."""
    ms = []
    for i in range(n):
        ms.append({"home": i % 2 == 0, "corners_for": for_, "corners_against": against,
                   "shots_for": 12, "date": f"2026-0{i % 9 + 1}-01"})
    return {"team_id": f"t-{name}", "name": name, "matches": ms, "real_matches": ms,
            "real_samples": n}


def test_the_board_can_look_a_month_ahead():
    """The UI's Month tab asks for 30; the clamp has to allow it or the tab lies."""
    assert BOARD_MAX_DAYS >= 30


def test_a_strong_side_against_a_leaky_defence_is_a_mismatch():
    strong, leaky = _team("Strong", for_=8.0), _team("Leaky", against=8.0)
    a = mismatch_angle(strong, leaky, "home", 5.0, 12.0, 0.0)
    assert a is not None
    assert a["kind"] == "mismatch" and a["team"] == "Strong"
    assert a["team_for"] >= 5.0 * 1.1 and a["opp_conceded"] >= 5.0 * 1.1


def test_an_average_side_is_not_a_mismatch_however_leaky_the_opponent():
    """Both halves have to clear the bar — a leaky defence alone is not an angle."""
    average, leaky = _team("Average", for_=5.0), _team("Leaky", against=9.0)
    assert mismatch_angle(average, leaky, "home", 5.0, 12.0, 0.0) is None


def test_a_strong_side_against_a_tight_defence_is_not_a_mismatch():
    strong, tight = _team("Strong", for_=9.0), _team("Tight", against=3.0)
    assert mismatch_angle(strong, tight, "home", 5.0, 12.0, 0.0) is None


def test_it_works_for_a_fixture_at_any_distance():
    """The point of the change: nothing here reads a next-fixture map, so a game three
    weeks out is assessed exactly like tomorrow's."""
    strong, leaky = _team("Strong", for_=8.0), _team("Leaky", against=8.0)
    assert mismatch_angle(strong, leaky, "away", 5.0, 12.0, 0.0) is not None


def test_a_team_with_no_history_at_that_venue_yields_nothing_rather_than_a_guess():
    empty = {"team_id": "t-e", "name": "Empty", "matches": [], "real_matches": [],
             "real_samples": 0}
    leaky = _team("Leaky", against=8.0)
    assert mismatch_angle(empty, leaky, "home", 5.0, 12.0, 0.0) is None
    assert mismatch_angle(leaky, empty, "home", 5.0, 12.0, 0.0) is None


def test_the_angle_carries_what_the_reason_line_needs():
    strong, leaky = _team("Strong", for_=8.0), _team("Leaky", against=8.0)
    a = mismatch_angle(strong, leaky, "home", 5.0, 12.0, 0.0)
    assert board_reason({**a, "strong": True})
    for key in ("team_for", "opp_conceded", "real_samples", "line", "prob", "fair_odds"):
        assert a.get(key) is not None, key
