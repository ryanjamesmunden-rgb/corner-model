"""What may be published as a stat pick, and what the count beside it has to mean.

THE POST THIS GUARDS IS THE MOST CHECKABLE THING THE ACCOUNT PUTS OUT. "4.5+ Corners @
2.10 (8/10)" invites a reader to go and count, because the form table it came from is on
the site unblurred. That is the whole appeal and it is also the whole exposure: a row
whose count does not survive being checked costs more than ten rows that were never
posted.

So the rules are: a price somebody could have taken, a bookmaker named, a line inside the
band the ledger measured, a rate over a window the payload states, and a REASON whenever a
rung is refused — because a card that came back short has to be able to say whether
nothing was priced, nothing cleared the rate, or nothing cleared the price.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import odds_feed  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _slice():
    """server.py cannot be imported here — pymongo pulls in cryptography, which panics in
    this container — so the pure helpers are exercised through a slice of the source, the
    technique test_value_snapshot, test_played_fixtures and test_price_provenance use."""
    with open(os.path.join(HERE, "server.py")) as fh:
        src = fh.read()
    start = src.index("STAT_PICK_BAND = (5, 6)")
    end = src.index('@api_router.get("/share/stat-picks")')
    ns = {"odds_feed": odds_feed, "Optional": __import__("typing").Optional,
          "STAT_PICK_BAND": None}
    exec(compile(src[start:end], "sliced", "exec"), ns)
    return ns


NS = _slice()
fault = NS["stat_pick_fault"]
row_of = NS["stat_pick_row"]
BAND = NS["STAT_PICK_BAND"]
API = odds_feed.SOURCE


def market(**over):
    m = {"key": "away_over_4.5", "group": "away", "line": 4.5, "book_odds": 2.10,
         "fair_odds": 1.84, "prob": 54.3, "ev": 14.3, "price_source": API,
         "book": "Bet365"}
    m.update(over)
    return m


# --- what may be published -------------------------------------------------------------

def test_a_priced_team_line_that_has_been_landing_is_a_pick():
    assert fault(market(), 8, 10) == ""


def test_the_band_is_the_one_the_ledger_measured():
    # 5+/6+ team corner lines: +48.47u over 90 settled. 4+ and below: -12.90u over 29.
    assert BAND == (5, 6)
    assert fault(market(line=4.5), 8, 10) == ""      # 5+
    assert fault(market(line=5.5), 8, 10) == ""      # 6+
    assert fault(market(line=3.5), 10, 10) == "outside_band"   # 4+, however well it lands
    assert fault(market(line=2.5), 10, 10) == "outside_band"


def test_a_match_total_is_not_a_team_line():
    assert fault(market(group="total", line=9.5), 9, 10) == "not_a_team_line"


def test_a_demo_or_unstamped_price_is_refused():
    # THE ONE THAT WOULD FABRICATE AN EDGE. The seeders write fair_odds * uniform(0.90,
    # 1.15), so an EV computed against one of those is the model finding value in its own
    # noise — and on this card it would sit beside a real count, borrowing its credibility.
    assert fault(market(price_source="demo"), 8, 10) == "no_real_price"
    assert fault(market(price_source=None), 8, 10) == "no_real_price"
    assert fault(market(price_source="seed"), 8, 10) == "no_real_price"


def test_a_hand_typed_price_is_allowed_and_a_bookless_one_is_not():
    # manual is real — somebody looked at a market and wrote the number down. What is
    # refused is a price with no bookmaker behind it: the feed takes the best of 33 books,
    # and an edge at a book the reader has no account with is not a bet they can place.
    assert fault(market(price_source="manual"), 8, 10) == ""
    assert fault(market(book=""), 8, 10) == "no_book"
    assert fault(market(book=None), 8, 10) == "no_book"


def test_the_price_floor_is_applied_and_is_inclusive():
    assert fault(market(book_odds=1.49), 8, 10) == "below_odds_floor"
    assert fault(market(book_odds=1.50), 8, 10) == ""
    assert fault(market(book_odds=None), 8, 10) == "below_odds_floor"


def test_the_edge_floor_is_applied_and_is_inclusive():
    assert fault(market(ev=-0.1), 8, 10) == "below_ev_floor"
    assert fault(market(ev=0.0), 8, 10) == ""
    assert fault(market(ev=None), 8, 10) == "below_ev_floor"


def test_the_hit_floor_is_applied_and_is_inclusive():
    assert fault(market(), 6, 10) == "below_hit_rate"
    assert fault(market(), 7, 10) == ""          # exactly 70%
    assert fault(market(), 10, 10) == ""


def test_the_floors_can_be_widened_deliberately():
    assert fault(market(), 6, 10, min_hit=0.6) == ""
    assert fault(market(book_odds=1.2), 8, 10, min_odds=1.1) == ""
    assert fault(market(ev=-4), 8, 10, min_ev=-5) == ""
    assert fault(market(line=3.5), 8, 10, band=(4, 5, 6)) == ""


# --- what must never be guessed ---------------------------------------------------------

def test_an_uncounted_rung_is_named_rather_than_treated_as_a_miss():
    # corner_counts measures LEAK_LINES only. A rung it never counted has NO rate, which
    # is a different thing from a rate of zero — and publishing it as a miss would be a
    # claim about games nobody looked at.
    assert fault(market(), None, 10) == "line_not_counted"


def test_no_games_is_not_a_hit_rate_of_zero():
    # A side with an empty pool divides by zero. The fault is checked before the rate so
    # the endpoint cannot raise on a team the sync has not filled in yet.
    assert fault(market(), None, 0) == "no_games"
    assert fault(market(), 0, 0) == "no_games"


def test_nothing_at_all_is_answered_rather_than_raised():
    assert fault(None, 8, 10) == "no_market"
    # An empty dict is the absence of a market, not a market of the wrong kind: the guard
    # is falsiness, so {} and None answer the same thing, which is what a caller counting
    # drops needs them to do.
    assert fault({}, 8, 10) == "no_market"
    assert fault({"group": "away"}, 8, 10) == "no_line"
    assert fault(market(line=None), 8, 10) == "no_line"


# --- the row a post is written from -----------------------------------------------------

BOARD = {"fixture_id": "f1", "league_id": "bra-sb", "league_name": "Serie B",
         "date": "2026-11-14T22:30:00+00:00",
         "home_name": "Fortaleza", "away_name": "Vila Nova"}
COUNTS = {"games": 10, "scope": "away", "avg": 6.2,
          "hits": {"4": 9, "5": 8, "6": 6}}
OPP = {"games": 10, "scope": "home", "avg": 7.1, "hits": {"4": 8, "5": 7, "6": 5}}


def test_the_row_names_the_side_the_bet_is_on():
    r = row_of(BOARD, market(), COUNTS, OPP)
    assert r["team"] == "Vila Nova"
    assert r["side"] == "away"
    assert row_of(BOARD, market(group="home", key="home_over_4.5"),
                  COUNTS, OPP)["team"] == "Fortaleza"


def test_the_count_is_read_at_the_rung_being_backed():
    # hits are keyed by the THRESHOLD: "5" is games with 5 or more corners, which is the
    # 5+ bet, which is the 4.5 line. An off-by-one here publishes the wrong number beside
    # the right bet and nothing anywhere would say so.
    assert row_of(BOARD, market(line=4.5), COUNTS, OPP)["hits"] == 8
    assert row_of(BOARD, market(line=5.5), COUNTS, OPP)["hits"] == 6
    assert row_of(BOARD, market(line=4.5), COUNTS, OPP)["plus"] == 5


def test_the_row_carries_the_denominator_and_the_pool_it_came_from():
    r = row_of(BOARD, market(), COUNTS, OPP)
    assert r["games"] == 10
    # "8/10 at home" and "8/10 overall" are claims about different populations.
    assert r["scope"] == "away"


def test_the_opponent_half_rides_along_without_being_required():
    r = row_of(BOARD, market(), COUNTS, OPP)
    assert r["opp_hits"] == 7
    assert r["opp_games"] == 10
    assert r["opp_scope"] == "home"


def test_the_row_carries_the_price_its_book_and_the_model_beside_it():
    r = row_of(BOARD, market(), COUNTS, OPP)
    assert r["price"] == 2.10
    assert r["book"] == "Bet365"
    assert r["price_source"] == API
    assert r["fair"] == 1.84
    assert r["ev"] == 14.3


def test_a_rung_nobody_counted_comes_back_as_none_not_zero():
    thin = {"games": 10, "scope": "overall", "hits": {"4": 9}}
    assert row_of(BOARD, market(line=4.5), thin, OPP)["hits"] is None


def test_the_fixture_travels_with_the_row():
    r = row_of(BOARD, market(), COUNTS, OPP)
    assert r["home_name"] == "Fortaleza" and r["away_name"] == "Vila Nova"
    assert r["league_id"] == "bra-sb"
    assert r["kickoff"] == "2026-11-14T22:30:00+00:00"


# --- the constants the rest of the app reads --------------------------------------------

def test_the_cap_is_two_angles_a_fixture():
    # Fixtures published with three or more angles returned -4.4% over 112u, against
    # +13.0% over 512.5u for those with one or two.
    assert NS["STAT_PICK_PER_GAME"] == 2


def test_the_defaults_match_the_post_they_are_written_for():
    assert NS["STAT_PICK_MIN_HIT"] == 0.70
    assert NS["STAT_PICK_MIN_ODDS"] == 1.50
    assert NS["STAT_PICK_MIN_EV"] == 0.0


def test_only_real_price_sources_are_listed():
    assert set(NS["REAL_PRICE_SOURCES"]) == {"manual", API}
    assert "demo" not in NS["REAL_PRICE_SOURCES"]
