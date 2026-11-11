"""Which bookmaker quoted a fetched price, and when the fetcher actually runs.

BOTH HALVES ANSWER THE SAME COMPLAINT: prices on the board that cannot be found at a
bookmaker. One half is timing — the window pass had never run on a schedule, so a market
that opened during the day was not looked at until 90 minutes before kick-off. The other
is attribution — the feed takes the BEST price across 33 books and never said which, so an
edge could be measured against a quote the reader has no account with.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import odds_feed  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    with open(os.path.join(HERE, name)) as fh:
        return fh.read()


# server.py cannot be imported here — pymongo pulls in cryptography, which panics in this
# container — so the pure helper is exercised through a slice of the source, the technique
# test_value_snapshot and test_played_fixtures both use.
def _book_names():
    src = _src("server.py")
    start = src.index("def feed_book_names(")
    end = src.index("async def _merged_prices(")
    ns = {"odds_feed": odds_feed, "Dict": __import__("typing").Dict,
          "str": str}
    exec(compile(src[start:end], "sliced", "exec"), ns)
    return ns["feed_book_names"]


BOOKS = _book_names()
API = odds_feed.SOURCE


# --- who quoted the price ---------------------------------------------------------------

def test_a_fetched_price_names_its_bookmaker():
    out = BOOKS({"home_over_4.5": "Bet365"}, {"home_over_4.5": API})
    assert out == {"home_over_4.5": "Bet365"}


def test_a_hand_typed_price_is_not_attributed_to_a_bookmaker():
    """THE ONE THAT WOULD INVENT PROVENANCE. merge_prices lets a manual price win over a
    fetched one on the same market and keeps the feed's figure beside it, so the `books`
    map still holds a name for that key. Copying it across unfiltered would credit a
    number somebody typed to a book that never quoted it — false provenance, which is
    worse than none because it reads as checkable."""
    out = BOOKS({"home_over_4.5": "Bet365"}, {"home_over_4.5": "manual"})
    assert out == {}


def test_each_market_is_attributed_separately():
    """One fixture can hold a hand-typed line and a fetched ladder around it, which is
    exactly when this matters."""
    books = {"home_over_4.5": "Bet365", "home_over_5.5": "William Hill",
             "total_over_9.5": "Betfair"}
    sources = {"home_over_4.5": "manual", "home_over_5.5": API, "total_over_9.5": API}
    assert BOOKS(books, sources) == {"home_over_5.5": "William Hill",
                                     "total_over_9.5": "Betfair"}


def test_a_market_with_no_recorded_book_is_left_out():
    """Older feed documents predate the `books` map. A blank name is not a bookmaker, and
    printing one would put an empty attribution next to a real price."""
    assert BOOKS({"home_over_4.5": ""}, {"home_over_4.5": API}) == {}
    assert BOOKS({"home_over_4.5": None}, {"home_over_4.5": API}) == {}


def test_no_books_at_all_is_empty_and_not_an_error():
    assert BOOKS(None, {"home_over_4.5": API}) == {}
    assert BOOKS({}, {}) == {}


def test_a_book_for_a_market_that_has_no_price_is_dropped():
    """A `books` entry with nothing in `sources` is a market that did not survive the
    merge, so there is no price for the name to belong to."""
    assert BOOKS({"home_over_9.5": "Bet365"}, {}) == {}


# --- when the fetcher runs --------------------------------------------------------------

def _odds_workflow():
    return _src(os.path.join("..", ".github", "workflows", "odds.yml"))


def test_a_scheduled_run_does_the_window_pass_too():
    """THE BUG THIS FIXES, PINNED. The window pass was gated on
    `github.event.schedule == '41 6 * * *'`, and GitHub never reported that schedule: the
    comparison was false on every run, including the one that fired at 06:16, so the pass
    had never run once. Every automatic fetch the app had ever done was a 90-minute
    closing capture, which is why prices lagged markets that opened during the day.
    """
    wf = _odds_workflow()
    # The default for a run with no inputs — a cron — must be both passes.
    block = wf[wf.index('mode="${MODE:-}"'):]
    block = block[:block.index("minutes=")]
    assert 'mode="both"' in block
    # The ASSIGNMENT, not the word: a comment mentioning the closing pass is fine, a
    # fallback that sets it is the bug coming back.
    assert 'mode="closing"' not in block, \
        "a scheduled run must not default to the closing pass alone"


def test_the_window_pass_no_longer_depends_on_which_cron_fired():
    """Whatever replaces this must not reintroduce the dependency: GitHub does not
    reliably say which schedule started a run, so anything keyed to it silently does
    nothing."""
    wf = _odds_workflow()
    assert "HOUR:" not in wf
    assert "$HOUR" not in wf


def test_both_crons_are_still_there():
    """The second cron is kept as a fire aimed at the morning in case the hourly one is
    dropped — which, measured over five days, it is about 80% of the time."""
    wf = _odds_workflow()
    assert re.search(r'cron:\s*"17 \* \* \* \*"', wf)
    assert re.search(r'cron:\s*"41 6 \* \* \*"', wf)


def test_the_preview_prints_the_bookmaker_beside_the_source():
    """The preview is how "where did this price come from" gets answered, and the source
    alone does not answer it — `api` does not say which of 33 books."""
    wf = _odds_workflow()
    assert "r.get('book')" in wf
