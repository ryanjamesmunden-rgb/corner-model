"""Naming a reason for every pending slip.

WHY THIS MATTERS MORE THAN IT LOOKS. "Pending" on the Bets page covers two states that
need opposite responses — a match not played yet, and a match played that the settler
could not grade — and the page shows them identically. A diagnostic that got the
classification wrong would be worse than none: it would give a confident reason for a slip
that is fine, or pronounce a stuck slip healthy.

WHAT THESE GUARD:

  - The grace period. A match does not owe you a corner count at kick-off + 1 minute.
    Calling that "corners not synced" would report the whole of a Saturday afternoon as
    broken.
  - The type check firing only where it costs something. A string id matters when there is
    a cached fixture it should have matched; on a fixture with nothing cached the real
    answer is missing data, and saying "type mismatch" would send someone to fix working
    code.
  - The audit not reproducing the bug it measures. It keys its own lookup through
    stats_key; if it looked up by the raw id it would report every slip as uncached and
    call it a sync problem.
  - The verdict naming a cause the counts support, and saying "nothing is stuck" when
    nothing is.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit_bets import (  # noqa: E402
    SETTLE_GRACE_HOURS, classify, raw_id, stats_key, verdict, why_pending,
)

NOW = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


def at(hours):
    """An ISO kick-off `hours` before NOW (negative for the future)."""
    return (NOW - timedelta(hours=hours)).isoformat()


def bet(**kw):
    base = {"bet_id": "bet_1", "fixture_id": "ned-ed-12345", "league_id": "ned-ed",
            "api_fixture_id": 12345, "market_key": "total_over_9.5", "status": "pending",
            "home_name": "Ajax", "away_name": "PSV", "kickoff": at(26)}
    return {**base, **kw}


def cached(home=6, away=5, fid=12345):
    return {fid: {"_id": fid, "home_corners": home, "away_corners": away}}


class TestAMatchNotPlayedYetIsNotABug:
    def test_a_future_kickoff_is_not_played_yet(self):
        reason, _ = why_pending(bet(kickoff=at(-30)), {}, NOW)
        assert reason == "not played yet"

    def test_a_match_inside_the_grace_window_is_not_late(self):
        # Ninety minutes plus half-time plus stoppage plus the provider's own lag. Calling
        # this "corners not synced" would report a live Saturday as broken.
        reason, _ = why_pending(bet(kickoff=at(SETTLE_GRACE_HOURS - 0.5)), {}, NOW)
        assert reason == "not played yet"

    def test_past_the_grace_window_it_is_answerable(self):
        reason, _ = why_pending(bet(kickoff=at(SETTLE_GRACE_HOURS + 1)), {}, NOW)
        assert reason != "not played yet"

    def test_the_detail_says_which_side_of_kick_off_it_is_on(self):
        _, ahead = why_pending(bet(kickoff=at(-30)), {}, NOW)
        assert "away" in ahead
        _, inside = why_pending(bet(kickoff=at(1)), {}, NOW)
        assert "grace" in inside


class TestTheReasonsForAStuckSlip:
    def test_a_slip_with_a_cached_result_would_settle_now(self):
        reason, detail = why_pending(bet(), cached(), NOW)
        assert reason == "would settle now"
        assert "6-5" in detail

    def test_nothing_cached_is_missing_data(self):
        reason, detail = why_pending(bet(), {}, NOW)
        assert reason == "corners not synced"
        assert "12345" in detail

    def test_a_null_corner_count_is_its_own_reason(self):
        reason, _ = why_pending(bet(), cached(home=None), NOW)
        assert reason == "corners missing"

    def test_an_unrecoverable_id_can_never_settle(self):
        slip = bet(api_fixture_id=None, fixture_id="other-1", league_id="ned-ed")
        reason, _ = why_pending(slip, cached(), NOW)
        assert reason == "no provider id"

    def test_an_unparseable_market_is_named_rather_than_blamed_on_the_data(self):
        reason, detail = why_pending(bet(market_key="nonsense"), cached(), NOW)
        assert reason == "market unparseable"
        assert "nonsense" in detail

    def test_a_slip_with_no_kickoff_is_still_classified(self):
        # Not classifiable as early or late, and it must not crash or silently vanish.
        reason, detail = why_pending(bet(kickoff=None), cached(), NOW)
        assert reason in ("corners not synced", "no provider id")
        assert "no kickoff" in detail


class TestTheTypeMismatchIsItsOwnFinding:
    """A string id and missing data look identical from the Bets page and have opposite
    fixes: one is a bug in our code, the other is data we do not have."""

    def test_a_string_id_against_an_int_keyed_cache_is_a_type_mismatch(self):
        # The slip's id is the digits as a string; the cache holds the int. The audit
        # normalises to find the document, then reports that the settler would not have.
        slip = bet(api_fixture_id="12345")
        reason, detail = why_pending(slip, cached(), NOW)
        assert reason == "key type mismatch"
        assert "str" in detail and "int" in detail

    def test_it_only_fires_where_there_was_something_to_match(self):
        # With nothing cached, the honest answer is missing data. Reporting a type mismatch
        # here would send someone to fix code that is working.
        reason, _ = why_pending(bet(api_fixture_id="12345"), {}, NOW)
        assert reason == "corners not synced"

    def test_a_correctly_typed_slip_is_never_flagged(self):
        reason, _ = why_pending(bet(api_fixture_id=12345), cached(), NOW)
        assert reason == "would settle now"

    def test_a_non_numeric_id_is_not_a_type_mismatch(self):
        # A synthesized fallback fixture has no int form. There is no type to fix.
        reason, _ = why_pending(bet(api_fixture_id="fallback-abc"), cached(), NOW)
        assert reason != "key type mismatch"

    def test_the_audit_does_not_reproduce_the_bug_it_measures(self):
        # stats_key on both sides of ITS lookup. Looking up by the raw id would make every
        # string-id slip read as uncached, and the audit would blame the sync for a bug in
        # our own join.
        assert stats_key("12345") == stats_key(12345) == 12345
        assert stats_key("fallback-abc") == "fallback-abc"
        assert stats_key(True) is None       # bool is an int; fixture 1 is a real fixture
        assert stats_key("") is None

    def test_it_reads_the_slip_rather_than_the_fixed_normaliser(self):
        # raw_id is NOT server._api_fixture_id, on purpose. That one now coerces to int,
        # which is the fix — importing it here would make the audit agree with itself and
        # report every historical row as healthy, which is exactly the blind spot that let
        # the bug ship in the first place.
        import server
        assert raw_id(bet(api_fixture_id="12345")) == "12345"     # as stored
        assert server._api_fixture_id(bet(api_fixture_id="12345")) == 12345   # as fixed
        assert raw_id(bet(fixture_id="ned-ed-777", api_fixture_id=None)) == "777"


class TestTheVerdict:
    def test_nothing_stuck_says_so(self):
        groups = classify([bet(kickoff=at(-30)), bet(kickoff=at(-50))], {}, NOW)
        out = verdict(groups, NOW)
        assert "Nothing is stuck" in out

    def test_a_type_mismatch_is_named_as_a_bug_not_as_missing_data(self):
        slips = [bet(bet_id=f"b{i}", api_fixture_id="12345") for i in range(4)]
        out = verdict(classify(slips, cached(), NOW), NOW)
        assert "KEY TYPE BUG" in out
        assert "Nothing to fetch" in out

    def test_missing_corners_points_at_coverage_rather_than_at_the_code(self):
        slips = [bet(bet_id=f"b{i}") for i in range(4)]
        out = verdict(classify(slips, {}, NOW), NOW)
        assert "sync_real" in out
        assert "never voids" in out

    def test_slips_ready_to_grade_point_at_the_settler_not_being_reached(self):
        out = verdict(classify([bet()], cached(), NOW), NOW)
        assert "page load" in out

    def test_classify_groups_every_slip_exactly_once(self):
        slips = [bet(bet_id="a", kickoff=at(-30)), bet(bet_id="b"),
                 bet(bet_id="c", api_fixture_id="12345"),
                 bet(bet_id="d", market_key="nonsense")]
        groups = classify(slips, cached(), NOW)
        assert sum(len(v) for v in groups.values()) == len(slips)
