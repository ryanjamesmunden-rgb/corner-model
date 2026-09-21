"""The settlement audit, tested on the failure it was written to catch.

WHY IT EXISTS. measure_calibration found the model calibrated over 11,590 replayed spots
(+0.1) while the published ledger's 3+ picks went 6 of 15 — p = 0.004 against the model's
own 75.3%, and implausible on its face. The suspect is settlement._pick_side, which
chooses a pick's side by TOKEN OVERLAP ON TEAM NAMES. Grade the wrong side and the
OPPONENT's corner count is recorded; the pick still settles cleanly to a confident loss,
so nothing anywhere says a word.

WHAT THESE GUARD. An audit's own failure mode is the expensive one: a false clean bill
sends the investigation down the wrong road, and a false accusation gets correct history
"repaired". So:

  - It must find a swapped side. That is the whole point.
  - It must not need names to do it, or it inherits the bug it is auditing.
  - A pick it cannot resolve must be reported as unchecked, never as clean. Two clubs
    sharing a name is exactly where a guess would invent a finding.
  - A cup pick carries `ucl` as its league while its team doc lives under the domestic
    league, so a (league, name) lookup alone fails on every European tie — silently, and
    in the direction of "nothing wrong here".
  - "X+" includes X. An off-by-one here would report every pick that landed exactly on
    its line as mis-graded, which is a fabricated finding on real history.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit_settlement import (  # noqa: E402
    api_team_id, audit_one, derive_side, hit_at, recorded_hit, resolve_team, tally,
)

# Arsenal (42) at home to Chelsea (49). Arsenal won 8 corners, Chelsea 2.
STATS = {"home_id": 42, "away_id": 49, "home_corners": 8, "away_corners": 2}
FIXTURE = {"home_team_id": "eng-pl-42", "away_team_id": "eng-pl-49"}


def pick(**kw):
    base = {"auto": True, "team": "Arsenal", "league_id": "eng-pl", "line": 4,
            "venue": "home", "settled_side": "home", "result_corners": 8,
            "status": "won", "date": "2026-09-01", "home": "Arsenal", "away": "Chelsea"}
    base.update(kw)
    return base


class TestItFindsASwappedSide:
    def test_a_pick_graded_on_the_opponent_is_caught(self):
        # The failure under investigation: Arsenal's pick graded as the away side, so
        # Chelsea's 2 corners were recorded and a 4+ that actually won reads as a loss.
        r = audit_one(pick(settled_side="away", result_corners=2, status="lost"),
                      FIXTURE, STATS, 42)
        assert r["true_side"] == "home"
        assert r["true_corners"] == 8
        joined = " | ".join(r["problems"])
        assert "graded as away, is actually home" in joined
        assert "recorded 2 corners, fixture says 8" in joined
        assert "graded LOST, should be WON" in joined

    def test_a_correctly_graded_pick_raises_nothing(self):
        assert audit_one(pick(), FIXTURE, STATS, 42)["problems"] == []

    def test_the_side_is_derived_from_ids_not_names(self):
        # The names on the pick are deliberately wrong here. If the audit consulted them
        # it would agree with the bug it exists to find.
        r = audit_one(pick(team="Not A Real Name", home="Wrong", away="Also Wrong"),
                      FIXTURE, STATS, 42)
        assert r["true_side"] == "home"
        assert r["problems"] == []

    def test_a_pick_on_neither_team_is_a_finding_not_a_pass(self):
        # Settled against some other fixture entirely. Silent today.
        r = audit_one(pick(), FIXTURE, STATS, 999)
        assert r["true_side"] is None
        assert "neither side" in " ".join(r["problems"])
        assert r["checkable"] is False

    def test_the_fixture_doc_is_used_when_stats_lack_ids(self):
        r = audit_one(pick(), FIXTURE, {"home_corners": 8, "away_corners": 2}, 42)
        assert r["true_side"] == "home"


class TestWhatItRefusesToGuess:
    def test_an_unresolvable_team_is_unchecked_rather_than_clean(self):
        r = audit_one(pick(), FIXTURE, STATS, None)
        assert r["checkable"] is False
        assert "not resolvable" in " ".join(r["problems"])

    def test_a_shared_name_across_leagues_is_declined(self):
        # Guessing here would pin a finding on a pick using another club's result.
        by_name = {"Arsenal": {42, 777}}
        assert resolve_team(pick(league_id="xx"), {}, by_name) is None

    def test_a_cup_pick_resolves_through_the_name_when_the_league_pair_misses(self):
        # A ucl pick's team doc lives under eng-pl. Without this fallback every European
        # tie is reported unchecked, and an audit that checks nothing reports nothing.
        by_pair = {("eng-pl", "Arsenal"): 42}
        by_name = {"Arsenal": {42}}
        assert resolve_team(pick(league_id="ucl"), by_pair, by_name) == 42

    def test_the_league_pair_wins_over_the_name_when_both_exist(self):
        by_pair = {("eng-pl", "Arsenal"): 42}
        by_name = {"Arsenal": {42, 777}}
        assert resolve_team(pick(), by_pair, by_name) == 42


class TestTheLineItself:
    def test_x_plus_includes_x(self):
        # Landing exactly on the line is a WIN. Getting this backwards would report every
        # such pick as mis-graded — a fabricated finding, on real history, at scale.
        assert hit_at(4, 4) == 1
        assert hit_at(4, 3) == 0

    def test_a_missing_corner_count_has_no_answer(self):
        assert hit_at(4, None) is None
        assert hit_at(None, 8) is None

    def test_a_void_has_no_recorded_hit(self):
        assert recorded_hit(pick(status="void")) is None
        assert recorded_hit(pick(status="pending")) is None


class TestIdParsing:
    def test_an_internal_id_yields_its_api_tail(self):
        assert api_team_id("eng-pl-42") == 42
        assert api_team_id("ucl-42") == 42

    def test_junk_is_none_rather_than_an_exception(self):
        for bad in (None, "", "eng-pl-", "eng-pl-abc"):
            assert api_team_id(bad) is None

    def test_derive_side_needs_a_team(self):
        assert derive_side(None, 42, 49) is None
        assert derive_side(42, None, None) is None


class TestTheHeadlineNumber:
    def test_it_states_what_the_record_should_have_said(self):
        rows = [audit_one(pick(settled_side="away", result_corners=2, status="lost"),
                          FIXTURE, STATS, 42),
                audit_one(pick(), FIXTURE, STATS, 42)]
        t = tally(rows)
        assert t == {"n": 2, "was": 1, "should": 2, "was_rate": 50.0,
                     "should_rate": 100.0, "changed": 1}

    def test_unresolvable_rows_are_left_out_of_the_arithmetic(self):
        # Counting them either way would move the headline using picks nothing verified.
        rows = [audit_one(pick(), FIXTURE, STATS, 42),
                audit_one(pick(), FIXTURE, STATS, None)]
        assert tally(rows)["n"] == 1

    def test_nothing_checkable_is_none_rather_than_a_divide_by_zero(self):
        assert tally([audit_one(pick(), FIXTURE, STATS, None)]) is None
        assert tally([]) is None
