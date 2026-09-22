"""Grading the projections board.

The failure this is built against is a record that flatters the model. Two shapes of that:
scoring only the games that settled conveniently, and scoring the projection against the
outcome rather than against a line somebody could have bet. Both read well and neither
would have told the owner anything he could act on.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from projection_record import (band_for, settle_line, grade, line_record,
                               band_record, summarise)


def entry(projection=10.0, fixture="fx1", **kw):
    return {"fixture_id": fixture, "lambda_total": projection,
            "home": "A", "away": "B", **kw}


class TestBands:
    def test_the_quiet_end_is_its_own_band(self):
        # The end the board was extended to show, and the one an under is bet on.
        assert band_for(7.9) == "quiet"
        assert band_for(8.4) == "quiet"

    def test_the_boundaries_do_not_overlap(self):
        # A row in two bands would be counted twice in the totals.
        assert band_for(8.5) == "below par"
        assert band_for(9.5) == "middling"
        assert band_for(10.5) == "busy"
        assert band_for(11.5) == "very busy"

    def test_a_missing_projection_is_not_silently_a_quiet_game(self):
        assert band_for(None) == "unknown"


class TestOneGame:
    def test_a_game_that_has_not_been_played_settles_nothing(self):
        g = grade(entry(10.0), None)
        assert g["settled"] is False
        assert g["error"] is None and g["lines"] == {}

    def test_the_error_is_signed_actual_minus_projected(self):
        # Positive means the game had MORE corners than the model said. Fixed in that
        # direction everywhere — a sign convention that varies by function is a bug
        # waiting for somebody to average two of them together.
        assert grade(entry(9.0), 12)["error"] == 3.0
        assert grade(entry(11.0), 8)["error"] == -3.0

    def test_each_line_records_what_was_called_and_what_landed(self):
        # Stored as a pair so a caller cannot score the outcome against itself.
        g = grade(entry(10.2), 8)
        assert g["lines"]["9.5"] == {"called": "over", "landed": "under"}
        assert g["lines"]["10.5"] == {"called": "under", "landed": "under"}

    def test_a_half_line_cannot_push(self):
        assert settle_line(9, 9.5) == "under"
        assert settle_line(10, 9.5) == "over"

    def test_an_unplayed_game_has_no_side(self):
        assert settle_line(None, 9.5) is None


class TestTheLineRecord:
    def test_it_scores_the_side_the_projection_called(self):
        # Not "how close was the number". Betting a line is binary, and a model can be
        # two corners out on average and still land the right side of 9.5 four in five.
        rows = [grade(entry(11.0, "a"), 12),   # called over, landed over
                grade(entry(11.0, "b"), 8),    # called over, landed under
                grade(entry(8.0, "c"), 7)]     # called under, landed under
        rec = line_record(rows, 9.5)
        assert rec["settled"] == 3 and rec["hits"] == 2
        assert rec["rate"] == 66.7

    def test_the_two_sides_are_reported_apart(self):
        # One good side carries a mediocre overall number, and the reader is about to bet
        # one side, not the average of them.
        rows = [grade(entry(11.0, "a"), 8), grade(entry(11.0, "b"), 8),
                grade(entry(8.0, "c"), 7), grade(entry(8.0, "d"), 7)]
        rec = line_record(rows, 9.5)
        assert rec["over"]["called"] == 2 and rec["over"]["rate"] == 0.0
        assert rec["under"]["called"] == 2 and rec["under"]["rate"] == 100.0

    def test_pending_games_are_not_counted_as_misses(self):
        rows = [grade(entry(11.0, "a"), 12), grade(entry(11.0, "b"), None)]
        rec = line_record(rows, 9.5)
        assert rec["settled"] == 1 and rec["rate"] == 100.0

    def test_nothing_settled_is_none_rather_than_zero(self):
        # A line with no settled games is not a line that never wins, and 0% is the kind
        # of number somebody quotes back at you.
        assert line_record([grade(entry(10.0), None)], 9.5)["rate"] is None


class TestTheBandRecord:
    def test_the_quiet_band_answers_the_under_question(self):
        # The whole reason the board shows the bottom of the distribution.
        rows = [grade(entry(7.5, "a"), 6), grade(entry(8.0, "b"), 8),
                grade(entry(7.9, "c"), 11)]
        rec = band_record(rows, "quiet")
        assert rec["games"] == 3 and rec["settled"] == 3
        assert rec["under_9_5"] == 66.7

    def test_bias_says_which_way_the_model_is_wrong(self):
        # A model wrong by one corner in the SAME direction every time poisons every over
        # bet placed off it, while reading as more accurate than one wrong by two in both.
        rows = [grade(entry(8.0, "a"), 10), grade(entry(8.0, "b"), 10)]
        assert band_record(rows, "quiet")["bias"] == 2.0

    def test_a_band_with_nothing_in_it_reports_nothing_not_zero(self):
        rec = band_record([grade(entry(11.9), 12)], "quiet")
        assert rec["games"] == 0
        assert rec["avg_actual"] is None and rec["under_9_5"] is None


class TestTheWholeRecord:
    def test_pending_games_are_published_rather_than_dropped(self):
        # A record showing only what settled is one dropped fixture away from being a
        # record of the games that happened to be convenient.
        s = summarise([grade(entry(10.0, "a"), 11), grade(entry(10.0, "b"), None)])
        assert s["games"] == 2 and s["settled"] == 1 and s["pending"] == 1

    def test_bias_and_error_are_different_numbers_and_both_are_reported(self):
        # Wrong by two in both directions: no bias, real error. Reporting only the second
        # would call this model as broken as one that is wrong by two every time one way.
        s = summarise([grade(entry(10.0, "a"), 12), grade(entry(10.0, "b"), 8)])
        assert s["bias"] == 0.0
        assert s["mean_abs_error"] == 2.0

    def test_every_band_appears_even_when_empty(self):
        # So a reader can see that a band had no games, rather than wondering where it
        # went and assuming the page is broken.
        s = summarise([grade(entry(10.0), 10)])
        assert [b["band"] for b in s["bands"]] == \
            ["quiet", "below par", "middling", "busy", "very busy"]

    def test_an_empty_record_does_not_divide_by_zero(self):
        s = summarise([])
        assert s["games"] == 0 and s["bias"] is None and s["mean_abs_error"] is None


# ---------------------------------------------------------------------------
# The window the Projected page may ask for
# ---------------------------------------------------------------------------
# 21 and 28 exist so an international break can be looked past: the break empties the board
# for ten days, and "which games to watch when it comes back" cannot be answered inside a
# fortnight. They are cumulative windows, not slices — the restart week is read off the
# dates.
#
# THE CLAMP IS THE POINT OF THIS BLOCK. `days` went straight into _fixture_projections,
# which walks every team and every fixture in the window, so `?days=3650` scanned the whole
# collection on a free-tier instance. The fixture board has enforced a ceiling since it was
# written and this endpoint reached the same function without one.

def test_the_page_offers_a_window_past_an_international_break():
    import json
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[2] / "frontend/src/pages/Projections.jsx"
    line = next(l for l in src.read_text().splitlines() if l.startswith("const DAYS"))
    days = json.loads(line.split("=", 1)[1].strip().rstrip(";"))
    assert max(days) >= 21, "no window reaches past a ten-day break"


def test_every_offered_window_survives_the_clamp():
    """A day option the backend would silently shrink is a page that lies about its window.

    The picker would read 28 while the board answered 30-day-capped — or worse, a future
    option beyond the cap would show fewer games than the button promised, with nothing
    saying so.
    """
    import json
    import os
    import pathlib
    # This module tests pure grading and so never imports server; the clamp lives there.
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_corner_model")
    import server
    src = pathlib.Path(__file__).resolve().parents[2] / "frontend/src/pages/Projections.jsx"
    line = next(l for l in src.read_text().splitlines() if l.startswith("const DAYS"))
    days = json.loads(line.split("=", 1)[1].strip().rstrip(";"))
    for d in days:
        assert d <= server.BOARD_MAX_DAYS, f"{d}-day option exceeds BOARD_MAX_DAYS"
