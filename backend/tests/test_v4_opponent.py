"""Unit tests for v4: the OPPONENT's defensive style in the corner projection.

Until v4, the only thing the opposition contributed to a price was their corners-conceded
average. A side that blocks five shots a game and a side that gives up clean looks priced
identically on the same corners-against number, which is what these tests now forbid.

Two invariants carry the weight here, and they are the first two tests:

1. Production (`live_lambda`) and the backtester (`model_lambda`) are separate
   implementations of the same formula. The backtest is the only evidence that can
   justify the weight, so if they drift the backtest stops describing production.
2. `live_lambda` is DEFINED as the product of the breakdown dicts, so the explain panel
   on the fixture page cannot claim one thing while pricing quietly does another.

The rest pin the direction of the effect, the semantics of the stat (it is easy to get
`blocked_shots_against` backwards), and — most importantly — that every "we cannot tell"
path prices EXACTLY as v3 did, to the cent.
"""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    MIN_BLOCKED_GAMES, V3_BLOCKED_WEIGHT, V4_OPP_BLOCKED_WEIGHT, _intent,
    expected_lambdas, intent_breakdown, live_lambda, model_lambda, opponent_defence,
)

LG_SHOTS, LG_BLOCKED = 12.0, 2.5


def team(n=8, blocked=3.0, blocks=2.5, shots=14.0, fh_hits=None, name="T", home=True,
         corners_for=5, corners_against=5):
    """A team whose venue splits are uniform, so the expected lambda is hand-computable.

    `blocked` is blocked_shots_for — this team's own shots that got blocked (the v3
    attacking-intent stat). `blocks` is blocked_shots_against — the opposition's shots
    that got blocked, i.e. this team doing the blocking (the v4 stat). They are
    deliberately separate arguments because the whole point of v4 is that they are
    different facts about the same team.
    """
    fh_hits = n // 2 if fh_hits is None else fh_hits
    ms = []
    for i in range(n):
        m = {"home": home, "corners_for": corners_for, "corners_against": corners_against,
             "shots_for": shots, "fh_goals_for": 1 if i < fh_hits else 0,
             "opponent": "X", "date": f"2026-01-{i + 1:02d}"}
        if blocked is not None:
            m["blocked_shots_for"] = blocked
        if blocks is not None:
            m["blocked_shots_against"] = blocks
        ms.append(m)
    return {"team_id": name, "league_id": "lg", "name": name, "real_matches": ms}


def v3_price(base, t):
    """What this team priced at BEFORE v4 — the thing every neutral path must reproduce."""
    return live_lambda(base, t, "home", LG_SHOTS, LG_BLOCKED)


# --- invariant 1: the two implementations must still agree, opponent included ---
def test_live_lambda_matches_the_backtester_lambda_with_an_opponent():
    t = team(n=8, blocked=3.0, shots=14.0, fh_hits=4)               # fh rate 0.5
    opp = team(n=8, blocks=4.0, name="O", home=False)
    tf, oa = 6.0, 4.0
    live = live_lambda((tf + oa) / 2, t, "home", LG_SHOTS, LG_BLOCKED, opp, "away")
    back = model_lambda("v4", tf, oa, 14.0, LG_SHOTS, 0.5, 3.0, LG_BLOCKED,
                        V3_BLOCKED_WEIGHT, 4.0, V4_OPP_BLOCKED_WEIGHT)
    assert live == pytest.approx(back, abs=0.005)                   # live rounds to 2dp


def test_backtester_v4_with_no_opponent_data_equals_v3():
    """The fallback path has to agree across implementations too, not just the happy one."""
    args = (6.0, 4.0, 14.0, LG_SHOTS, 0.5, 3.0, LG_BLOCKED, V3_BLOCKED_WEIGHT)
    assert model_lambda("v4", *args, 0.0) == pytest.approx(model_lambda("v3", *args))


# --- invariant 2: the price is the product of the panels that explain it ---
@pytest.mark.parametrize("blocks", [1.0, 2.5, 4.0, None])
def test_live_lambda_is_the_product_of_its_breakdowns(blocks):
    t = team(blocked=3.0)
    opp = team(blocks=blocks, name="O", home=False)
    b = intent_breakdown(t, "home", LG_SHOTS, LG_BLOCKED)
    d = opponent_defence(opp, "away", LG_BLOCKED)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, opp, "away") == pytest.approx(
        round(5.0 * b["multiplier"] * b["form"] * d["multiplier"], 2), abs=0.005)


# --- the effect itself: this is the bug being fixed ---
def test_a_blocking_opponent_raises_the_projection():
    t = team(blocked=3.0)
    heavy = team(blocks=5.0, name="Heavy", home=False)     # blocks a lot -> more corners
    light = team(blocks=1.0, name="Light", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, heavy, "away") > \
           live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, light, "away")


def test_the_opponents_own_attacking_blocks_do_not_move_the_price():
    """`blocked_shots_for` on the OPPONENT is their attacking intent, not their defending.

    Reading the wrong one of the pair would still produce a plausible-looking number that
    moved with the opposition, so this pins the semantics rather than just the direction.
    """
    t = team(blocked=3.0)
    a = team(blocks=3.0, blocked=1.0, name="A", home=False)
    b = team(blocks=3.0, blocked=9.0, name="B", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, a, "away") == \
           live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, b, "away")


def test_end_to_end_two_identical_defences_that_defend_differently():
    """The user-visible bug: same corners conceded, different style, previously same price."""
    home = team(blocked=3.0, corners_for=7, corners_against=4, name="H", home=True)
    deep = team(blocks=5.0, corners_for=4, corners_against=5, name="Deep", home=False)
    open_ = team(blocks=1.0, corners_for=4, corners_against=5, name="Open", home=False)
    lam_deep = expected_lambdas(home, deep, LG_SHOTS, LG_BLOCKED)["home"]
    lam_open = expected_lambdas(home, open_, LG_SHOTS, LG_BLOCKED)["home"]
    assert lam_deep > lam_open


# --- every "cannot tell" path prices exactly as v3 did ---
def test_no_opponent_prices_exactly_as_v3():
    t = team(blocked=3.0)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED) == v3_price(5.0, t)


def test_opponent_without_the_stat_prices_exactly_as_v3():
    t = team(blocked=3.0)
    opp = team(blocks=None, name="O", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, opp, "away") == v3_price(5.0, t)


def test_thin_opponent_coverage_prices_exactly_as_v3():
    t = team(blocked=3.0)
    thin = team(n=MIN_BLOCKED_GAMES - 1, blocks=5.0, name="O", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, thin, "away") == v3_price(5.0, t)
    enough = team(n=MIN_BLOCKED_GAMES, blocks=5.0, name="O", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, enough, "away") != v3_price(5.0, t)


def test_league_without_blocked_data_prices_exactly_as_v3():
    t = team(blocked=3.0)
    opp = team(blocks=5.0, name="O", home=False)
    assert live_lambda(5.0, t, "home", LG_SHOTS, 0.0, opp, "away") == \
           live_lambda(5.0, t, "home", LG_SHOTS, 0.0)


def test_zero_weight_is_the_kill_switch():
    """Setting the weight to 0 must reproduce v3 to the cent — that is the documented
    way to turn this off if the sweep says it does not earn its place."""
    assert _intent(5.0, LG_BLOCKED, 0.0) == 1.0
    args = (6.0, 4.0, 14.0, LG_SHOTS, 0.5, 3.0, LG_BLOCKED, V3_BLOCKED_WEIGHT)
    assert model_lambda("v4", *args, 5.0, 0.0) == pytest.approx(model_lambda("v3", *args))


# --- the breakdown reports honestly ---
def test_breakdown_names_the_stat_and_its_coverage():
    opp = team(n=9, blocks=4.0, name="O", home=False)
    d = opponent_defence(opp, "away", LG_BLOCKED)
    assert d["source"] == "blocked_against"
    assert d["value"] == 4.0 and d["league_avg"] == 2.5
    assert d["weight"] == V4_OPP_BLOCKED_WEIGHT and d["covered"] == 9
    assert d["reason"] is None


@pytest.mark.parametrize("opp,venue,expect", [
    (None, "away", "no opponent supplied"),
    (team(blocks=4.0, name="O", home=False), None, "no opponent supplied"),
])
def test_breakdown_explains_a_neutral_multiplier(opp, venue, expect):
    d = opponent_defence(opp, venue, LG_BLOCKED)
    assert d["multiplier"] == 1.0 and d["reason"] == expect


def test_breakdown_explains_thin_coverage_with_the_count():
    opp = team(n=2, blocks=4.0, name="O", home=False)
    d = opponent_defence(opp, "away", LG_BLOCKED)
    assert d["multiplier"] == 1.0
    assert "2 of the opponent's games" in d["reason"] and str(MIN_BLOCKED_GAMES) in d["reason"]


def test_breakdown_explains_a_league_with_no_blocked_data():
    opp = team(blocks=4.0, name="O", home=False)
    d = opponent_defence(opp, "away", 0.0)
    assert d["multiplier"] == 1.0 and d["reason"] == "league has no blocked-shots data"


# --- bounds: an extreme opponent cannot run away with the price ---
@pytest.mark.parametrize("blocks", [0.0, 0.1, 2.5, 20.0, 500.0])
def test_the_multiplier_stays_inside_the_clamp(blocks):
    opp = team(blocks=blocks, name="O", home=False)
    d = opponent_defence(opp, "away", LG_BLOCKED)
    lo = (1.0 - V4_OPP_BLOCKED_WEIGHT) + V4_OPP_BLOCKED_WEIGHT * 0.6
    hi = (1.0 - V4_OPP_BLOCKED_WEIGHT) + V4_OPP_BLOCKED_WEIGHT * 1.5
    assert lo <= d["multiplier"] <= hi


def test_the_weight_is_below_the_attacking_term():
    """Documented reasoning, pinned: the opponent's corner concession is already half the
    base, so this term must not be trusted as far as the team's own intent."""
    assert 0.0 <= V4_OPP_BLOCKED_WEIGHT < V3_BLOCKED_WEIGHT


# --- venue: the opponent's blocking is read on the venue they are actually playing ---
def test_the_opponents_blocking_is_venue_split():
    t = team(blocked=3.0)
    opp = {"team_id": "O", "league_id": "lg", "name": "O", "real_matches": (
        team(n=6, blocks=5.0, home=True)["real_matches"]
        + team(n=6, blocks=1.0, home=False)["real_matches"])}
    at_home = live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, opp, "home")
    away = live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED, opp, "away")
    assert at_home > away
