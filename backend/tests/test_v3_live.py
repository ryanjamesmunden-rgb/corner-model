"""Unit tests for v3 as the LIVE pricing lambda.

The backtester (`model_lambda`) and production (`live_lambda`) are two separate
implementations of the same formula. The backtest is the entire justification for
shipping v3, so the first test here pins that they actually agree — if they drift,
the backtest stops describing what production does.

The rest pin the fallback: a team without blocked-shots history must price EXACTLY as
it does today, to the cent."""
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    MIN_BLOCKED_GAMES, V3_BLOCKED_WEIGHT, _blocked_form, _intent, _league_blocked_map,
    expected_lambdas, live_lambda, model_lambda,
)

LG_SHOTS, LG_BLOCKED = 12.0, 2.5


def team(n=8, blocked=3.0, shots=14.0, fh_hits=None, name="T", league="lg", home=True):
    """A team whose venue splits are uniform, so the expected lambda is hand-computable."""
    fh_hits = n // 2 if fh_hits is None else fh_hits
    ms = []
    for i in range(n):
        m = {"home": home, "corners_for": 5, "corners_against": 5, "shots_for": shots,
             "fh_goals_for": 1 if i < fh_hits else 0, "opponent": "X", "date": f"2026-01-{i + 1:02d}"}
        if blocked is not None:
            m["blocked_shots_for"] = blocked
        ms.append(m)
    return {"team_id": name, "league_id": league, "name": name, "real_matches": ms}


def v2_expected(base, shots, fh):
    """The formula exactly as it was before v3 — the thing the fallback must reproduce."""
    return round(base * (0.90 + 0.10 * max(0.6, min(1.5, shots / LG_SHOTS)))
                 * (1.0 + 0.03 * (fh - 0.5)), 2)


# --- the two implementations must agree ---
def test_live_lambda_matches_the_backtester_lambda():
    t = team(n=8, blocked=3.0, shots=14.0, fh_hits=4)          # fh rate 0.5
    tf, oa = 6.0, 4.0
    live = live_lambda((tf + oa) / 2, t, "home", LG_SHOTS, LG_BLOCKED)
    back = model_lambda("v3", tf, oa, 14.0, LG_SHOTS, 0.5, 3.0, LG_BLOCKED, V3_BLOCKED_WEIGHT)
    assert live == pytest.approx(back, abs=0.005)              # live rounds to 2dp


def test_live_lambda_uses_the_blocked_term_not_the_shots_term():
    heavy = team(blocked=4.0, shots=14.0)
    light = team(blocked=1.5, shots=14.0)
    assert live_lambda(5.0, heavy, "home", LG_SHOTS, LG_BLOCKED) > \
           live_lambda(5.0, light, "home", LG_SHOTS, LG_BLOCKED)
    # shots no longer move the price once blocked shots are available
    a = live_lambda(5.0, team(blocked=3.0, shots=20.0), "home", LG_SHOTS, LG_BLOCKED)
    b = live_lambda(5.0, team(blocked=3.0, shots=6.0), "home", LG_SHOTS, LG_BLOCKED)
    assert a == b


def test_weight_is_the_swept_value():
    assert V3_BLOCKED_WEIGHT == 0.15


# --- fallback: unchanged pricing for teams the backfill hasn't reached ---
def test_team_without_blocked_data_prices_exactly_as_before():
    t = team(n=8, blocked=None, shots=14.0, fh_hits=4)
    assert live_lambda(5.0, t, "home", LG_SHOTS, LG_BLOCKED) == v2_expected(5.0, 14.0, 0.5)


def test_league_without_blocked_data_prices_exactly_as_before():
    t = team(n=8, blocked=3.0, shots=14.0, fh_hits=4)
    assert live_lambda(5.0, t, "home", LG_SHOTS, 0.0) == v2_expected(5.0, 14.0, 0.5)


def test_thin_blocked_history_falls_back_rather_than_trusting_it():
    """MIN_BLOCKED_GAMES games of data must not swing a live price."""
    thin = team(n=MIN_BLOCKED_GAMES - 1, blocked=9.0, shots=14.0, fh_hits=0)
    assert _blocked_form(thin, "home") is None
    assert live_lambda(5.0, thin, "home", LG_SHOTS, LG_BLOCKED) == v2_expected(5.0, 14.0, 0.0)
    enough = team(n=MIN_BLOCKED_GAMES, blocked=9.0, shots=14.0, fh_hits=0)
    assert _blocked_form(enough, "home") == 9.0
    assert live_lambda(5.0, enough, "home", LG_SHOTS, LG_BLOCKED) != v2_expected(5.0, 14.0, 0.0)


def test_partially_covered_team_averages_only_the_covered_games():
    t = team(n=6, blocked=None, shots=14.0)
    for i, m in enumerate(t["real_matches"]):
        if i < 5:
            m["blocked_shots_for"] = 4.0            # 5 covered, 1 blank
    assert _blocked_form(t, "home") == 4.0          # the blank is not a zero


def test_no_matches_at_all_returns_bare_base():
    empty = {"team_id": "e", "league_id": "lg", "name": "E", "real_matches": []}
    assert live_lambda(5.0, empty, "home", LG_SHOTS, LG_BLOCKED) == 5.0


# --- league map ---
def test_league_blocked_map_skips_uncovered_leagues_and_nulls():
    teams = [team(blocked=3.0, league="a"), team(blocked=None, league="b")]
    m = _league_blocked_map(teams)
    assert m["a"] == 3.0
    assert "b" not in m                             # falls back to shots intent


def test_league_blocked_map_ignores_blank_matches_within_a_league():
    t = team(n=4, blocked=2.0, league="a")
    t["real_matches"].append({"home": True, "corners_for": 5, "corners_against": 5,
                              "shots_for": 12, "fh_goals_for": 0, "opponent": "X",
                              "date": "2026-02-01"})     # no blocked_shots_for
    assert _league_blocked_map([t])["a"] == 2.0


# --- fixture-level entry point ---
def test_expected_lambdas_defaults_to_the_old_behaviour():
    """Callers that don't pass a league blocked average (e.g. the odds seeder) are
    unaffected — pricing there is identical to before."""
    h, a = team(blocked=3.0, home=True), team(blocked=3.0, home=False)
    before = expected_lambdas(h, a, LG_SHOTS)
    assert before["home"] == pytest.approx(expected_lambdas(h, a, LG_SHOTS, 0.0)["home"])


def test_expected_lambdas_moves_when_blocked_average_is_supplied():
    h, a = team(blocked=4.5, home=True), team(blocked=1.0, home=False)
    plain = expected_lambdas(h, a, LG_SHOTS)
    v3 = expected_lambdas(h, a, LG_SHOTS, LG_BLOCKED)
    assert v3["home"] != plain["home"]
    assert v3["total"] == pytest.approx(v3["home"] + v3["away"], abs=0.01)


def test_intent_neutral_at_league_average():
    assert _intent(LG_BLOCKED, LG_BLOCKED, V3_BLOCKED_WEIGHT) == pytest.approx(1.0)
