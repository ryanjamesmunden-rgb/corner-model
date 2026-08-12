"""Unit tests for the v3 candidate lambda: blocked-shots intent replacing shots intent.
v3 is backtest-only, so the first thing these lock down is that v1 and v2 — the models
that actually price bets — are untouched."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import V3_BLOCKED_WEIGHT, _intent, model_lambda  # noqa: E402

TF, OA, FH = 6.0, 5.0, 0.6          # team corners for, opponent conceded, fh-goal rate
BASE = (TF + OA) / 2.0
FORM = 1.0 + 0.03 * (FH - 0.5)


def test_v1_is_corner_form_only():
    assert model_lambda("v1", TF, OA, 14.0, 12.0, FH, 4.0, 2.0) == BASE


def test_v2_is_unchanged_by_the_v3_arguments():
    """v2 prices real bets — passing blocked shots must not move it."""
    without = model_lambda("v2", TF, OA, 14.0, 12.0, FH)
    with_blocked = model_lambda("v2", TF, OA, 14.0, 12.0, FH, 9.0, 2.0, 0.30)
    assert without == with_blocked
    expected = BASE * (0.90 + 0.10 * (14.0 / 12.0)) * FORM
    assert without == pytest.approx(expected)


def test_v3_swaps_shots_intent_for_blocked_intent():
    lam = model_lambda("v3", TF, OA, 14.0, 12.0, FH, 3.0, 2.0)
    expected = BASE * _intent(3.0, 2.0, V3_BLOCKED_WEIGHT) * FORM
    assert lam == pytest.approx(expected)


def test_v3_ignores_shots_entirely():
    a = model_lambda("v3", TF, OA, 20.0, 12.0, FH, 3.0, 2.0)
    b = model_lambda("v3", TF, OA, 2.0, 12.0, FH, 3.0, 2.0)
    assert a == b


def test_v3_weight_scales_the_intent():
    flat = model_lambda("v3", TF, OA, 0, 0, FH, 3.0, 2.0, 0.0)
    assert flat == pytest.approx(BASE * FORM)          # zero weight = no intent at all
    heavy = model_lambda("v3", TF, OA, 0, 0, FH, 3.0, 2.0, 0.30)
    light = model_lambda("v3", TF, OA, 0, 0, FH, 3.0, 2.0, 0.05)
    assert heavy > light > flat                        # above-average blocked -> lift


def test_v3_intent_is_clamped_both_ways():
    huge = model_lambda("v3", TF, OA, 0, 0, FH, 99.0, 2.0)
    at_cap = model_lambda("v3", TF, OA, 0, 0, FH, 3.0, 2.0)     # 1.5x = the cap
    assert huge == pytest.approx(at_cap)
    tiny = model_lambda("v3", TF, OA, 0, 0, FH, 0.01, 2.0)
    at_floor = model_lambda("v3", TF, OA, 0, 0, FH, 1.2, 2.0)   # 0.6x = the floor
    assert tiny == pytest.approx(at_floor)


def test_v3_falls_back_when_blocked_data_is_missing():
    """An uncovered team must not be silently priced off a zero."""
    assert model_lambda("v3", TF, OA, 14.0, 12.0, FH, 0.0, 2.0) == BASE
    assert model_lambda("v3", TF, OA, 14.0, 12.0, FH, 3.0, 0.0) == BASE


def test_intent_is_neutral_at_the_league_average():
    assert _intent(2.0, 2.0, 0.10) == pytest.approx(1.0)
    assert _intent(2.0, 2.0, 0.30) == pytest.approx(1.0)
