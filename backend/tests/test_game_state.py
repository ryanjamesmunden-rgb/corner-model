"""The game-state verdict: chase spot, neutral, caution, avoid.

WHAT THESE GUARD. The verdict sits beside a price on the value board, so a wrong one is
read as advice. The cases below are the weekend that prompted it (20-22 Nov 2026) in
miniature: a side swamped by a much stronger opponent, a side that goes ahead and sits
deep, a side that does not shoot, and the one that pays — a weaker side, not swamped,
whose corners go UP when it trails.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_state as gs  # noqa: E402
from odds_feed import feed_doc  # noqa: E402


def g(cf, gf=1, ga=1, fhf=0, fha=0, shots=12):
    return {"corners_for": cf, "corners_against": 5, "goals_for": gf, "goals_against": ga,
            "fh_goals_for": fhf, "fh_goals_against": fha, "shots_for": shots}


def trailing(cf, **kw):
    return g(cf, gf=0, ga=1, fhf=0, fha=1, **kw)


def leading(cf, **kw):
    return g(cf, gf=1, ga=0, fhf=1, fha=0, **kw)


def level(cf, **kw):
    return g(cf, **kw)


def side(gf, ga, n=10, shots=12):
    """A history scoring gf and conceding ga every game, all level at half-time."""
    return [g(5, gf=gf, ga=ga, shots=shots) for _ in range(n)]


def half_goal_better():
    """Goal difference +0.5 a game: alternating 2-1 wins and 1-1 draws."""
    return [g(5, gf=2, ga=1) if i % 2 else g(5, gf=1, ga=1) for i in range(10)]


class TestTheTraitIsAgainstTheSidesOwnAverage:
    def test_a_side_that_wins_more_when_behind_is_a_chaser(self):
        hist = [trailing(8) for _ in range(6)] + [level(4) for _ in range(10)]
        t = gs.state_trait(hist)
        assert t["trail"]["games"] == 6
        assert t["trail"]["raw"] > 1.4
        # SHRUNK, so it sits between the raw ratio and 1.0
        assert 1.0 < t["trail"]["ratio"] < t["trail"]["raw"]

    def test_shrinkage_pulls_a_two_game_trait_towards_no_effect(self):
        few = gs.state_trait([trailing(10), trailing(10)] + [level(4)] * 10)
        many = gs.state_trait([trailing(10)] * 10 + [level(4)] * 10)
        def pulled(t):      # share of the raw effect the shrinkage takes away
            return (t["trail"]["raw"] - t["trail"]["ratio"]) / (t["trail"]["raw"] - 1.0)
        assert pulled(few) > pulled(many)

    def test_games_without_a_half_time_score_are_in_no_state(self):
        hist = [{"corners_for": 6}] * 5
        t = gs.state_trait(hist)
        assert t["games"] == 5 and t["trail"]["games"] == 0 and t["lead"]["games"] == 0

    def test_empty_history_says_nothing_rather_than_failing(self):
        t = gs.state_trait([])
        assert t["games"] == 0 and t["base"] is None


class TestVerdicts:
    def test_the_bayern_game_is_avoid(self):
        # opponent two goals a game better: the side never gets the ball to chase with
        v = gs.side_verdict(side(0, 1), side(2, 1), league_shots=12)
        assert v["verdict"] == "avoid"
        assert "mismatch" in v["flags"]
        assert v["gap"] >= gs.MISMATCH_GD

    def test_a_side_that_does_not_shoot_is_avoid(self):
        v = gs.side_verdict(side(1, 1, shots=6), side(1, 1), league_shots=12)
        assert v["verdict"] == "avoid" and "blunt" in v["flags"]

    def test_zero_shots_are_missing_not_blunt(self):
        # sync_real writes `shots or 0`, so 0 is usually a provider gap
        v = gs.side_verdict(side(1, 1, shots=0), side(1, 1), league_shots=12)
        assert "blunt" not in v["flags"] and v["shots"] is None

    def test_a_weaker_side_that_chases_is_the_spot(self):
        mine = [trailing(9) for _ in range(6)] + [level(5, gf=1, ga=1) for _ in range(10)]
        theirs = half_goal_better()
        v = gs.side_verdict(mine, theirs, league_shots=12)
        assert v["verdict"] == "chase_spot", v
        assert "chaser" in v["flags"] and "close" in v["flags"]
        assert v["reasons"][0].startswith("Underdog or level")

    def test_a_chaser_against_a_mismatch_is_still_avoid(self):
        mine = [trailing(9) for _ in range(6)] + [level(5, gf=0, ga=2) for _ in range(10)]
        v = gs.side_verdict(mine, side(2, 1), league_shots=12)
        assert v["verdict"] == "avoid"

    def test_a_side_that_sits_on_a_lead_is_caution(self):
        mine = [leading(2) for _ in range(6)] + [level(6) for _ in range(10)]
        v = gs.side_verdict(mine, side(1, 1), league_shots=12)
        assert v["verdict"] == "caution" and "parker" in v["flags"]

    def test_too_little_history_is_neutral_not_a_guess(self):
        v = gs.side_verdict([trailing(12)] * 2 + [level(4)] * 3, side(1, 1), league_shots=12)
        assert v["verdict"] == "neutral"
        assert "chaser" not in v["flags"]

    def test_every_verdict_says_it_is_unmeasured(self):
        assert gs.side_verdict(side(1, 1), side(1, 1), 12)["measured"] is False

    def test_market_price_is_a_fact_beside_the_verdict_not_part_of_it(self):
        base = gs.side_verdict(side(1, 1), side(1, 1), 12)
        short = gs.side_verdict(side(1, 1), side(1, 1), 12, opp_win_prob=0.75)
        assert "market_short" in short["flags"]
        assert short["verdict"] == base["verdict"]


def mw(book, h, d, a):
    return {"name": book, "bets": [{"name": "Match Winner", "values": [
        {"value": "Home", "odd": h}, {"value": "Draw", "odd": d}, {"value": "Away", "odd": a}]}]}


class TestMatchWinnerIsReadFromTheSameResponse:
    def test_consensus_probabilities_with_the_margin_taken_off(self):
        mo = gs.match_winner({"bookmakers": [mw("A", 1.40, 5.0, 8.0), mw("B", 1.45, 4.8, 7.5)]})
        assert mo["books"] == 2
        assert abs(mo["home"] + mo["draw"] + mo["away"] - 1.0) < 1e-3
        assert mo["home"] > gs.MARKET_SHORT

    def test_a_book_missing_an_outcome_is_ignored(self):
        partial = {"name": "C", "bets": [{"name": "Match Winner", "values": [
            {"value": "Home", "odd": 2.0}, {"value": "Away", "odd": 3.0}]}]}
        assert gs.match_winner({"bookmakers": [partial]}) is None

    def test_feed_doc_carries_it_without_touching_the_corner_prices(self):
        doc = feed_doc("fx1", 123, {"bookmakers": [mw("A", 2.0, 3.4, 3.8)]}, "2026-11-22")
        assert doc["match_odds"]["books"] == 1
        assert doc["odds"] == {}
