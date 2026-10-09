"""The corner ticker's two lists.

WHAT THIS PINS. The ticker holds its teams as literals on a standalone page, so these
numbers get copied by hand and then live for weeks. The ways that goes wrong are not
arithmetic:

  - a "last 5" built from three games is a different, noisier number wearing the same
    label, and because a short window is extreme by construction it would LEAD the
    ranking rather than merely appear in it.
  - the window has to come off a date-sorted list, or "the last five" means "whichever
    five the sync happened to write last".
  - a missing corner count is not a nil.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ticker_feed as tf  # noqa: E402


def m(date, cf):
    return {"date": date, "corners_for": cf, "corners_against": 4, "home": True,
            "goals_for": 1, "goals_against": 1, "opponent": "X"}


def team(name, league, corners, dates=None):
    rows = [m(dates[i] if dates else f"2026-09-{i + 1:02d}", c)
            for i, c in enumerate(corners)]
    return {"team_id": name, "name": name, "league_id": league, "real_matches": rows}


NAMES = {"eng-ch": "Championship", "ned-ed": "Eredivisie"}

# Was quiet, is now loud: season 5.0, last five 9.0. The two lists must disagree.
TURNED = team("Cardiff", "eng-ch", [1, 1, 1, 1, 1, 9, 9, 9, 9, 9])
# Loud all season and no more so lately.
STEADY = team("PSV", "ned-ed", [7, 7, 7, 7, 7, 7, 7, 7, 7, 7])
# Three games at a huge rate — the row that must NOT top a five-game list.
SHORT = team("Newcomer", "eng-ch", [14, 14, 14])


class TestTheFormListNeedsItsFullWindow:
    def test_a_side_with_too_few_games_is_dropped(self):
        # Not ranked low — dropped. A three-game average at 14 would lead a five-game
        # list and be the first thing read off a recording.
        rows = tf.build([TURNED, STEADY, SHORT], NAMES, 5, 10)
        assert "Newcomer" not in [r["name"] for r in rows]

    def test_and_it_is_the_window_that_decides_not_a_fixed_floor(self):
        # At a window of three the same side is a legitimate row.
        rows = tf.build([SHORT], NAMES, 3, 10)
        assert [r["name"] for r in rows] == ["Newcomer"]

    def test_the_season_list_keeps_it_if_it_has_enough_games(self):
        enough = team("Six", "eng-ch", [8] * tf.MIN_SEASON_GAMES)
        assert [r["name"] for r in tf.build([enough], NAMES, 0, 10)] == ["Six"]

    def test_but_not_below_the_season_floor(self):
        thin = team("Few", "eng-ch", [8] * (tf.MIN_SEASON_GAMES - 1))
        assert tf.build([thin], NAMES, 0, 10) == []


class TestTheTwoListsAnswerDifferentQuestions:
    def test_the_season_list_ranks_on_everything(self):
        rows = tf.build([TURNED, STEADY], NAMES, 0, 10)
        assert [r["name"] for r in rows] == ["PSV", "Cardiff"]
        assert rows[1]["value"] == 5.0

    def test_the_form_list_ranks_on_the_last_five(self):
        rows = tf.build([TURNED, STEADY], NAMES, 5, 10)
        assert [r["name"] for r in rows] == ["Cardiff", "PSV"]
        assert rows[0]["value"] == 9.0

    def test_only_the_form_list_carries_the_flame(self):
        # The flame marks a claim about form. A season average is not one.
        assert all(r["hot"] for r in tf.build([STEADY], NAMES, 5, 10))
        assert not any(r["hot"] for r in tf.build([STEADY], NAMES, 0, 10))


class TestTheWindowComesOffADateSortedList:
    def test_stored_order_does_not_decide_which_five_are_last(self):
        # Shuffled on purpose. Walked as stored, "the last five" would be the first
        # five of the season and the number would be quietly wrong.
        shuffled = team("Shuffled", "eng-ch", [9, 9, 9, 9, 9, 1, 1, 1, 1, 1],
                        dates=["2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09",
                               "2026-09-10", "2026-09-01", "2026-09-02", "2026-09-03",
                               "2026-09-04", "2026-09-05"])
        assert tf.rate_over(shuffled, 5) == 9.0


class TestAGapIsNotANil:
    def test_a_missing_corner_count_drops_the_row(self):
        gappy = team("Gappy", "eng-ch", [8, 8, 8, 8])
        gappy["real_matches"].append({"date": "2026-09-09", "opponent": "X"})
        assert tf.rate_over(gappy, 5) is None, "averaging over a gap reports a quiet side"

    def test_a_team_with_no_history_at_all_is_not_a_zero(self):
        assert tf.rate_over(team("Empty", "eng-ch", []), 5) is None
        assert tf.build([team("Empty", "eng-ch", [])], NAMES, 5, 10) == []


class TestTheShapeIsTheOneThePageWants:
    def test_each_row_has_exactly_the_four_keys_the_ticker_reads(self):
        r = tf.build([STEADY], NAMES, 5, 10)[0]
        assert set(r) == {"name", "league", "value", "hot"}

    def test_the_league_is_its_display_name_not_its_id(self):
        assert tf.build([STEADY], NAMES, 5, 10)[0]["league"] == "Eredivisie"

    def test_an_unknown_league_is_blank_rather_than_an_id_leaking_through(self):
        # "ned-ed" on a recording is a bug anybody can see; an empty slot is not.
        assert tf.build([team("X", "zzz", [7] * 6)], NAMES, 5, 10)[0]["league"] == ""

    def test_the_value_is_rounded_for_display(self):
        odd = team("Odd", "eng-ch", [1, 2, 3, 4, 6])
        assert tf.build([odd], NAMES, 5, 10)[0]["value"] == 3.2

    def test_the_top_cap_is_honoured(self):
        many = [team(f"T{i}", "eng-ch", [i] * 6) for i in range(1, 12)]
        assert len(tf.build(many, NAMES, 5, 4)) == 4

    def test_and_the_cap_keeps_the_BEST_rather_than_the_first(self):
        many = [team(f"T{i}", "eng-ch", [i] * 6) for i in range(1, 12)]
        assert [r["name"] for r in tf.build(many, NAMES, 5, 3)] == ["T11", "T10", "T9"]
