"""What the Daily 2 selects on, after the search for a ranking failed.

Every candidate was replayed walk-forward and scored by residual:

    chase_score +0.02   lambda_only +0.01   no_opp_fh +0.03   RANDOM flat
    venue_delta +9.1 -> FLAT once lambda was built venue-split (artifact confirmed)
    consistency_only +7.9, against a KNOWN-SPURIOUS 7.5 from estimation error alone

So the rule is stated, not discovered: a quality bar, then model probability. These pin
that it stays stated — and in particular that `consistency` is used as a FILTER and never
as a ranking, which is the distinction the whole result rests on."""
import inspect
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import (  # noqa: E402
    DAILY_MIN_CONSISTENCY, DAILY_MIN_VENUE_GAMES, DAILY_PICK_RULE,
    daily_pick_order, daily_pick_qualifies,
)


def spot(hits=5, of=5, prob=70.0, chase=9.9):
    return {"consistency": hits, "consistency_of": of, "prob": prob, "chase_score": chase}


# --- the bar ---
def test_a_reliable_spot_qualifies():
    assert daily_pick_qualifies(spot(hits=4, of=5)) is True


def test_an_unreliable_spot_is_dropped_however_big_its_chase_score():
    assert daily_pick_qualifies(spot(hits=2, of=5, chase=99.0)) is False


def test_a_thin_venue_record_is_dropped():
    """3 of 3 looks perfect and means very little."""
    assert daily_pick_qualifies(spot(hits=3, of=3)) is False
    assert DAILY_MIN_VENUE_GAMES == 4


def test_the_bar_is_exactly_four_of_five():
    assert DAILY_MIN_CONSISTENCY == 0.8
    assert daily_pick_qualifies(spot(hits=4, of=5)) is True
    assert daily_pick_qualifies(spot(hits=3, of=5)) is False


def test_missing_fields_do_not_raise():
    assert daily_pick_qualifies({}) is False


# --- the order ---
def test_order_is_model_probability_not_chase_score():
    """The falsified ranking must not be what decides the picks."""
    confident_but_low_chase = spot(prob=80.0, chase=1.0)
    unconfident_but_high_chase = spot(prob=55.0, chase=99.0)
    assert daily_pick_order(confident_but_low_chase) > daily_pick_order(unconfident_but_high_chase)


def test_the_rule_is_named_for_what_it_actually_does():
    assert DAILY_PICK_RULE == "quality_bar_then_probability"


def test_the_shortlist_sorts_by_the_stated_order():
    src = inspect.getsource(server._daily_shortlist)
    assert "daily_pick_order" in src and "daily_pick_qualifies" in src
    assert "chase_score" not in src


def test_a_thin_day_returns_fewer_rather_than_topping_up():
    """The bar is absolute — same principle as the fixture board."""
    src = inspect.getsource(server._daily_shortlist)
    assert "yields fewer than" in src


def test_the_null_is_recorded_where_the_rule_is_defined():
    """So nobody re-introduces a 'score' without seeing that this was measured."""
    src = inspect.getsource(server)
    block = src[src.index("# WHAT THE DAILY 2 SELECTS ON"):src.index("DAILY_PICK_RULE =")]
    assert "RANDOM" in block and "7.5" in block
    assert "STATED rule, not a discovered edge" in block


def test_consistency_is_documented_as_a_filter_not_a_ranking():
    src = inspect.getsource(server)
    block = src[src.index("# WHAT THE DAILY 2 SELECTS ON"):src.index("DAILY_PICK_RULE =")]
    assert "RELIABILITY FILTER" in block and "NOT as a ranking" in block
