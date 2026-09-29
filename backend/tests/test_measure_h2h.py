"""The head-to-head coverage probe.

WHAT A COVERAGE PROBE CAN GET WRONG, which is not what the panel can get wrong:

  - COUNTING FIXTURES THAT COULD NEVER HAVE HISTORY. A synthesized fixture carries a
    string team id and no provider id. Filed as "uncovered" it blames the cache for
    something the sync did, and the headline percentage drops for a reason that has no
    fix.
  - COLLAPSING THOSE INTO ONE PAIRING. Two missing ids make one (None, None) key, so
    every such fixture indexes to the same bucket — and the probe reports history for
    teams that have never played each other.
  - DISAGREEING WITH THE PANEL. The number wanted is what the panel will actually show,
    so the run count comes from h2h.build rather than from a second copy of the rule here.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import measure_h2h as m  # noqa: E402

A, B, C = 42, 49, 157


def stat(host, guest, date="2026-02-01T15:00:00Z", hg=2, ag=0, lid="eng-pl"):
    return {"home_id": host, "away_id": guest, "date": date, "league_id": lid,
            "home_goals": hg, "away_goals": ag, "home_corners": 7, "away_corners": 4}


def fx(fid, home, away, lid="eng-pl"):
    return {"fixture_id": fid, "league_id": lid, "status": "upcoming",
            "home_team_id": home, "away_team_id": away,
            "home_name": home, "away_name": away, "date": "2026-10-01T15:00:00Z"}


API = {"eng-pl-42": A, "eng-pl-49": B, "eng-pl-157": C, "eng-pl-x": "eng-pl-x"}


class TestThePairingKey:
    def test_a_tie_indexes_to_one_key_whichever_way_it_was_played(self):
        assert m.pair_key(A, B) == m.pair_key(B, A)

    def test_a_fixture_with_no_provider_id_has_no_key_at_all(self):
        """NOT A TUPLE OF Nones. Those collapse into one bucket, and the probe then
        reports history for teams that have never played."""
        assert m.pair_key(None, B) is None
        assert m.pair_key(A, "eng-pl-49") is None
        assert m.pair_key(None, None) is None

    def test_meetings_group_by_pairing(self):
        idx = m.index_meetings([stat(A, B), stat(B, A, date="2025-11-01T15:00:00Z"),
                                stat(A, C)])
        assert len(idx[m.pair_key(A, B)]) == 2
        assert len(idx[m.pair_key(A, C)]) == 1

    def test_a_row_with_no_ids_is_dropped_rather_than_bucketed(self):
        idx = m.index_meetings([{"home_id": None, "away_id": None, "date": "2026-01-01"}])
        assert dict(idx) == {}


class TestGrading:
    def test_a_meeting_with_a_score_is_graded(self):
        assert m.graded(stat(A, B)) is True

    def test_one_with_corners_and_no_score_is_not(self):
        # It still shows in the panel. It just stops an unbeaten run, which is a different
        # shortfall with a different fix (backfill_goals), so it is counted apart.
        assert m.graded(stat(A, B, hg=None, ag=None)) is False


class TestFixtureCoverage:
    def test_it_counts_the_meetings_behind_each_upcoming_fixture(self):
        idx = m.index_meetings([stat(A, B), stat(B, A)])
        rows = m.fixture_coverage([fx("f1", "eng-pl-42", "eng-pl-49")], API, idx)
        assert rows[0]["meetings"] == 2 and rows[0]["resolvable"] is True

    def test_a_pairing_with_no_history_reads_zero_not_missing(self):
        rows = m.fixture_coverage([fx("f1", "eng-pl-42", "eng-pl-49")], API, {})
        assert rows[0]["meetings"] == 0 and rows[0]["resolvable"] is True

    def test_a_synthesized_fixture_is_marked_unresolvable(self):
        # THE ONE THAT SKEWS THE HEADLINE. It has no provider id, so it could never have
        # history — counting it as uncovered blames the cache for the sync's doing.
        rows = m.fixture_coverage([fx("f1", "eng-pl-x", "eng-pl-49")], API, {})
        assert rows[0]["resolvable"] is False

    def test_ungraded_meetings_are_counted_separately(self):
        idx = m.index_meetings([stat(A, B), stat(A, B, hg=None, ag=None)])
        rows = m.fixture_coverage([fx("f1", "eng-pl-42", "eng-pl-49")], API, idx)
        assert rows[0]["meetings"] == 2 and rows[0]["graded"] == 1


class TestBuckets:
    def test_zero_is_its_own_bucket_because_it_is_the_finding(self):
        assert m.bucket(0) == "0"

    def test_and_everything_deep_lands_in_one(self):
        assert [m.bucket(n) for n in (1, 2, 3, 9)] == ["1", "2", "3+", "3+"]


class TestUnbeatenHits:
    def test_it_counts_fixtures_that_will_actually_print_a_run(self):
        """Through h2h.build, not through a second copy of the rule — the number wanted is
        what the panel will show."""
        stats = [stat(A, B, date=f"2026-0{i}-01T15:00:00Z") for i in range(1, 5)]
        idx = m.index_meetings(stats)
        fixtures = [fx("f1", "eng-pl-42", "eng-pl-49")]
        rows = m.fixture_coverage(fixtures, API, idx)
        assert m.unbeaten_hits(rows, idx, API, {"f1": fixtures[0]}) == 1

    def test_a_pairing_too_short_to_carry_a_run_is_not_counted(self):
        idx = m.index_meetings([stat(A, B)])
        fixtures = [fx("f1", "eng-pl-42", "eng-pl-49")]
        rows = m.fixture_coverage(fixtures, API, idx)
        assert m.unbeaten_hits(rows, idx, API, {"f1": fixtures[0]}) == 0

    def test_a_fixture_with_no_meetings_is_skipped_without_building_anything(self):
        fixtures = [fx("f1", "eng-pl-42", "eng-pl-49")]
        rows = m.fixture_coverage(fixtures, API, {})
        assert m.unbeaten_hits(rows, {}, API, {"f1": fixtures[0]}) == 0


class TestTheVerdict:
    def rows(self, covered, total):
        return [{"resolvable": True, "meetings": 1 if i < covered else 0}
                for i in range(total)]

    def test_an_empty_cache_is_named_as_a_sync_problem(self):
        assert "sync problem" in m.verdict(self.rows(0, 10), 0)

    def test_good_coverage_says_there_is_nothing_to_do(self):
        assert "nothing to change" in m.verdict(self.rows(8, 10), 5000)

    def test_thin_coverage_is_explained_rather_than_called_a_fault(self):
        # It is the cache's depth, which is a fact about this database's history.
        assert "not a fault" in m.verdict(self.rows(4, 10), 5000)

    def test_near_zero_coverage_points_at_the_sync_and_not_the_panel(self):
        v = m.verdict(self.rows(1, 100), 5000)
        assert "effectively dark" in v.lower()
        assert "fix is in the SYNC" in v

    def test_a_board_of_synthesized_fixtures_is_its_own_finding(self):
        rows = [{"resolvable": False, "meetings": 0} for _ in range(5)]
        assert "synthesized" in m.verdict(rows, 5000)
