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

from odds_feed import (GROUP_LINES, MARKET_GROUP, REFUSED, SOURCE,  # noqa: E402
                       TEAM_FEED_LINES, TOTAL_FEED_LINES, clv_percent,
                       extract, feed_doc, first_entry, market_key, merge_prices,
                       parse_line)


def bet(name, *pairs):
    return {"name": name, "values": [{"value": v, "odd": o} for v, o in pairs]}


def entry(*books):
    return {"bookmakers": [{"name": n, "bets": list(bs)} for n, bs in books]}


class TestTheKeyIsSpelledTheWayTheAppSpellsIt:
    """The failure mode this class exists for is silence.

    server.py's TEAM_LINES and TOTAL_LINES are lists of FLOATS, so build_markets writes
    `home_over_4.5`, and every reader of db.odds looks that key up. A mapping that wrote
    `home_over_4` instead would store cleanly, merge cleanly, pass every test about
    prices and books — and then match no market at all, so the whole pipeline would do
    nothing with no error anywhere. That is the one bug a spot-check cannot see.
    """

    def test_the_key_keeps_the_half(self):
        got = extract(entry(("Bet365", [
            bet("Home Corners Over/Under", ("Over 4.5", "1.80")),
            bet("Corners Over Under", ("Over 10.5", "1.91"))])))
        assert "home_over_4.5" in got["taken"], "the app never queries home_over_4"
        assert "total_over_10.5" in got["taken"]

    def test_the_two_ladders_match_the_apps_own_line_lists(self):
        # Copied from server.py rather than imported, because importing server here
        # panics on a cryptography build. If these lists ever move, this test is the
        # tripwire — and a line outside them has no fair price to be an edge against.
        assert sorted(TEAM_FEED_LINES) == [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
        assert sorted(TOTAL_FEED_LINES) == [6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5, 13.5]
        assert GROUP_LINES["home"] is GROUP_LINES["away"] is TEAM_FEED_LINES

    def test_a_line_the_model_does_not_price_is_refused_with_that_reason(self):
        # The feed quotes both of these; neither has a key, so neither has a fair price.
        got = extract(entry(("Bet365", [
            bet("Corners Over Under", ("Over 14.5", "3.40")),
            bet("Home Corners Over/Under", ("Over 1.5", "1.12"))])))
        assert got["taken"] == {}
        assert all("outside the ladder" in s["why"] for s in got["skipped"])

    def test_a_total_line_only_the_team_ladder_carries_is_refused(self):
        # 2.5 is a team line and not a total one. Sharing one list would have let a
        # "Total Over 2.5" price be stored against a key build_markets never makes.
        got = extract(entry(("Bet365", [bet("Corners Over Under", ("Over 2.5", "1.05"))])))
        assert got["taken"] == {}


class TestAHalfLineIsNotAnIntegerLine:
    def test_the_half_line_maps_to_the_key_that_prices_the_same_event(self):
        # "Over 4.5" is five or more: the key home_over_4.5 prices nb_ge(4+1) = P(X>=5).
        assert parse_line("Over 4.5") == (4.5, None)
        assert parse_line("over 10.5") == (10.5, None)

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
        assert set(got["taken"]) == {"total_over_10.5"}
        assert got["taken"]["total_over_10.5"]["price"] == 2.00
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
        assert got["taken"]["home_over_5.5"]["price"] == 1.80
        assert got["taken"]["away_over_3.5"]["price"] == 1.83
        assert got["taken"]["total_over_9.5"]["price"] == 1.91

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
        row = got["taken"]["home_over_4.5"]
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
        assert d["odds"] == {"home_over_4.5": 1.95}
        assert d["books"]["home_over_4.5"] == "Pinnacle"
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
        out = merge_prices({"home_over_4.5": 1.90}, {"home_over_4.5": 2.10})
        assert out["home_over_4.5"]["price"] == 1.90
        assert out["home_over_4.5"]["source"] == "manual"

    def test_but_the_better_feed_price_is_kept_beside_it(self):
        # So a board can say "2.10 available elsewhere" without switching on its own.
        out = merge_prices({"home_over_4.5": 1.90}, {"home_over_4.5": 2.10})
        assert out["home_over_4.5"]["feed_price"] == 2.10
        assert out["home_over_4.5"]["feed_better"] is True

    def test_a_worse_feed_price_is_marked_as_worse(self):
        out = merge_prices({"home_over_4.5": 2.20}, {"home_over_4.5": 2.00})
        assert out["home_over_4.5"]["feed_better"] is False

    def test_a_feed_price_stands_alone_where_no_human_typed_one(self):
        out = merge_prices({}, {"total_over_10.5": 1.91})
        assert out["total_over_10.5"] == {"price": 1.91, "source": SOURCE}

    def test_neither_side_can_smuggle_in_a_bad_number(self):
        out = merge_prices({"a_over_1": 1.0, "b_over_2": None},
                           {"c_over_3": "x", "d_over_4": 0.5})
        assert out == {}

    def test_an_empty_pair_is_empty_not_an_error(self):
        assert merge_prices({}, {}) == {}
        assert merge_prices(None, None) == {}


class TestFromAPostToAPrice:
    def test_five_plus_is_priced_on_the_four_and_a_half_line(self):
        # The post says "5+". The bet is struck on 4.5. Getting this wrong compares a
        # price against a different bet and the number still looks plausible.
        assert market_key("team", True, 5) == ("home_over_4.5", None)
        assert market_key("team", False, 4) == ("away_over_3.5", None)

    def test_a_match_total_goes_to_the_total_ladder(self):
        assert market_key("match", True, 10) == ("total_over_9.5", None)

    def test_an_under_is_refused_and_says_no_price_exists_for_it(self):
        # Not "no closing price was found" — no fetched under price can exist at all,
        # because this module refuses the feed's under side and build_markets makes no
        # under keys. The two would otherwise be indistinguishable in a report.
        key, why = market_key("team", True, 5, direction="under")
        assert key is None and "under" in why

    def test_a_claim_that_never_recorded_its_side_is_refused(self):
        key, why = market_key("team", None, 5)
        assert key is None and "side" in why


class TestBeatingTheClose:
    def test_a_better_price_than_the_close_is_positive(self):
        assert clv_percent(2.10, 2.00) == 5.0

    def test_a_worse_price_is_negative(self):
        assert clv_percent(1.90, 2.00) == -5.0

    def test_the_same_price_is_zero_not_missing(self):
        assert clv_percent(2.0, 2.0) == 0.0

    @pytest.mark.parametrize("pair", [(None, 2.0), (2.0, None), (2.0, 0.5),
                                      ("x", 2.0), (2.0, "x"), (1.0, 2.0)])
    def test_an_unmeasurable_pair_is_none_and_never_zero(self, pair):
        # A zero would average into a summary as "we matched the close", which is a claim.
        assert clv_percent(*pair) is None


class TestWhatAfGetActuallyHandsBack:
    """The bug that cost sixty API calls and reported none of them.

    sync_real.af_get ends `return data["response"]` — it unwraps the envelope and returns
    the LIST. The fetcher called `.get("response")` on that, which is the shape the raw
    provider sends, so every fixture raised AttributeError and nothing was stored.

    It was invisible from outside, which is the part worth testing against: the run came
    back `priced: 0` with `calls: 0`, so it looked free as well as empty.
    """

    def test_the_list_af_get_returns_is_accepted(self):
        e = entry(("Bet365", [bet("Home Corners Over/Under", ("Over 4.5", "1.80"))]))
        assert first_entry([e]) is e

    def test_the_raw_envelope_is_accepted_too(self):
        # Nothing calls it this way today. Accepting both is cheaper than a call site
        # guessing which it has — the guess is what went wrong.
        e = entry(("Bet365", []))
        assert first_entry({"response": [e]}) is e

    def test_only_the_first_entry_is_taken(self):
        a, b = entry(("A", [])), entry(("B", []))
        assert first_entry([a, b]) is a

    @pytest.mark.parametrize("empty", [[], None, {}, {"response": []},
                                       {"response": None}, "", 0])
    def test_a_fixture_nobody_prices_is_none_not_an_exception(self, empty):
        # The common case on a lower division, and it must not look like a fault.
        assert first_entry(empty) is None

    @pytest.mark.parametrize("junk", [["x"], [None], [[]], [1]])
    def test_a_response_of_the_wrong_shape_is_none_rather_than_a_crash(self, junk):
        assert first_entry(junk) is None

    def test_the_fetcher_uses_it_rather_than_reaching_into_the_response(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "fetch_odds.py")) as fh:
            s = fh.read()
        assert "first_entry(" in s
        assert '.get("response")' not in s, \
            "af_get already unwrapped it — this is the sixty-call bug"


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

    def test_a_call_is_counted_when_it_is_MADE_not_when_it_succeeds(self):
        """The number that was supposed to make the cost visible, and hid it.

        `calls` incremented after fetch_one returned, so sixty charged calls against a
        mapping bug reported `calls: 0`. The run looked free as well as empty, which is
        the opposite of what this counter is for. It must now sit above the try, where a
        failure cannot skip it."""
        s = self.src()
        for fn in ("async def fetch_window", "async def fetch_closing"):
            body = s.split(fn, 1)[1][:2600]
            count_at = body.find('out["calls"] += 1')
            try_at = body.find("try:")
            assert count_at != -1 and try_at != -1, fn
            assert count_at < try_at, \
                f"{fn} counts the call inside the try — a failed call would be free"

    def test_one_bad_fixture_does_not_end_the_run(self):
        s = self.src()
        block = s.split("for fx, fid in todo:")[-1]
        assert "except Exception" in block

    def test_the_closing_pass_writes_to_its_own_collection(self):
        # A closing price is a different fact from a live one — it is what the market
        # settled at — and overwriting the live price with it would destroy the thing CLV
        # is measured against on the next fixture.
        s = self.src()
        assert "db.odds_closing.update_one" in s
        assert "db.odds.update_one" not in s

    def test_a_later_capture_only_wins_if_it_is_closer_to_kick_off(self):
        s = self.src()
        block = s.split("async def fetch_closing")[-1].split("async def fetch_window")[0]
        assert "minutes_before_kickoff" in block
        assert "kept_earlier" in block, "a worse reading must not displace a better one"

    def test_both_passes_are_reachable_over_http_and_token_gated(self):
        """A CLI cannot be put on a schedule here.

        Every scheduled job in this repo is a workflow that curls an endpoint with
        TOOLS_TOKEN; fetch_odds needs MONGO_URL and the provider key, which the backend has
        and a GitHub runner does not. For the WINDOW pass that is an inconvenience. For the
        CLOSING pass it is the whole thing: a closing price is captured before kick-off or
        lost for that fixture for good, so with no endpoint there was nothing a cron could
        call and CLV could never be filled in.

        Token-gated, because these spend one API call per fixture. /api/sync/if-stale can
        be left open — it does nothing unless the data is already stale — and these cannot.
        """
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "server.py")) as fh:
            s = fh.read()
        for route in ('@api_router.post("/odds/fetch")',
                      '@api_router.post("/odds/closing")'):
            assert route in s, route
            body = s.split(route, 1)[1][:1600]
            assert "_check_tools_token(token)" in body, f"{route} must be gated"

    def test_a_schedule_actually_calls_the_closing_pass(self):
        """The endpoint existing is not the same as anything calling it.

        This is the one piece of the pipeline that cannot be caught up on later, so a
        workflow that forgets it leaves an unrecoverable hole rather than a backlog.
        """
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(root, ".github", "workflows", "odds.yml")) as fh:
            wf = fh.read()
        assert "/api/odds/closing" in wf
        assert "cron:" in wf, "a dispatch-only workflow captures nothing unattended"

    def test_it_says_a_closing_price_cannot_be_fetched_afterwards(self):
        # The constraint that makes this a scheduled job rather than a backfill. If this
        # sentence goes, somebody will write the backfill and find it returns nothing.
        s = self.src()
        assert "cannot be done after the game" in s.lower() \
            or "cannot be fetched after the game" in s.lower()
