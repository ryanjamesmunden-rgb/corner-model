"""The calibration harness, tested on the parts that decide what it concludes.

WHY THESE TESTS AND NOT OTHERS. A measurement script that is wrong does not crash — it
prints a confident number and someone retunes a model on it. The failures worth guarding
here are the ones that produce a clean, plausible, wrong answer:

  - A VOID counted as a loss. Voids are picks that never happened; scoring them as 0
    drags the actual hit rate down and manufactures exactly the overconfidence this is
    supposed to detect.
  - A pick with no stored probability quietly defaulted to something. There is no honest
    default: the whole point is the number that was printed BEFORE kick-off.
  - The result and the status disagreeing, and the harness believing the label. The
    corner count is the primitive; a settlement bug should surface, not be inherited.
  - A normal-approximation interval. At n=44 and a rate near 0.8 it runs past 100%, and
    an interval that cannot be exceeded can never say the promise is outside it.
  - The quality bar reading a bare fraction. 3 of 3 and 4 of 5 are both 1.0 and 0.8, and
    only one of each pair clears DAILY_MIN_VENUE_GAMES. Getting this wrong makes the
    replay describe a selection production never made.
  - The verdict naming the wrong culprit. Its three cases point at three different fixes
    — retune the model, change what the Daily 2 selects on, or do nothing — so a case
    boundary that is off sends the next piece of work in the wrong direction.
"""
import math
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from measure_calibration import (  # noqa: E402
    BAR_MIN_OF, BAR_MIN_RATE, band_keys, band_of, hit_of, ledger_rows, predicted_of,
    qualifying, summarise, top_per_day, verdict, wilson,
)


def pick(**kw):
    base = {"auto": True, "line": 4, "model_prob": 75.0, "status": "won",
            "result_corners": 6, "date": "2026-09-01", "team": "Arsenal"}
    base.update(kw)
    return base


def spot(prob=75.0, hit=1, line=4, date="2026-09-01", consistency=1.0, of=5):
    return {"prob": prob, "hit": hit, "line": line, "date": date,
            "consistency": consistency, "consistency_of": of}


# --------------------------------------------------------------------------
# What counts as an answer
# --------------------------------------------------------------------------

class TestAVoidIsNotALoss:
    def test_a_void_has_no_answer(self):
        # The game did not produce the event either way. Scoring it 0 is the single
        # easiest way to invent an overconfidence finding out of nothing.
        assert hit_of(pick(status="void", result_corners=None)) is None

    def test_a_pending_pick_has_no_answer(self):
        assert hit_of(pick(status="pending", result_corners=None)) is None

    def test_voids_are_dropped_and_counted_rather_than_scored(self):
        rows, dropped = ledger_rows([pick(), pick(status="void", result_corners=None)])
        assert len(rows) == 1
        assert dropped == {"not settled or void": 1}


class TestTheResultOutranksTheLabel:
    def test_the_corner_count_decides(self):
        assert hit_of(pick(line=4, result_corners=4)) == 1
        assert hit_of(pick(line=4, result_corners=3)) == 0

    def test_a_line_stored_as_x_plus_includes_the_line_itself(self):
        # "4+" means four or more. An off-by-one here reads as a 4-6 point calibration
        # gap on the exact lines the card prints, which is the size of the effect being
        # investigated.
        assert hit_of(pick(line=4, result_corners=4)) == 1

    def test_a_status_that_contradicts_the_result_does_not_win(self):
        # If settlement ever mislabels one, the harness should show the disagreement in
        # its numbers rather than quietly adopting the label.
        assert hit_of(pick(line=4, result_corners=2, status="won")) == 0

    def test_the_status_is_used_when_there_is_no_result(self):
        assert hit_of(pick(result_corners=None, status="won")) == 1
        assert hit_of(pick(result_corners=None, status="lost")) == 0

    def test_a_boolean_is_not_a_corner_count(self):
        # True == 1 in Python, so a stray boolean would grade as "1 corner" and score a
        # 4+ pick as a loss without anything looking wrong.
        assert hit_of(pick(result_corners=True, status="won")) == 1


class TestThePromiseIsTheOneThatWasPrinted:
    def test_the_frozen_probability_is_used(self):
        assert predicted_of(pick(model_prob=77.5)) == 77.5

    def test_an_older_pick_falls_back_to_the_stored_price(self):
        assert predicted_of(pick(model_prob=None, model_odds=1.25)) == 80.0

    def test_a_pick_with_no_probability_at_all_is_dropped_not_defaulted(self):
        assert predicted_of(pick(model_prob=None, model_odds=None)) is None
        rows, dropped = ledger_rows([pick(model_prob=None, model_odds=None)])
        assert rows == []
        assert dropped == {"no stored probability": 1}

    def test_a_nonsense_probability_is_refused(self):
        assert predicted_of(pick(model_prob=0, model_odds=None)) is None
        assert predicted_of(pick(model_prob=140.0, model_odds=None)) is None


# --------------------------------------------------------------------------
# The interval
# --------------------------------------------------------------------------

class TestTheIntervalCanActuallyBeExceeded:
    def test_it_never_runs_past_the_ends(self):
        # The normal approximation gives 100 +/- 0 at 10/10 and 0.80 +/- 0.24 at 44
        # games, both of which make "the promise is outside the interval" unreachable.
        for hits, n in ((10, 10), (0, 10), (44, 44), (35, 44)):
            lo, hi = wilson(hits, n)
            assert 0.0 <= lo <= hi <= 100.0, (hits, n, lo, hi)

    def test_a_perfect_record_still_admits_doubt(self):
        lo, hi = wilson(5, 5)
        assert lo < 100.0 and hi == 100.0

    def test_the_published_record_reproduces(self):
        # 23 of 44 — the number on the card as of 2026-09-21. If this moves, the
        # arithmetic under every conclusion drawn from it has moved.
        lo, hi = wilson(23, 44)
        assert math.isclose(lo, 37.5, abs_tol=0.5)
        assert math.isclose(hi, 66.7, abs_tol=0.5)

    def test_a_77_percent_promise_is_outside_that_interval(self):
        # The whole finding, in one assertion: the card's 1.29 implies 77.5% and 44
        # games cannot support it.
        s = summarise([{"prob": 77.5, "hit": 1, "line": 4}] * 23
                      + [{"prob": 77.5, "hit": 0, "line": 4}] * 21)
        assert s["n"] == 44 and s["hits"] == 23
        assert s["residual"] < -20
        assert s["covers"] is False

    def test_an_empty_sample_is_none_rather_than_a_divide_by_zero(self):
        assert summarise([]) is None
        assert wilson(0, 0) == (0.0, 100.0)


class TestBands:
    def test_the_card_prices_land_where_they_should(self):
        # 1.42 -> 70.4, 1.36 -> 73.5, 1.29 -> 77.5. The middle two must share a band or
        # the table splits three prices that are making the same claim.
        assert band_of(70.4) == "65-72.5%"
        assert band_of(73.5) == band_of(77.5) == "72.5-80%"

    def test_a_band_edge_is_labelled_with_a_number_a_row_can_have(self):
        # An edge of 72.5 rounded to "72" in the label puts rows at 72.3 in a band whose
        # name excludes them, and the table can no longer be checked against the card.
        assert "65-72%" not in band_keys()

    def test_every_band_a_row_can_fall_into_is_printed(self):
        keys = set(band_keys())
        for p in (1.0, 50.0, 65.0, 72.5, 80.0, 87.5, 99.9, 100.0):
            assert band_of(p) in keys, p


# --------------------------------------------------------------------------
# Replaying the selection production actually makes
# --------------------------------------------------------------------------

class TestTheQualityBarNeedsBothNumbers:
    def test_a_short_run_does_not_clear_the_bar_on_a_perfect_rate(self):
        # 3 of 3 is 1.0. The live bar wants four venue games before it believes a rate,
        # and a harness that only reads the fraction lets these through.
        assert qualifying([spot(consistency=1.0, of=3)]) == []

    def test_four_of_five_clears_it(self):
        assert len(qualifying([spot(consistency=0.8, of=5)])) == 1

    def test_a_long_run_at_a_poor_rate_does_not_clear_it(self):
        assert qualifying([spot(consistency=0.6, of=5)]) == []

    def test_the_bar_matches_the_one_the_live_selection_uses(self):
        # These are restated in the harness so the replay can apply them. If server.py
        # moves them and this file does not, the replay silently describes a selection
        # that was never made.
        import server
        assert BAR_MIN_OF == server.DAILY_MIN_VENUE_GAMES
        assert BAR_MIN_RATE == server.DAILY_MIN_CONSISTENCY


class TestTopPerDay:
    def test_it_takes_the_most_confident_of_each_day_not_of_the_whole_set(self):
        spots = [spot(prob=90, date="d1"), spot(prob=60, date="d1"),
                 spot(prob=55, date="d2"), spot(prob=50, date="d2")]
        got = sorted(r["prob"] for r in top_per_day(spots, top_n=1))
        assert got == [55, 90]

    def test_a_thin_day_yields_what_it_has_rather_than_topping_up(self):
        # The live rule is absolute: a day with one qualifying spot posts one pick.
        spots = [spot(prob=90, date="d1"), spot(prob=80, date="d2"), spot(prob=70, date="d2")]
        assert len(top_per_day(spots, top_n=2)) == 3

    def test_an_empty_set_is_empty_rather_than_a_crash(self):
        assert top_per_day([]) == []


# --------------------------------------------------------------------------
# The sentence someone will act on
# --------------------------------------------------------------------------

def band(n, prob, actual_rate):
    hits = round(n * actual_rate)
    return summarise([{"prob": prob, "hit": 1, "line": 4}] * hits
                     + [{"prob": prob, "hit": 0, "line": 4}] * (n - hits))


class TestTheVerdictNamesTheRightCulprit:
    def test_calibrated_everywhere_blames_nothing(self):
        s = band(2000, 75.0, 0.75)
        out = verdict(s, s, band(400, 75.0, 0.75))
        assert "CALIBRATED" in out
        assert "small-sample" in out

    def test_a_uniform_gap_blames_the_model(self):
        # Off by the same amount with no selection at all, so sorting is not the story.
        s = band(2000, 75.0, 0.66)
        out = verdict(s, s, band(400, 75.0, 0.66))
        assert "THE MODEL IS OFF EVERYWHERE" in out
        assert "dispersion" in out

    def test_a_gap_that_only_appears_at_the_top_blames_the_selection(self):
        # The case nobody looks for: the model is fine, and sorting on an estimated
        # probability is what costs the money.
        out = verdict(band(2000, 75.0, 0.75), band(900, 75.0, 0.75), band(400, 75.0, 0.60))
        assert "THE SELECTION BLEEDS" in out
        assert "do not retune" in out

    def test_a_thin_replay_refuses_to_decide(self):
        out = verdict(band(2000, 75.0, 0.75), band(900, 75.0, 0.75), band(8, 75.0, 0.25))
        assert "too few" in out

    def test_nothing_replayed_says_so(self):
        assert "not enough" in verdict(None, None, None)
