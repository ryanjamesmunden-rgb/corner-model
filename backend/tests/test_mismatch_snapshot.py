"""The mismatch record, which did not exist until the board was frozen.

Every other board on this site can be graded because something wrote it down before the
games were played. The mismatch board could not: it is computed from the current team
records, so once a fixture is played its row is gone and the averages behind it have
moved — with the graded game now inside them. history_export.py names the gap in those
terms, and everything that could be said about this board was a walk-forward replay.

What is pinned here is not that the numbers add up. It is the handful of ways a freeze
can quietly stop being a record:

  - settling it with a second copy of the settlement logic, which would drift from the
    one the public record uses until the two disagree about what a win is
  - rewriting a snapshot after kick-off
  - freezing numbers from stale data and leaving nobody able to tell
  - losing the sample each average rested on, which is the one thing this board does not
    gate on and therefore the one thing its record most needs
"""
import inspect
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from server import _grade_entries, WIN, LOSS  # noqa: E402


def mismatch_entry(name="Avai", line=6, opponent="Botafogo SP", **kw):
    """A row shaped the way snapshot_mismatches freezes one."""
    return {"team_id": f"t-{name}", "name": name, "league_id": "bra-sb",
            "line": line, "direction": "over", "subject": "team",
            "lambda": 7.21, "prob": 65.9, "team_for": 6.78, "opp_conceded": 7.22,
            "team_games": 9, "team_venue_used": "home", "team_recent": [9, 4, 8, 4, 7, 6],
            "opp_games": 9, "opp_venue_used": "away", "opp_recent": [7, 7, 2, 5, 7, 12],
            "opponent": opponent, "kickoff": "2026-10-24T19:00:00+00:00",
            "is_home": True, "fixture_id": "bra-sb-1520942", **kw}


def team_with(name="Avai", opponent="Botafogo SP", corners_for=7, date="2026-10-24"):
    return {f"t-{name}": {"team_id": f"t-{name}", "real_matches": [
        {"opponent": opponent, "date": date, "corners_for": corners_for,
         "corners_against": 4}]}}


class TestItSettlesThroughTheSameCodeAsTheRecord:
    """ONE SETTLEMENT IMPLEMENTATION, which is why the frozen row carries `direction`
    and `subject` although a mismatch is always a team over. A second copy would
    eventually disagree with the public record about what a win is, and the disagreement
    would be between two things this site publishes."""

    def test_clearing_the_line_is_a_win(self):
        rows = _grade_entries([mismatch_entry(line=6)], team_with(corners_for=7))
        assert rows[0]["result"] == WIN
        assert rows[0]["value"] == 7

    def test_missing_it_is_graded_as_a_miss_rather_than_disappearing(self):
        """The survivorship failure the freeze exists to prevent: a side that misses
        drops off the live board entirely, so grading the board afterwards would count
        only the rows that happened to come good."""
        rows = _grade_entries([mismatch_entry(line=8)], team_with(corners_for=3))
        assert rows[0]["result"] == LOSS
        assert rows[0]["value"] == 3

    def test_an_unplayed_game_is_pending_rather_than_dropped(self):
        rows = _grade_entries([mismatch_entry()], {})
        assert rows[0]["result"] == "pending"
        assert rows[0]["value"] is None

    def test_an_earlier_meeting_cannot_be_graded_in_its_place(self):
        """Matched on opponent AND on being at or after the recorded kick-off, so a
        reverse fixture played weeks earlier does not settle this claim."""
        rows = _grade_entries([mismatch_entry()],
                              team_with(corners_for=12, date="2026-08-02"))
        assert rows[0]["result"] == "pending"


class TestTheFreezeCannotQuietlyStopBeingARecord:
    """Source-level, because these are properties of the endpoint rather than of a
    return value, and each one has a specific way of failing silently."""

    def _src(self):
        return inspect.getsource(server.snapshot_mismatches)

    def test_it_refuses_to_replace_an_existing_tag(self):
        """A snapshot that could be rewritten after kick-off would be no snapshot."""
        src = self._src()
        assert "db.mismatch_snapshots.find_one" in src
        assert '"exists"' in src
        before_insert = src.split("insert_one")[0]
        assert '"exists"' in before_insert, \
            "the existing-tag check must return BEFORE the insert, not after it"

    def test_it_refuses_stale_data(self):
        """A stale freeze does not go unused — it becomes part of a published record,
        read later by people who cannot see how fresh it was."""
        src = self._src()
        assert "SNAPSHOT_MAX_AGE_HOURS" in src
        assert '"stale"' in src

    def test_it_freezes_the_sample_each_average_rested_on(self):
        """THE FIELD THIS BOARD NEEDS MOST, because _all_mismatches applies no minimum
        game count while BOARD_MIN_MISMATCH_GAMES gates the fixture-board angles at six.
        So a side whose average is one match ships beside one built on ten and prints
        identically. Counting the games afterwards reads a pool that has since grown."""
        src = self._src()
        for field in ("team_games", "opp_games", "team_venue_used", "opp_venue_used"):
            assert f'"{field}"' in src, f"{field} is not frozen with the row"

    def test_it_freezes_what_the_row_rested_on_not_just_the_verdict(self):
        src = self._src()
        for field in ("team_for", "opp_conceded", "lambda", "team_recent", "opp_recent"):
            assert f'"{field}"' in src

    def test_it_stores_the_fixture_it_will_be_graded_against(self):
        src = self._src()
        for field in ("fixture_id", "kickoff", "opponent"):
            assert f'"{field}"' in src
        assert "continue" in src, \
            "a row with no fixture_id has nothing to grade against and must be skipped"

    def test_the_results_endpoint_does_not_rescan_the_board(self):
        """Graded off synced match data and the frozen list, never a fresh scan — the
        whole point is that the list cannot change between the claim and the grading."""
        src = inspect.getsource(server.mismatch_snapshot_results)
        assert "_grade_entries" in src
        assert "_all_mismatches" not in src
