"""A bet has to outlive the fixture it was placed against.

FOUND LIVE. Every slip on the Bets page sat at "pending" for ever, which made the page a
list of things nobody could tell you the result of.

The settler was there and ran on every page load. What starved it was the sync: it deletes
every fixture in a league and re-inserts only the UPCOMING ones, so a match left
db.fixtures the moment it kicked off — well before its corners were synced. Settlement
joined through that collection to find the provider's id, found nothing, returned None for
the outcome, and skipped. Nothing logged, nothing failed, and the bet was never graded.

So the provider's id now rides on the bet, and settlement reads nothing but fixture_stats.

AND THEN THE SAME BUG SURVIVED THE FIX, IN THE TYPE. The recovery path strips the league
prefix off `fixture_id`, which leaves a STRING, while fixture_stats is keyed by the
provider's id as the provider sends it — a JSON number, so an int. Mongo's `$in` does not
equate "12345" with 12345, so every slip that had to recover its id matched nothing, for
ever, and looked exactly like a match that had not kicked off. The digits were right and
the type was wrong.

The tests below had asserted the string, which is how it survived: they checked the value
the function returned without ever checking it against the thing it is used to look up.
They now assert the int, and TestTheKeyTypeMatchesTheCache checks the round trip against
the type sync_real actually writes.
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
        # sync_real copies the provider's int onto the fixture and create_bet copies it
        # onto the slip, so this is the ordinary case and it arrives already an int.
        assert server._api_fixture_id(bet(api_fixture_id=998877)) == 998877

    def test_an_older_bet_recovers_it_from_the_fixture_id(self):
        # Every bet placed before this was stored with no api id, and they are the ones
        # sitting pending. fixture_id is "{league_id}-{api_id}", so it is recoverable —
        # here rather than in a one-off migration somebody has to remember to run.
        assert server._api_fixture_id(bet()) == 12345

    def test_a_league_id_containing_a_hyphen_is_handled(self):
        # "ned-ed" is the common case and naive splitting on "-" gets it wrong.
        assert server._api_fixture_id(
            bet(fixture_id="ned-ed-777", league_id="ned-ed")) == 777

    def test_the_stored_id_wins_over_the_derived_one(self):
        assert server._api_fixture_id(
            bet(api_fixture_id=4242, fixture_id="ned-ed-999")) == 4242

    def test_a_numeric_string_stored_on_an_old_slip_is_normalised(self):
        # Belt and braces: if anything ever wrote the id as a string, it must still match.
        assert server._api_fixture_id(bet(api_fixture_id="998877")) == 998877

    def test_nothing_recoverable_is_none_rather_than_a_guess(self):
        # A synthesized fallback fixture is an invented pairing, not a real match, and
        # must settle nothing.
        assert server._api_fixture_id(bet(fixture_id="other-1", league_id="ned-ed")) is None
        assert server._api_fixture_id(bet(fixture_id="", league_id="")) is None

    def test_a_synthesized_fixtures_non_numeric_id_is_left_alone(self):
        # It must not become None (that would hide it) and must not become a number
        # (there isn't one). Passing it through means it matches no cached fixture, which
        # is the intended outcome.
        assert server._api_fixture_id(bet(api_fixture_id="fallback-abc")) == "fallback-abc"


class TestTheKeyTypeMatchesTheCache:
    """The second half of the same bug, and the reason the first fix did not work.

    db.fixture_stats is keyed by `f["fixture"]["id"]` straight from the provider — a JSON
    number, so an int. A string id matches no document and Mongo reports nothing wrong.
    """

    def test_the_recovered_id_is_the_type_the_cache_is_keyed_by(self):
        # THE REGRESSION GUARD. This is the assertion whose absence let the bug ship: the
        # old test checked the digits and never the type.
        recovered = server._api_fixture_id(bet())
        cache_key = 12345          # what sync_real writes as fixture_stats._id
        assert recovered == cache_key
        assert isinstance(recovered, int)
        assert recovered is not False       # bool is an int; make sure that is not the path

    def test_a_recovered_id_and_a_carried_id_agree(self):
        # The same real match, one slip carrying the id and one having to recover it, must
        # resolve to the same key — otherwise half the slips on a fixture settle and half
        # do not, which is worse than none settling because it looks like bad luck.
        carried = server._api_fixture_id(bet(api_fixture_id=12345))
        recovered = server._api_fixture_id(bet(fixture_id="ned-ed-12345"))
        assert carried == recovered

    def test_stats_key_normalises_only_what_it_should(self):
        assert server._stats_key(12345) == 12345
        assert server._stats_key("12345") == 12345
        assert server._stats_key("  12345  ") == 12345
        assert server._stats_key("fallback-abc") == "fallback-abc"
        assert server._stats_key("") is None
        assert server._stats_key(None) is None
        # True == 1 in Python, and a bool reaching a fixture id means something upstream is
        # broken; returning 1 would silently grade the slip against fixture 1.
        assert server._stats_key(True) is None

    def test_the_settler_normalises_both_sides_of_the_join(self):
        # A document written with a string _id by an older writer must not become the new
        # thing that fails to match. The source asks for both forms and keys through
        # _stats_key, so neither storage shape can break the join.
        import inspect
        src = inspect.getsource(server.settle_pending_bets)
        assert "_stats_key(c[\"_id\"])" in src, \
            "the settler keys fixture_stats by its raw _id again — a string-keyed document " \
            "will silently match nothing"


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
