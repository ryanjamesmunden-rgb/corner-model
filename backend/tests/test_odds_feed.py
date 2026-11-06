"""Mapping the provider's corner odds onto the lines this app prices.

WHAT THESE GUARD. A wrong price here does not look wrong — it looks like an edge. The
value board ranks on the gap between the model's fair price and a book price, so a line
mapped one step out, or an Asian line priced as a clean over, produces a confident EV
figure against the wrong event. Nothing downstream can detect that.

THE TWO THAT WOULD COST REAL MONEY:

  - "Over 10" and "Over 10.5" are different bets. The first pushes on exactly ten. Its
    fair price is conditional on the game not landing there, so pricing it as P(X>=11)
    overstates the edge on every integer line the feed quotes — and it quotes them
    alongside the .5 lines on the same market.
  - half-time corner markets are quoted on every fixture and cannot be priced at all,
    because no half-split corner data exists (issue #260). A stored price for one would
    sit on the board with no fair value to compare against.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from odds_feed import (MARKET_GROUP, REFUSED, SOURCE, extract,  # noqa: E402
                       feed_doc, merge_prices, parse_line)


def bet(name, *pairs):
    return {"name": name, "values": [{"value": v, "odd": o} for v, o in pairs]}


def entry(*books):
    return {"bookmakers": [{"name": n, "bets": list(bs)} for n, bs in books]}


class TestAHalfLineIsNotAnIntegerLine:
    def test_the_half_line_maps_to_the_key_that_prices_the_same_event(self):
        # "Over 4.5" is five or more. The key home_over_4 prices nb_ge(4+1) = P(X>=5).
        assert parse_line("Over 4.5") == (4, None)
        assert parse_line("over 10.5") == (10, None)

    def test_an_integer_line_is_refused_and_says_why(self):
        line, why = parse_line("Over 10")
        assert line is None
        assert "push" in why

    def test_the_under_side_is_refused(self):
        line, why = parse_line("Under 4.5")
        assert line is None and "under" in why.lower()

    def test_nonsense_is_refused_rather_than_guessed(self):
        for label in ("", None, "Exactly 4", "Yes", "Over", "4.5"):
            line, why = parse_line(label)
            assert line is None and why

    def test_both_lines_on_one_market_keep_only_the_half(self):
        # This is exactly what the feed sends: Over 10 and Over 10.5 side by side.
        got = extract(entry(("Bet365", [bet("Corners Over Under",
                                            ("Over 10", "1.82"), ("Over 10.5", "2.00"))])))
        assert set(got["taken"]) == {"total_over_10"}
        assert got["taken"]["total_over_10"]["price"] == 2.00
        assert any("push" in s["why"] for s in got["skipped"])


class TestOnlyMarketsThisAppCanPrice:
    def test_the_three_usable_markets_map_to_the_three_groups(self):
        assert MARKET_GROUP == {"Corners Over Under": "total",
                                "Home Corners Over/Under": "home",
                                "Away Corners Over/Under": "away"}

    def test_team_and_total_markets_land_on_their_own_keys(self):
        got = extract(entry(("Bet365", [
            bet("Home Corners Over/Under", ("Over 5.5", "1.80")),
            bet("Away Corners Over/Under", ("Over 3.5", "1.83")),
            bet("Corners Over Under", ("Over 9.5", "1.91")),
        ])))
        assert got["taken"]["home_over_5"]["price"] == 1.80
        assert got["taken"]["away_over_3"]["price"] == 1.83
        assert got["taken"]["total_over_9"]["price"] == 1.91

    @pytest.mark.parametrize("market", [
        "Total Corners (1st Half)", "Total Corners (2nd Half)",
        "Home Total Corners (1st Half)", "Away Total Corners (2nd Half)"])
    def test_every_half_market_is_refused_with_the_data_reason(self, market):
        # Quoted on every fixture the probe sampled, and unpriceable: there is no
        # half-split corner figure to build a fair price from.
        got = extract(entry(("Bet365", [bet(market, ("Over 4.5", "2.02"))])))
        assert got["taken"] == {}, f"{market} must not be stored"
        why = " ".join(s["why"] for s in got["skipped"])
        assert "half-split" in why and "260" in why

    def test_handicaps_and_race_to_are_refused(self):
        for market in ("Corners Asian Handicap", "Corners Race To", "Corners 1x2",
                       "Multicorners", "Corners. Odd/Even", "Corners. Total (Range)"):
            got = extract(entry(("Bet365", [bet(market, ("Over 4.5", "1.90"))])))
            assert got["taken"] == {}, market
            assert market in REFUSED

    def test_an_unknown_market_is_ignored_silently_not_stored(self):
        got = extract(entry(("Bet365", [bet("Something New", ("Over 4.5", "1.90"))])))
        assert got["taken"] == {} and got["skipped"] == []


class TestBestPriceWins:
    def test_the_highest_quote_is_taken_and_names_its_book(self):
        got = extract(entry(
            ("Bet365", [bet("Home Corners Over/Under", ("Over 4.5", "1.80"))]),
            ("Pinnacle", [bet("Home Corners Over/Under", ("Over 4.5", "1.95"))]),
            ("1xBet", [bet("Home Corners Over/Under", ("Over 4.5", "1.88"))]),
        ))
        row = got["taken"]["home_over_4"]
        assert row["price"] == 1.95 and row["book"] == "Pinnacle"
        assert row["quotes"] == 3, "how many books quoted it travels with the price"

    def test_every_book_seen_is_recorded(self):
        got = extract(entry(("Bet365", []), ("Pinnacle", []), ("Betano", [])))
        assert got["books"] == ["Bet365", "Betano", "Pinnacle"]

    def test_an_unusable_price_is_skipped_not_stored(self):
        # The probe saw "Over 1 = 1.00" on 3-way markets: a feed artefact, not a price.
        got = extract(entry(("Bet365", [bet("Corners Over Under",
                                            ("Over 9.5", "1.00"), ("Over 10.5", "abc"))])))
        assert got["taken"] == {}
        assert len(got["skipped"]) == 2


class TestTheStoredDocument:
    def doc(self):
        return feed_doc("fx-1", 123456, entry(
            ("Bet365", [bet("Home Corners Over/Under", ("Over 4.5", "1.80")),
                        bet("Total Corners (1st Half)", ("Over 4.5", "2.02"))]),
            ("Pinnacle", [bet("Home Corners Over/Under", ("Over 4.5", "1.95"))]),
        ), "2026-11-06T10:00:00Z")

    def test_it_is_not_stamped_manual(self):
        # The flag the value board trusts to mean "a human chose this number".
        d = self.doc()
        assert d["source"] == SOURCE != "manual"

    def test_it_carries_the_price_the_book_and_the_clock(self):
        d = self.doc()
        assert d["odds"] == {"home_over_4": 1.95}
        assert d["books"]["home_over_4"] == "Pinnacle"
        assert d["fetched_at"] == "2026-11-06T10:00:00Z"
        assert d["fixture_id"] == "fx-1" and d["api_fixture_id"] == 123456

    def test_refusals_are_recorded_so_a_gap_is_not_mistaken_for_no_market(self):
        d = self.doc()
        assert d["skipped_total"] >= 1
        assert any("half-split" in s["why"] for s in d["skipped"])

    def test_the_skipped_list_is_capped_but_the_count_is_not(self):
        many = [bet("Corners Asian Handicap", ("Over 4.5", "1.9")) for _ in range(60)]
        d = feed_doc("fx-2", 1, entry(("Bet365", many)), "2026-11-06T10:00:00Z")
        assert len(d["skipped"]) == 40
        assert d["skipped_total"] == 60

    def test_a_fixture_nobody_prices_yields_an_empty_but_valid_doc(self):
        d = feed_doc("fx-3", 9, {"bookmakers": []}, "2026-11-06T10:00:00Z")
        assert d["odds"] == {} and d["bookmakers"] == [] and d["source"] == SOURCE


class TestManualAlwaysWins:
    def test_a_human_price_beats_a_feed_price_on_the_same_key(self):
        out = merge_prices({"home_over_4": 1.90}, {"home_over_4": 2.10})
        assert out["home_over_4"]["price"] == 1.90
        assert out["home_over_4"]["source"] == "manual"

    def test_but_the_better_feed_price_is_kept_beside_it(self):
        # So a board can say "2.10 available elsewhere" without switching on its own.
        out = merge_prices({"home_over_4": 1.90}, {"home_over_4": 2.10})
        assert out["home_over_4"]["feed_price"] == 2.10
        assert out["home_over_4"]["feed_better"] is True

    def test_a_worse_feed_price_is_marked_as_worse(self):
        out = merge_prices({"home_over_4": 2.20}, {"home_over_4": 2.00})
        assert out["home_over_4"]["feed_better"] is False

    def test_a_feed_price_stands_alone_where_no_human_typed_one(self):
        out = merge_prices({}, {"total_over_10": 1.91})
        assert out["total_over_10"] == {"price": 1.91, "source": SOURCE}

    def test_neither_side_can_smuggle_in_a_bad_number(self):
        out = merge_prices({"a_over_1": 1.0, "b_over_2": None},
                           {"c_over_3": "x", "d_over_4": 0.5})
        assert out == {}

    def test_an_empty_pair_is_empty_not_an_error(self):
        assert merge_prices({}, {}) == {}
        assert merge_prices(None, None) == {}


class TestTheFetcherIsHonestAboutItsCost:
    """Source-level: fetch_odds.py needs a database and the provider to import."""

    @staticmethod
    def src():
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "fetch_odds.py")) as fh:
            return fh.read()

    def test_it_writes_to_its_own_collection_not_db_odds(self):
        s = self.src()
        assert "db.odds_feed.update_one" in s
        assert "db.odds.update_one" not in s, "feed prices must not touch the manual store"

    def test_the_defaults_are_small(self):
        # One API call per fixture, ~300 fixtures a week. A large default is a bill.
        import re
        s = self.src()
        days = int(re.search(r"DEFAULT_DAYS = (\d+)", s).group(1))
        limit = int(re.search(r"DEFAULT_LIMIT = (\d+)", s).group(1))
        assert days <= 3 and limit <= 60, "default run must stay cheap"

    def test_it_offers_a_dry_run_that_makes_no_calls(self):
        s = self.src()
        assert "--dry-run" in s and "no API calls" in s

    def test_it_sorts_soonest_first_so_a_cap_keeps_the_useful_ones(self):
        s = self.src()
        assert '.sort("date", 1)' in s

    def test_one_bad_fixture_does_not_end_the_run(self):
        s = self.src()
        block = s.split("for fx, fid in todo:")[-1]
        assert "except Exception" in block
