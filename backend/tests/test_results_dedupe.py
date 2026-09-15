"""The record must count a claim once, however many days it was frozen on.

The streak snapshot ran weekly, so no entry could appear twice and nothing needed to say
so. It runs daily now, with an overlapping two-day horizon deliberately chosen so that one
failed run does not lose a day — which means the same team, line and fixture is frozen on
consecutive days.

Counted once per snapshot, a Sunday game frozen on Friday and Saturday lands TWICE in the
headline rate. That is not cosmetic: it weights whichever fixtures sat longest in the
window, quietly, and nothing in the published output would reveal it.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def entry(fixture="fx1", team="t1", line=5, direction="over", subject="team", **kw):
    return {"fixture_id": fixture, "team_id": team, "line": line,
            "direction": direction, "subject": subject, **kw}


def dedupe(snapshots):
    """The same newest-first pass public_results makes, isolated.

    Kept in step with the endpoint by the source check at the bottom of this file: the
    rule is small enough to restate here, and a copy that drifts is worse than none.
    """
    seen, out = set(), []
    for snap in snapshots:
        fresh = []
        for e in snap:
            key = (e.get("fixture_id"), e.get("team_id"), e.get("line"),
                   e.get("direction"), e.get("subject"))
            if key in seen:
                continue
            seen.add(key)
            fresh.append(e)
        out.append(fresh)
    return out


class TestOneClaimPerFixture:
    def test_the_same_claim_frozen_twice_is_counted_once(self):
        # Sunday's game, frozen on Friday and again on Saturday.
        sat, fri = [entry()], [entry()]
        out = dedupe([sat, fri])           # newest first, as the endpoint sorts them
        assert [len(s) for s in out] == [1, 0]

    def test_the_newest_freeze_is_the_one_kept(self):
        # What is graded is the claim as it last stood before kick-off.
        sat = [entry(price=1.9)]
        fri = [entry(price=2.1)]
        out = dedupe([sat, fri])
        assert out[0][0]["price"] == 1.9

    def test_the_same_team_on_a_different_line_is_a_different_claim(self):
        # 5+ and 6+ on one team are two separate calls and both deserve grading.
        out = dedupe([[entry(line=5), entry(line=6)]])
        assert len(out[0]) == 2

    def test_over_and_under_on_the_same_line_are_different_claims(self):
        out = dedupe([[entry(direction="over"), entry(direction="under")]])
        assert len(out[0]) == 2

    def test_team_corners_and_match_corners_are_different_claims(self):
        out = dedupe([[entry(subject="team"), entry(subject="match")]])
        assert len(out[0]) == 2

    def test_two_teams_in_one_fixture_both_count(self):
        # Celtic and Rangers both carrying a run into the same derby is two claims.
        out = dedupe([[entry(team="celtic"), entry(team="rangers")]])
        assert len(out[0]) == 2

    def test_a_week_of_overlapping_daily_snapshots_settles_to_the_real_count(self):
        # Three fixtures, each frozen on three consecutive days. Nine entries, three
        # claims — the difference between an honest rate and one inflated threefold.
        day = [entry(fixture="a"), entry(fixture="b"), entry(fixture="c")]
        out = dedupe([list(day), list(day), list(day)])
        assert sum(len(s) for s in out) == 3


class TestTheEndpointStillDoesThis:
    def test_public_results_deduplicates(self):
        # A regression guard. Removing the pass would restore a headline rate that counts
        # a Sunday game once per day it was frozen on, with nothing failing to say so.
        import inspect
        src = inspect.getsource(server.public_results)
        assert "seen" in src and "_fresh" in src, \
            "public_results no longer deduplicates — daily snapshots overlap, so every " \
            "fixture will be counted once per day it was frozen on"

    def test_the_window_covers_a_year_of_daily_snapshots(self):
        # The unit changed under this constant: 12 meant twelve weeks, then twelve days.
        assert server.RESULTS_WEEKS >= 365
        clamp = inspect_clamp()
        assert clamp >= server.RESULTS_WEEKS, \
            f"the clamp ({clamp}) cuts the default ({server.RESULTS_WEEKS}) back"


def inspect_clamp():
    """The ceiling public_results applies, read out of the source."""
    import inspect
    import re
    src = inspect.getsource(server.public_results)
    m = re.search(r"min\(weeks,\s*(\d+)\)", src)
    return int(m.group(1)) if m else 0
