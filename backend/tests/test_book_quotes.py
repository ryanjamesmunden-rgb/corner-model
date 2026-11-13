"""Every book's price for a market, not just the winner — and what the spread means.

WHY THE FEED KEPT ONLY ONE. extract() compared each quote against the best so far and
threw the loser away. That answered "what is the best price and who has it", which is the
question a backer asks, and left two it could not:

  how far clear the best price actually is — 2.30 against 2.28 and 2.25 is a market
  agreeing with itself, 2.30 against 1.95 and 1.90 is ONE BOOK OUT ON ITS OWN, and the
  second is far more often a mis-set line than free money;

  whether a price exists at a book the reader actually holds — the aggregator carries 33,
  and the best of them is frequently not one anybody has an account with.

Keeping all of them costs nothing: the response already carries every book, so there is
no second request and no extra API call.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import odds_feed  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _helpers():
    """server.py cannot be imported here — pymongo pulls in cryptography, which panics in
    this container — so the pure helpers come from a slice of the source, as in
    test_price_provenance and test_stat_picks."""
    with open(os.path.join(HERE, "server.py")) as fh:
        src = fh.read()
    start = src.index("MAX_QUOTES_SHOWN = 8")
    end = src.index("def feed_book_names(")
    typing = __import__("typing")
    ns = {"List": typing.List, "Optional": typing.Optional, "Dict": typing.Dict}
    exec(compile(src[start:end], "sliced", "exec"), ns)
    return ns


NS = _helpers()
book_quotes = NS["book_quotes"]
quote_spread = NS["quote_spread"]


def entry(*books):
    """An /odds response entry: (book name, [(market value, price), ...]) per book."""
    return {"bookmakers": [
        {"name": name, "bets": [{"name": "Corners Over Under",
                                 "values": [{"value": v, "odd": str(o)} for v, o in vals]}]}
        for name, vals in books]}


# --- the feed keeps every book -----------------------------------------------------------

def test_every_book_that_quoted_a_market_is_kept():
    got = odds_feed.extract(entry(
        ("Bet365", [("Over 9.5", 2.10)]),
        ("Pinnacle", [("Over 9.5", 2.05)]),
        ("1xBet", [("Over 9.5", 2.25)]),
    ))
    assert got["taken"]["total_over_9.5"]["prices"] == {
        "Bet365": 2.10, "Pinnacle": 2.05, "1xBet": 2.25}


def test_the_headline_price_is_still_the_best_and_still_names_its_book():
    # Nothing downstream may change shape: `odds` and `books` are read everywhere.
    got = odds_feed.extract(entry(
        ("Bet365", [("Over 9.5", 2.10)]),
        ("1xBet", [("Over 9.5", 2.25)]),
    ))
    t = got["taken"]["total_over_9.5"]
    assert t["price"] == 2.25
    assert t["book"] == "1xBet"
    assert t["quotes"] == 2


def test_one_book_quoting_the_same_market_twice_appears_once_at_its_best():
    # The probe saw "Over 10.5" and "Over 10" fold onto one key. Listing a book twice at
    # two prices would read as two books, and inflate how wide the market looks.
    got = odds_feed.extract(entry(
        ("Bet365", [("Over 9.5", 1.90), ("Over 9.5", 2.05)]),
    ))
    t = got["taken"]["total_over_9.5"]
    assert t["prices"] == {"Bet365": 2.05}
    assert t["price"] == 2.05


def test_the_stored_document_carries_them_best_first():
    doc = odds_feed.feed_doc("f1", 99, entry(
        ("Bet365", [("Over 9.5", 2.10)]),
        ("Pinnacle", [("Over 9.5", 2.30)]),
        ("1xBet", [("Over 9.5", 1.95)]),
    ), "2026-11-13T12:00:00+00:00")
    assert list(doc["quoted"]["total_over_9.5"]) == ["Pinnacle", "Bet365", "1xBet"]
    # The fields every existing reader depends on are untouched.
    assert doc["odds"]["total_over_9.5"] == 2.30
    assert doc["books"]["total_over_9.5"] == "Pinnacle"
    assert doc["quotes"]["total_over_9.5"] == 3


def test_a_market_only_one_book_quoted_still_gets_an_entry():
    doc = odds_feed.feed_doc("f1", 99, entry(("Bet365", [("Over 9.5", 2.10)])),
                             "2026-11-13T12:00:00+00:00")
    assert doc["quoted"]["total_over_9.5"] == {"Bet365": 2.10}


# --- reading them back --------------------------------------------------------------------

QUOTED = {"home_over_4.5": {"1xBet": 2.31, "Betano": 2.10, "Bet365": 2.05, "Pinnacle": 1.98}}


def test_the_row_comes_back_best_first():
    rows = book_quotes(QUOTED, "home_over_4.5")
    assert [r["book"] for r in rows] == ["1xBet", "Betano", "Bet365", "Pinnacle"]
    assert rows[0]["price"] == 2.31


def test_it_sorts_rather_than_trusting_the_stored_order():
    # Documents written before feed_doc sorted them exist, and a list whose first entry is
    # not the best would put the wrong number under a heading that says "best".
    rows = book_quotes({"k": {"A": 1.80, "B": 2.40, "C": 2.00}}, "k")
    assert [r["price"] for r in rows] == [2.40, 2.00, 1.80]


def test_a_market_or_a_document_with_nothing_stored_is_empty_not_an_error():
    assert book_quotes(QUOTED, "away_over_9.5") == []
    assert book_quotes(None, "home_over_4.5") == []
    assert book_quotes({}, "home_over_4.5") == []


def test_junk_prices_are_dropped_rather_than_sorted():
    rows = book_quotes({"k": {"A": 2.0, "B": None, "C": "2.5", "D": True}}, "k")
    assert [r["book"] for r in rows] == ["A"]


def test_the_list_is_capped():
    many = {"k": {f"Book{i}": 1.5 + i / 100 for i in range(20)}}
    assert len(book_quotes(many, "k")) == NS["MAX_QUOTES_SHOWN"] == 8
    # The cap takes the WORST off, never the best.
    assert book_quotes(many, "k")[0]["price"] == 1.69


# --- the spread, which is what says whether to believe the best price ----------------------

def test_it_measures_the_best_against_the_second_and_the_worst():
    sp = quote_spread(book_quotes(QUOTED, "home_over_4.5"))
    assert sp["books"] == 4
    assert sp["best"] == 2.31 and sp["second"] == 2.10 and sp["worst"] == 1.98
    assert sp["over_second"] == 10.0      # 2.31 / 2.10
    assert sp["over_worst"] == 16.7       # 2.31 / 1.98


def test_a_market_that_agrees_with_itself_looks_different_from_an_outlier():
    tight = quote_spread(book_quotes({"k": {"A": 2.30, "B": 2.28, "C": 2.25}}, "k"))
    lone = quote_spread(book_quotes({"k": {"A": 2.30, "B": 1.95, "C": 1.90}}, "k"))
    assert tight["over_second"] < 1
    assert lone["over_second"] > 17
    # THE WHOLE POINT. Both have a best price of 2.30 and the board would have shown the
    # same single number for each; only one of them is a price the market agrees exists.
    assert tight["best"] == lone["best"]


def test_one_quote_has_no_spread_and_says_so_rather_than_claiming_agreement():
    # Reporting 0% on a single price would read as "every book agrees" when the truth is
    # that nobody else was asked.
    assert quote_spread(book_quotes({"k": {"A": 2.0}}, "k")) is None
    assert quote_spread([]) is None
    assert quote_spread(None) is None
