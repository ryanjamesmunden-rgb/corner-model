"""The team-corner ladder, up to 10+.

WHY THIS FILE EXISTS: the ladder stopped at Over 6.5, so a side the boards rate at 8 or 9
corners a game had no row to type a price into — the one market worth pricing on exactly
those games. The rungs are what the fixture page renders an odds box for and what its
paste parser checks a pasted line against, so the ladder's shape IS the feature.

Pure functions — no backend or database needed.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import TEAM_LINES, build_markets  # noqa: E402

LAMBDAS = {"total": 11.0, "home": 8.2, "away": 4.6}


def keys(markets, group):
    return [m["key"] for m in markets if m["group"] == group]


class TestTheLadderReachesTen:
    def test_every_rung_from_three_to_ten_is_priced_for_both_sides(self):
        markets = build_markets(LAMBDAS, {})
        for group in ("home", "away"):
            assert keys(markets, group) == [f"{group}_over_{l}" for l in TEAM_LINES]
            # "Over 7.5" is how a book writes "8+", which is how the posts say it.
            assert f"{group}_over_9.5" in keys(markets, group)

    def test_a_longer_line_is_never_more_likely_than_a_shorter_one(self):
        rows = [m for m in build_markets(LAMBDAS, {}) if m["group"] == "home"]
        probs = [m["prob"] for m in rows]
        assert probs == sorted(probs, reverse=True), probs
        # The tail is thin, not zero: a side averaging 8.2 clears 10+ often enough to
        # price. A zero here would mean the distribution had been truncated.
        assert 0 < rows[-1]["prob"] < rows[0]["prob"]

    def test_a_price_on_a_new_rung_gets_a_fair_price_and_an_ev(self):
        # The point of the whole change: type a price against 8+ and get the gap.
        markets = build_markets(LAMBDAS, {"home_over_7.5": 3.0})
        row = next(m for m in markets if m["key"] == "home_over_7.5")
        assert row["book_odds"] == 3.0
        assert row["fair_odds"] > 1.0
        assert row["ev"] is not None
        # Unpriced rungs stay unpriced rather than inheriting the one beside them.
        assert next(m for m in markets if m["key"] == "home_over_8.5")["ev"] is None

    def test_the_match_total_ladder_is_untouched(self):
        # Team corners and match totals are different markets on different scales, and
        # this change was only ever about the first.
        totals = keys(build_markets(LAMBDAS, {}), "total")
        assert totals[0] == "total_over_6.5" and totals[-1] == "total_over_13.5"
