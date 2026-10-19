"""A fixture belongs to the competition it is PLAYED in, not to one team's league.

THE BUG THIS PINS, found in a live export. The readable streak export reported:

    Fixtures but no qualifying streak (4): 1. divisjon, Champions League,
                                           Conference League, Europa League

All three European competitions had fixtures in the window and the export said none of
them produced an angle. They had produced angles. Two separate mistakes stacked:

  1. `slot["league"]` was `r["league_name"]` — the TEAM's league. An Arsenal v Bayern tie
     was therefore filed under "Premier League", and WHICH domestic division it got
     depended on whichever side's streak row reached the slot first.
  2. The coverage check compared `{f["league"]}` (display names, now domestic) against
     fixture counts keyed on competition id (`ucl`). Those two sets could never
     intersect, so every cup was reported as empty no matter what it contained.

Neither failed loudly. The export rendered, the fixtures were all present, and the one
line a reader would use to check for a missing competition actively asserted the wrong
thing — which is worse than silence, because it reads as a finding.

AND THE CAUSE WAS A COPIED MAP. `_next_fixtures` already carried `league_id` and
`cross_league`, with a comment explaining that a cup tie needs to be identifiable as one.
`streaks()` built its own copy of that map and omitted exactly those two fields, so the
competition simply was not in the row to read.

These tests import leagues_meta only, so they run where importing server panics the
pydantic-core extension. What they can check is the invariant and the arithmetic; the
wiring itself is asserted by reading server.py's source, which needs no import.
"""
import ast
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from leagues_meta import CUP_IDS, MANAGED_LEAGUE_IDS  # noqa: E402

SERVER = pathlib.Path(__file__).parent.parent / "server.py"
SRC = SERVER.read_text(encoding="utf-8")

#: What sync_real stores per competition. Duplicated here because sync_real reads
#: API_FOOTBALL_KEY at import time and cannot be imported from a test.
UPCOMING_FIXTURES = 80


def _const(name):
    """Read a module-level int constant out of server.py without importing it."""
    for node in ast.walk(ast.parse(SRC)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not defined in server.py")


class TestTheFixtureSweepCanHoldWhatIsStored:
    """A cap below what the database holds drops rows, and the old one did."""

    def test_the_cap_clears_the_worst_case(self):
        worst = len(MANAGED_LEAGUE_IDS) * UPCOMING_FIXTURES
        cap = _const("NEXT_FIXTURE_SCAN")
        assert cap >= worst, (
            f"{len(MANAGED_LEAGUE_IDS)} competitions x {UPCOMING_FIXTURES} upcoming = "
            f"{worst} fixture documents, and the sweep caps at {cap}. The five leagues "
            f"added on 2026-10-19 are what pushed this past the old flat 2000.")

    def test_the_old_cap_really_was_too_small(self):
        """Pinned as arithmetic so the fix is not mistaken for a tidy-up: at 36
        competitions the previous 2000 was 880 documents short."""
        assert len(MANAGED_LEAGUE_IDS) * UPCOMING_FIXTURES > 2000

    def test_the_sweep_sorts_in_the_query_not_in_python(self):
        """THE ACTUAL FIX, and the bigger number is only the belt. Unsorted, a truncation
        keeps Mongo's natural order and the rows it drops are arbitrary — so some teams'
        next games went missing for no stateable reason. Sorted by date server-side, a
        truncation can only lose the games furthest away, which is the one thing a
        next-fixture map does not want."""
        body = SRC[SRC.index("async def _next_fixtures("):]
        body = body[:body.index("\n\n\n")]
        assert '.sort("date", 1)' in body, \
            "the fixture sweep must sort in the query, or truncation drops arbitrary rows"
        assert "NEXT_FIXTURE_SCAN" in body
        assert "to_list(2000)" not in body


class TestStreaksUsesTheSharedMap:
    def test_it_calls_the_helper_rather_than_rebuilding_it(self):
        """The copy is what lost `league_id`. One map, one definition, one place for the
        cup fields to live."""
        body = SRC[SRC.index("async def streaks("):]
        body = body[:body.index("@api_router.get(\"/features/coverage\")")]
        assert "await _next_fixtures(q)" in body
        # The tell-tale line of the old inline copy.
        assert 'next_fx[tid] = {"fixture_id"' not in body, \
            "streaks is rebuilding the next-fixture map again — it will drift again too"

    def test_the_helper_still_carries_both_cup_fields(self):
        """If either is dropped, the export silently goes back to labelling a European
        tie with a domestic league."""
        body = SRC[SRC.index("async def _next_fixtures("):]
        body = body[:body.index("\n\n\n")]
        assert '"league_id": fx["league_id"]' in body
        assert '"cross_league"' in body


class TestTheExportLabelsByCompetition:
    def _export(self):
        start = SRC.index("# match-total overs need a higher floor")
        return SRC[start:SRC.index("@api_router.get(\"/export\")")]

    def test_the_slot_takes_the_fixtures_competition(self):
        body = self._export()
        assert 'comp_id = nf.get("league_id")' in body
        assert 'comp_names.get(comp_id) or r["league_name"]' in body, \
            "the fixture's competition must win, with the team's league only as fallback"

    def test_coverage_compares_ids_not_display_names(self):
        """The second half of the false negative. Fixtures are counted under `ucl` and the
        angles were labelled "Premier League", so a name comparison could never match."""
        body = self._export()
        assert 'with_angles = {f.get("league_id") for f in fixtures}' in body
        assert 'with_angles = {f["league"] for f in fixtures}' not in body

    def test_a_cup_tie_is_flagged_on_the_heading(self):
        """A run earned in one league meeting a defence measured in another is weaker
        evidence, and the export should not make a reader infer that from a name."""
        assert "cup tie, form from two leagues" in self._export()

    def test_the_export_sweep_uses_the_same_cap_as_the_map(self):
        # It had its own 5000. Two caps on the same collection drift; this one also has
        # to clear the worst case, and deriving both from one constant is how.
        assert "to_list(NEXT_FIXTURE_SCAN)" in self._export()


class TestTheCupsAreStillWhatTheyWere:
    """Guards the assumption the whole fix rests on: cups hold fixtures and no teams."""

    def test_there_are_cups_to_get_wrong(self):
        assert CUP_IDS, "no cups, so none of the above is testing anything"

    def test_cups_are_in_the_managed_set(self):
        # Boot cleanup deletes fixtures whose league_id is unmanaged, so a cup outside
        # this set would have no fixtures to mislabel in the first place.
        assert CUP_IDS <= MANAGED_LEAGUE_IDS

    def test_a_cup_cannot_be_filtered_by_league_id_and_this_is_known(self):
        """WORTH WRITING DOWN RATHER THAN FIXING HERE. `streaks(league_id="ucl")` queries
        db.teams for league_id="ucl" and a cup stores no team documents, so a per-cup
        export is empty by construction and always was.

        That is a separate limitation from the labelling bug above — which affected the
        `all` export, the one actually used — and fixing it means resolving each cup
        fixture's two sides back to their domestic team documents. Pinned as a comment in
        a test so the next person meets it before spending an afternoon on it.
        """
        assert "ucl" in CUP_IDS
