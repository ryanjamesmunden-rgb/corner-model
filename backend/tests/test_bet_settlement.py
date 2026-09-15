"""A bet has to outlive the fixture it was placed against.

FOUND LIVE. Every slip on the Bets page sat at "pending" for ever, which made the page a
list of things nobody could tell you the result of.

The settler was there and ran on every page load. What starved it was the sync: it deletes
every fixture in a league and re-inserts only the UPCOMING ones, so a match left
db.fixtures the moment it kicked off — well before its corners were synced. Settlement
joined through that collection to find the provider's id, found nothing, returned None for
the outcome, and skipped. Nothing logged, nothing failed, and the bet was never graded.

So the provider's id now rides on the bet, and settlement reads nothing but fixture_stats.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def bet(**kw):
    base = {"bet_id": "bet_1", "fixture_id": "ned-ed-12345", "league_id": "ned-ed",
            "market_key": "total_over_9.5", "stake": 1.0, "book_odds": 2.0,
            "status": "pending"}
    return {**base, **kw}


class TestFindingTheFixtureId:
    def test_a_new_bet_carries_it(self):
        assert server._api_fixture_id(bet(api_fixture_id="998877")) == "998877"

    def test_an_older_bet_recovers_it_from_the_fixture_id(self):
        # Every bet placed before this was stored with no api id, and they are the ones
        # sitting pending. fixture_id is "{league_id}-{api_id}", so it is recoverable —
        # here rather than in a one-off migration somebody has to remember to run.
        assert server._api_fixture_id(bet()) == "12345"

    def test_a_league_id_containing_a_hyphen_is_handled(self):
        # "ned-ed" is the common case and naive splitting on "-" gets it wrong.
        assert server._api_fixture_id(
            bet(fixture_id="ned-ed-777", league_id="ned-ed")) == "777"

    def test_the_stored_id_wins_over_the_derived_one(self):
        assert server._api_fixture_id(
            bet(api_fixture_id="real", fixture_id="ned-ed-999")) == "real"

    def test_nothing_recoverable_is_none_rather_than_a_guess(self):
        # A synthesized fallback fixture is an invented pairing, not a real match, and
        # must settle nothing.
        assert server._api_fixture_id(bet(fixture_id="other-1", league_id="ned-ed")) is None
        assert server._api_fixture_id(bet(fixture_id="", league_id="")) is None


class TestGradingASlip:
    def test_a_total_over_that_landed(self):
        assert server.bet_outcome(bet(market_key="total_over_9.5"), 6, 5) == "won"

    def test_and_one_that_did_not(self):
        assert server.bet_outcome(bet(market_key="total_over_9.5"), 4, 5) == "lost"

    def test_a_home_line_reads_only_the_home_side(self):
        assert server.bet_outcome(bet(market_key="home_over_4.5"), 6, 1) == "won"
        assert server.bet_outcome(bet(market_key="away_over_4.5"), 6, 1) == "lost"

    def test_an_exact_whole_number_under_is_a_push_not_a_loss(self):
        # settle_streak_leg owns this rule and is called rather than copied, so the slip
        # and the streak boards cannot come to disagree about the same game.
        assert server.bet_outcome(bet(market_key="total_under_9"), 5, 4) == "void"

    def test_a_game_with_no_corners_synced_stays_pending(self):
        # None means "cannot be known yet" everywhere here. Guessing would invent a
        # result on somebody's money.
        assert server.bet_outcome(bet(), None, None) is None
        assert server.bet_outcome(bet(), 5, None) is None

    def test_an_unparseable_market_stays_pending(self):
        assert server.bet_outcome(bet(market_key="nonsense"), 5, 5) is None
        assert server.bet_outcome(bet(market_key=""), 5, 5) is None


class TestItNoLongerNeedsTheFixtureToStillExist:
    def test_the_settler_does_not_read_db_fixtures(self):
        # THE REGRESSION GUARD. The fix is precisely that this join is gone; a later tidy
        # -up that reinstates it would silently restore a Bets page of permanent
        # "pending" rows, and nothing would fail or log.
        import inspect
        src = inspect.getsource(server.settle_pending_bets)
        # The docstring explains the bug and names the collection; it is the CODE that
        # must not touch it. Checking the whole source would fail on its own explanation.
        body = src.replace(server.settle_pending_bets.__doc__ or "", "")
        assert "db.fixtures" not in body, \
            "settlement reads db.fixtures again — the sync deletes played fixtures, so " \
            "every bet will sit pending for ever"
        assert "fixture_stats" in src
