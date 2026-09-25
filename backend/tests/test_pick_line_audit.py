"""Recovering the model's lambda from the probability it printed.

WHY THIS EXISTS. Three explanations for the ledger are already eliminated: the model is
calibrated (+0.1 over 11,590 replayed spots), the grading is sound (44/44 checked by team
id, zero regraded), and line/probability cannot disagree at write time because
_chase_board derives both from one lam. What is left is whether that lam was RIGHT for
the spots actually published — and the only trace of it is the frozen `model_prob`.

So the whole result rests on one inversion. If it is off, the gap it reports is off by
the same amount and reads as a finding about the model. These test the inversion first
and the arithmetic built on it second.

WHAT THEY GUARD:

  - The round trip. nb_ge(line, implied_lambda(line, p)) must return p. Anything else
    means the number every table below prints is not the model's lambda.
  - A probability the bracket cannot produce must be None, not a clamped endpoint. An
    endpoint looks exactly like a real estimate and would drag a bucket's mean toward
    whichever end it hit.
  - The gap's sign. Positive must mean lambda was too HIGH — the direction is the entire
    conclusion, and a flipped sign would send someone to fix the opposite problem.
  - The line rule tripwire, BOTH WAYS. It must hold by construction, so a violation means
    a pick was rewritten after pricing — it has to fire, or it is not a tripwire. And it
    must NOT fire on a pick whose stored probability, rounded to the 1dp every writer
    stores, straddles the rule's own boundary. The first version compared the midpoint of
    that rounding bucket and reported two correctly-priced 3+ picks as tampering, which
    under this file's own rule voided every other number in the audit. A tripwire more
    precise than the data it reads does not detect tampering, it invents it.
  - The verdict naming the right cause. Its three branches point at three different fixes
    — the max(3, ...) floor, the inputs, or nothing at all.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit_pick_lines import (  # noqa: E402
    group, implied_band, implied_lambda, line_for, row_for, rule_holds, summarise, verdict,
)
from server import nb_ge  # noqa: E402


def pick(line=3, prob=75.3, corners=2, **kw):
    gradeable = isinstance(corners, (int, float)) and not isinstance(corners, bool)
    base = {"auto": True, "line": line, "model_prob": prob, "result_corners": corners,
            "status": ("won" if corners >= line else "lost") if gradeable else "pending",
            "venue": "home", "league_id": "eng-pl", "team": "Arsenal",
            "date": "2026-09-01"}
    base.update(kw)
    return base


class TestTheInversionIsExact:
    def test_it_round_trips_through_nb_ge(self):
        # The load-bearing assertion. Every corner figure in every table is this number.
        for line in (3, 4, 5, 6, 7):
            for lam in (3.2, 4.0, 5.5, 7.1, 9.0):
                p = nb_ge(line, lam) * 100
                if not (0.5 < p < 99.5):
                    continue
                assert abs(implied_lambda(line, p) - lam) < 1e-6, (line, lam)

    def test_a_higher_probability_at_one_line_means_a_higher_lambda(self):
        assert implied_lambda(3, 60.0) < implied_lambda(3, 75.0) < implied_lambda(3, 90.0)

    def test_the_same_probability_at_a_higher_line_means_a_higher_lambda(self):
        # 75% of clearing 5+ takes a far better side than 75% of clearing 3+.
        assert implied_lambda(5, 75.0) > implied_lambda(3, 75.0)

    def test_the_published_numbers_land_where_the_argument_said(self):
        # The 3+ bucket promised 75.3%, which the write-up reads as "lambda about 4".
        # If that is wrong the whole line of reasoning is wrong.
        assert 3.5 < implied_lambda(3, 75.3) < 4.5


class TestItRefusesRatherThanClamps:
    def test_a_probability_outside_the_bracket_is_none(self):
        # A silently clamped endpoint reads as a real estimate and moves a bucket's mean.
        assert implied_lambda(3, 99.9999) is None

    def test_certainty_either_way_is_none(self):
        assert implied_lambda(3, 0.0) is None
        assert implied_lambda(3, 100.0) is None

    def test_junk_is_none_rather_than_an_exception(self):
        assert implied_lambda(None, 75.0) is None
        assert implied_lambda(3, None) is None
        assert implied_lambda(3, "seventy") is None
        assert implied_lambda(-1, 75.0) is None


class TestARowOnlyFormsWhenItCanContribute:
    def test_a_pick_with_no_result_is_dropped(self):
        assert row_for(pick(corners=None)) is None

    def test_a_boolean_result_is_not_a_corner_count(self):
        assert row_for(pick(corners=True)) is None

    def test_a_pick_with_no_probability_is_dropped(self):
        assert row_for(pick(prob=None)) is None

    def test_x_plus_includes_x(self):
        assert row_for(pick(line=3, corners=3))["hit"] == 1
        assert row_for(pick(line=3, corners=2))["hit"] == 0


class TestTheGapPointsTheRightWay:
    def test_positive_means_lambda_was_too_high(self):
        # The direction IS the conclusion. Flipped, it sends someone to fix the opposite.
        r = row_for(pick(line=3, prob=75.3, corners=2))
        assert r["gap"] > 0
        assert r["lam"] > r["corners"]

    def test_negative_means_the_team_beat_the_estimate(self):
        assert row_for(pick(line=3, prob=75.3, corners=8))["gap"] < 0

    def test_a_bucket_averages_both_the_estimate_and_the_outcome(self):
        s = summarise([row_for(pick(corners=2)), row_for(pick(corners=6))])
        assert s["n"] == 2
        assert abs(s["corners"] - 4.0) < 1e-9
        assert abs(s["gap"] - (s["lam"] - s["corners"])) < 1e-9

    def test_an_empty_bucket_is_none_rather_than_a_divide_by_zero(self):
        assert summarise([]) is None


class TestTheTripwire:
    def test_the_rule_holds_for_a_pick_priced_normally(self):
        # line = max(3, round(lam) - 1), and _chase_board derives both from one lam, so
        # a real pick always satisfies it.
        for lam in (4.0, 5.4, 6.6, 8.2):
            line = line_for(lam)
            assert row_for(pick(line=line, prob=nb_ge(line, lam) * 100))["rule_ok"]

    def test_the_floor_holds_at_the_bottom(self):
        # round(3.2) - 1 = 2, and the floor lifts it to 3. This is the case the whole 3+
        # hypothesis is about, so it must be the rule, not an exception to it.
        assert line_for(3.2) == 3
        assert line_for(2.0) == 3

    def test_a_rewritten_pick_is_caught(self):
        # A pick stored at 3+ whose probability implies a lambda of ~9 cannot have been
        # priced that way. If this does not fire, the tripwire is decorative.
        r = row_for(pick(line=3, prob=nb_ge(3, 9.0) * 100))
        assert r["rule_ok"] is False

    def test_the_rule_is_read_with_the_same_rounding_production_uses(self):
        # Python's round() is banker's: round(4.5) is 4, so a lam of exactly 4.5 gives
        # max(3, 3) = 3. Every writer in server.py calls that same round(). A restatement
        # that rounded half up would disagree with production at this exact boundary —
        # which is the boundary the two reported violations sat on.
        assert line_for(4.5) == 3
        assert line_for(4.51) == 4
        assert line_for(5.5) == 5


class TestTheStoredProbabilityIsRounded:
    """The bug that voided a live audit.

    Writers store `round(p * 100, 1)`. Inverting that as though it were exact makes the
    check finer than the data, and near the rule's boundary the rounding bucket straddles
    it — so the midpoint lands on the wrong side of a rule that production applied
    correctly.
    """

    def test_the_band_brackets_the_stored_number(self):
        lo, hi = implied_band(3, 77.6)
        assert lo < implied_lambda(3, 77.6) < hi
        assert nb_ge(3, lo) * 100 < 77.6 < nb_ge(3, hi) * 100

    def test_the_straddling_case_from_the_live_run_is_not_a_violation(self):
        # Brighton and Servette FC, both 3+, both inverting to λ 4.50. The band is
        # [4.4988, 4.5081]: its lower half gives line 3 and its upper half line 4, so the
        # stored 3 is consistent and there is nothing to explain.
        lo, hi = implied_band(3, 77.6)
        assert line_for(lo) == 3 and line_for(hi) == 4      # it really does straddle
        assert rule_holds(3, 77.6) is True
        assert row_for(pick(line=3, prob=77.6, corners=4))["rule_ok"] is True

    def test_a_real_violation_still_fires_across_the_whole_band(self):
        # Rounding buys about 0.005 of a corner. It must not excuse a pick that is wrong
        # by whole corners, or the tripwire has been turned off rather than fixed.
        prob = nb_ge(3, 9.0) * 100
        assert rule_holds(3, round(prob, 1)) is False

    def test_every_line_the_board_publishes_survives_a_1dp_round_trip(self):
        # The end-to-end guard: price a lam the way production does, round the probability
        # the way production stores it, read it back. No stored pick may read as tampering.
        lam = 2.0
        while lam <= 12.0:
            line = line_for(lam)
            stored = round(nb_ge(line, lam) * 100, 1)
            assert rule_holds(line, stored), (lam, line, stored)
            lam = round(lam + 0.01, 2)

    def test_an_unusable_probability_is_not_reported_as_tampering(self):
        # row_for drops these rows anyway; calling them violations would put a scare in
        # the output for a pick that contributes nothing to any table.
        assert rule_holds(3, None) is True
        assert rule_holds(3, 100.0) is True


def bucket(n, line, prob, corners):
    return [row_for(pick(line=line, prob=prob, corners=corners)) for _ in range(n)]


class TestTheVerdictNamesTheRightCause:
    def test_a_small_gap_blames_nothing(self):
        rows = bucket(20, 3, 75.3, 4)
        by_line = group(rows, lambda r: r["line"])
        out = verdict(by_line, summarise(rows))
        assert "Lambda is RIGHT" in out and "unlucky" in out

    def test_a_gap_only_at_three_blames_the_floor(self):
        rows = bucket(15, 3, 75.3, 2) + bucket(20, 5, 66.1, 6)
        out = verdict(group(rows, lambda r: r["line"]), summarise(rows))
        assert "THE GAP IS AT THE 3+ LINE" in out
        assert "floor" in out.lower()
        assert "do not retune lambda" in out

    def test_a_gap_everywhere_blames_the_inputs(self):
        rows = bucket(15, 3, 75.3, 2) + bucket(20, 5, 66.1, 3)
        out = verdict(group(rows, lambda r: r["line"]), summarise(rows))
        assert "ACROSS THE BOARD" in out

    def test_nothing_gradeable_says_so(self):
        assert "no conclusion" in verdict({}, None)
