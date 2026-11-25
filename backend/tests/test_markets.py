"""Unders, and both teams over a line.

MOST OF THIS FILE IS ABOUT ONE NUMBER: the factor that turns two single-side probabilities
into a joint one. P(home >= 4) x P(away >= 4) is only the right answer if the two sides'
corner counts are independent, and on a sample where one side dominates the game they are
not — the measured joint comes out at about three quarters of the independent product. At
Bradford v Barnsley's lambdas that is the difference between a fair price of 1.80 and one
of 2.47, which is the difference between a bet and a mistake.

So the tests care about the direction being right, the shrinkage being real, and the thing
refusing to answer when it has not got the games to answer with.
"""
import math

import markets

NB_R = 11


def nb_pmf(k, lam, r=NB_R):
    p = r / (r + lam)
    return (math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1))
            * (p ** r) * ((1 - p) ** k))


def nb_ge(k, lam, r=NB_R):
    return max(0.0, min(1.0, 1.0 - sum(nb_pmf(i, lam, r) for i in range(int(k)))))


def poisson_ge(k, lam):
    cum = sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(int(k)))
    return max(0.0, min(1.0, 1.0 - cum))


def fair_odds(p):
    return round(1 / p, 2) if p > 0 else None


def ev_percent(book, p):
    return round((book * p - 1) * 100, 2)


def tier_for_ev(ev):
    return "strong" if ev >= 5 else ("small" if ev > 0 else "none")


def team(*pairs):
    return {"real_matches": [{"corners_for": a, "corners_against": b} for a, b in pairs]}


def extra(odds=None, home=None, away=None, **kw):
    return markets.build_extra_markets(
        {"total": 10.4, "home": 6.0, "away": 4.8}, odds or {},
        team_ge=nb_ge, total_ge=poisson_ge, fair_odds=fair_odds,
        ev_percent=ev_percent, tier_for_ev=tier_for_ev,
        team_lines=[3.5, 4.5], total_lines=[9.5, 10.5],
        pairs=markets.pair_counts(home, away) if (home or away) else None, **kw)


# --- pairing the two sides of a match ------------------------------------------------

class TestPairCounts:
    def test_one_match_is_one_observation_of_both_sides(self):
        # corners_against IS the opponent's count in that game — the joint is on file.
        assert markets.pair_counts(team((7, 3))) == [(7, 3)]

    def test_both_teams_histories_are_pooled(self):
        got = markets.pair_counts(team((7, 3)), team((2, 9)))
        assert sorted(got) == [(2, 9), (7, 3)]

    def test_a_row_missing_either_side_is_not_half_an_observation(self):
        thin = {"real_matches": [{"corners_for": 5}, {"corners_against": 4},
                                 {"corners_for": 6, "corners_against": 2}]}
        assert markets.pair_counts(thin) == [(6, 2)]

    def test_no_team_and_no_matches_are_both_simply_empty(self):
        assert markets.pair_counts() == []
        assert markets.pair_counts(None, {}, {"real_matches": []}) == []

    def test_a_limit_takes_the_most_recent_games(self):
        t = team((1, 1), (2, 2), (3, 3), (4, 4))
        assert markets.pair_counts(t, limit=2) == [(3, 3), (4, 4)]


# --- the factor ----------------------------------------------------------------------

class TestDependence:
    def test_independent_counts_measure_as_independent(self):
        # Every combination of 0..9 against 0..9, once: independence by construction.
        pairs = [(a, b) for a in range(10) for b in range(10)]
        got = markets.dependence(pairs, 4)
        assert 0.98 <= got["factor"] <= 1.02
        assert got["pairs"] == 100

    def test_sides_that_rise_together_measure_above_one(self):
        # A shared tempo: both counts move with the same underlying number.
        pairs = [(t + a, t + b) for t in range(7) for a in range(4) for b in range(4)]
        assert markets.dependence(pairs, 5)["factor"] > 1.0

    def test_one_side_dominating_measures_below_one(self):
        # THE DANGEROUS CASE. A roughly fixed total split between the sides: when one has
        # many the other has few, so "both clear 4" is rarer than independence claims and
        # the independent price is too short.
        pairs = [(a, 12 - a) for a in range(13)] * 8
        got = markets.dependence(pairs, 4)
        assert got["factor"] < 1.0
        assert got["raw"] < got["factor"] or got["factor"] == markets.DEPENDENCE_MIN

    def test_a_thin_sample_is_pulled_towards_independence(self):
        # The same signal, measured on few games, must move the price less. Kept mild
        # on purpose: a signal strong enough to hit the clamp would read as equal at both
        # sample sizes and the shrinkage would go untested.
        signal = [(9, 9), (9, 1), (1, 9), (9, 9)]
        few = markets.dependence(signal * 3, 4, min_pairs=4)
        many = markets.dependence(signal * 60, 4, min_pairs=4)
        assert few["raw"] == many["raw"]                     # same signal
        assert abs(few["factor"] - 1.0) < abs(many["factor"] - 1.0)

    def test_the_factor_is_clamped_however_strong_the_sample_looks(self):
        perfect = ([(9, 9)] * 200) + ([(0, 0)] * 200)
        got = markets.dependence(perfect, 4)
        assert got["factor"] == markets.DEPENDENCE_MAX
        assert got["raw"] > markets.DEPENDENCE_MAX     # the measurement is still reported

    def test_too_few_games_refuses_rather_than_guesses(self):
        assert markets.dependence([(5, 5)] * (markets.MIN_PAIRS - 1), 4) is None
        assert markets.dependence([], 4) is None

    def test_a_line_neither_side_ever_reached_is_not_a_measurement(self):
        # Nobody clearing k says the line is out of reach, not that the sides are linked.
        assert markets.dependence([(1, 1)] * 50, 9) is None

    def test_it_is_measured_at_each_line_not_once_for_the_fixture(self):
        pairs = [(a, 12 - a) for a in range(13)] * 8
        assert markets.dependence(pairs, 2) != markets.dependence(pairs, 5)


# --- the probabilities ----------------------------------------------------------------

class TestProbabilities:
    def test_both_over_is_the_product_when_nothing_is_measured(self):
        got = markets.both_over_prob(4, 6.0, 4.8, nb_ge, 1.0)
        assert abs(got - nb_ge(4, 6.0) * nb_ge(4, 4.8)) < 1e-12

    def test_the_factor_moves_the_joint_and_nothing_else(self):
        base = markets.both_over_prob(4, 6.0, 4.8, nb_ge, 1.0)
        assert abs(markets.both_over_prob(4, 6.0, 4.8, nb_ge, 0.73) - base * 0.73) < 1e-12

    def test_a_joint_probability_can_never_leave_zero_to_one(self):
        assert markets.both_over_prob(1, 20.0, 20.0, nb_ge, 1.3) <= 1.0
        assert markets.both_over_prob(40, 1.0, 1.0, nb_ge, 1.3) >= 0.0

    def test_under_is_the_exact_complement_of_the_over(self):
        for lam in (4.8, 10.4):
            assert abs(markets.under_prob(9.5, lam, poisson_ge)
                       + poisson_ge(10, lam) - 1.0) < 1e-12

    def test_under_counts_the_line_itself_as_a_win(self):
        # Under 4.5 is "four or fewer", so exactly four lands it.
        assert markets.under_prob(4.5, 4.8, nb_ge) > markets.under_prob(3.5, 4.8, nb_ge)


# --- the rows -------------------------------------------------------------------------

class TestRows:
    def test_every_group_that_has_overs_gets_unders(self):
        groups = {r["group"] for r in extra()}
        assert {"total_under", "home_under", "away_under"} <= groups

    def test_both_teams_lines_are_there_and_keyed_so_a_price_can_be_typed(self):
        keys = {r["key"] for r in extra()}
        assert "both_over_3.5" in keys          # "4 corners each team"
        assert "home_under_4.5" in keys
        assert "total_under_9.5" in keys

    def test_a_row_carries_the_same_fields_every_other_market_does(self):
        row = next(r for r in extra() if r["key"] == "both_over_3.5")
        assert set(row) >= {"key", "group", "group_label", "line", "label", "prob",
                            "fair_odds", "book_odds", "ev", "tier"}

    def test_no_price_means_no_edge_rather_than_a_zero_one(self):
        row = next(r for r in extra() if r["key"] == "both_over_3.5")
        assert row["book_odds"] is None and row["ev"] is None and row["tier"] is None

    def test_a_typed_price_prices_the_new_market_like_any_other(self):
        row = next(r for r in extra(odds={"both_over_3.5": 2.50})
                   if r["key"] == "both_over_3.5")
        assert row["book_odds"] == 2.50
        # Against the FULL probability, not the one rounded for display — exactly as the
        # single-side markets do it. Comparing to row["prob"] is out by a hundredth.
        assert abs(row["ev"] - (2.50 * row["prob"] / 100 - 1) * 100) < 0.05

    def test_the_joint_row_says_what_it_assumed(self):
        # A price built on a measured factor and one built on an assumption are different
        # claims, and the row is read by a bot that cannot ask which it is.
        pairs = [(a, 12 - a) for a in range(13)] * 8
        rows = markets.build_extra_markets(
            {"total": 10.4, "home": 6.0, "away": 4.8}, {},
            team_ge=nb_ge, total_ge=poisson_ge, fair_odds=fair_odds,
            ev_percent=ev_percent, tier_for_ev=tier_for_ev,
            team_lines=[3.5], total_lines=[9.5], pairs=pairs)
        row = next(r for r in rows if r["key"] == "both_over_3.5")
        assert row["dependence"]["pairs"] == len(pairs)
        assert row["dependence"]["factor"] < 1.0
        assert row["independent_prob"] > row["prob"]

    def test_with_no_history_it_falls_back_to_independence_and_says_so(self):
        row = next(r for r in extra() if r["key"] == "both_over_3.5")
        assert row["dependence"] is None
        assert row["independent_prob"] == row["prob"]

    def test_a_fixture_with_no_lambdas_produces_no_rows_rather_than_zeroes(self):
        rows = markets.build_extra_markets(
            {"total": 0, "home": 0, "away": 0}, {},
            team_ge=nb_ge, total_ge=poisson_ge, fair_odds=fair_odds,
            ev_percent=ev_percent, tier_for_ev=tier_for_ev,
            team_lines=[3.5], total_lines=[9.5])
        assert rows == []

    def test_both_teams_over_is_never_longer_than_one_team_over(self):
        # A joint event cannot be likelier than either half of it. This is the check that
        # catches a factor applied the wrong way round.
        for row in extra():
            if row["group"] != "both":
                continue
            k = int(row["line"]) + 1
            assert row["prob"] / 100 <= nb_ge(k, 6.0) + 1e-9
            assert row["prob"] / 100 <= nb_ge(k, 4.8) + 1e-9
