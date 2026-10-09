"""Everything the site has published, graded, week by week.

WHAT THIS PINS. The export's job is to be readable as a record, and the ways a record
goes wrong are not arithmetic ones:

  - a REPLAY must never use a game at or after the fixture it is grading. That is the
    whole discipline, and it fails silently: an off-by-one reads as a better model.
  - a rate must not exist without its denominator (recordCard.js).
  - a week with no snapshot must not look like a week with nothing on.
  - the published rows and the whole frozen board are different populations, and
    counting the second as the record counts claims the site never made.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import history_export as hx  # noqa: E402
from server import LOSS, WIN  # noqa: E402


def m(date, cf, opponent="X", home=True):
    return {"date": date, "corners_for": cf, "corners_against": 4,
            "goals_for": 1, "goals_against": 1, "opponent": opponent, "home": home}


class TestTheWeekKey:
    def test_an_iso_date_becomes_its_iso_week(self):
        assert hx.iso_week("2026-10-08") == "2026-W41"

    def test_a_timestamp_works_too(self):
        assert hx.iso_week("2026-10-08T19:45:00+00:00") == "2026-W41"

    def test_nothing_is_not_a_week(self):
        assert hx.iso_week(None) == "unknown"
        assert hx.iso_week("not a date") == "unknown"


class TestARateRefusesToExistWithoutADenominator:
    """recordCard.js: a rate without its denominator is unfalsifiable, and 0% is a claim
    about a record that has not been made yet."""

    def test_no_settled_games_has_no_rate(self):
        t = hx.tally([{"result": "pending"}, {"result": "pending"}])
        assert t["hit_rate"] is None and t["rows"] == 2 and t["settled"] == 0

    def test_a_rate_arrives_with_its_denominator(self):
        t = hx.tally([{"result": WIN}, {"result": LOSS}, {"result": "pending"}])
        assert (t["landed"], t["missed"], t["settled"], t["pending"]) == (1, 1, 2, 1)
        assert t["hit_rate"] == 50.0

    def test_everything_missing_is_zero_not_absent(self):
        # "nothing settled" and "everything missed" have to be distinguishable.
        assert hx.tally([{"result": LOSS}])["hit_rate"] == 0.0


class TestTheReplayNeverSeesTheResult:
    """The one that fails silently. An off-by-one here reads as a better model, and
    nothing in the output would say so."""

    # Nine at every game, then a 2. A window ending BEFORE the 2 is a clean 9-of-9.
    ROWS = [m(f"2026-08-{d:02d}", 9) for d in range(1, 10)] + [m("2026-08-10", 2)]
    TEAM = {"team_id": "t", "name": "T", "league_id": "l", "real_matches": ROWS}

    def test_the_window_is_strictly_before_the_graded_game(self):
        rows = hx.consistency_replay([self.TEAM], window=9)
        assert len(rows) == 1
        r = rows[0]
        assert r["played_at"] == "2026-08-10"
        assert r["line"] == 9, "the window must be the nine NINES, not include the 2"
        assert r["corners"] == 2 and r["result"] == LOSS

    def test_a_graded_game_is_never_inside_its_own_window(self):
        # Every row's line is the minimum of games strictly before it, so a row whose
        # own value is below its line MUST be possible. If the graded game leaked into
        # the window the line could never exceed it and nothing would ever lose.
        rows = hx.consistency_replay([self.TEAM], window=9)
        assert any(r["corners"] < r["line"] for r in rows)

    def test_the_line_is_the_highest_rung_all_of_them_cleared(self):
        team = {"team_id": "u", "name": "U", "league_id": "l",
                "real_matches": [m("2026-08-01", 9), m("2026-08-02", 6),
                                 m("2026-08-03", 8), m("2026-08-04", 7)]}
        rows = hx.consistency_replay([team], window=3)
        assert rows[0]["line"] == 6, "6 is the minimum of 9, 6, 8"
        assert rows[0]["result"] == WIN and rows[0]["corners"] == 7

    def test_a_window_longer_than_the_history_produces_nothing(self):
        assert hx.consistency_replay([self.TEAM], window=50) == []

    def test_a_run_that_only_clears_a_trivial_rung_is_not_a_row(self):
        # Below OVER_LINE_FLOOR there is no rung worth reporting — every side in
        # football clears 2+ every week.
        quiet = {"team_id": "q", "name": "Q", "league_id": "l",
                 "real_matches": [m(f"2026-08-{d:02d}", 2) for d in range(1, 8)]}
        assert hx.consistency_replay([quiet], window=5) == []

    def test_a_missing_corner_count_skips_rather_than_counts_as_zero(self):
        gappy = [m("2026-08-01", 9), {"date": "2026-08-02", "opponent": "X"},
                 m("2026-08-03", 9), m("2026-08-04", 9)]
        team = {"team_id": "g", "name": "G", "league_id": "l", "real_matches": gappy}
        rows = hx.consistency_replay([team], window=3)
        assert rows == [], "a gap is not a zero-corner game"

    def test_it_walks_in_date_order_whatever_order_the_matches_arrive_in(self):
        # Stored out of order on purpose. At window=1 every game after the first is
        # gradeable, so the sort is what decides which game precedes which — and if the
        # list were walked as stored, 2026-08-03 would be graded against nothing and
        # 2026-08-01 against the 8.
        shuffled = {"team_id": "s", "name": "S", "league_id": "l",
                    "real_matches": [m("2026-08-03", 8), m("2026-08-01", 9),
                                     m("2026-08-02", 6)]}
        rows = hx.consistency_replay([shuffled], window=1)
        assert [r["played_at"] for r in rows] == ["2026-08-02", "2026-08-03"]
        assert rows[0]["line"] == 9 and rows[0]["result"] == LOSS   # 6 against the 9
        assert rows[1]["line"] == 6 and rows[1]["result"] == WIN    # 8 against the 6

    def test_a_game_is_only_gradeable_once_the_window_exists_behind_it(self):
        # Three matches at window=2 leaves exactly one gradeable game, not two: the
        # second game has only one game behind it.
        team = {"team_id": "s2", "name": "S2", "league_id": "l",
                "real_matches": [m("2026-08-01", 9), m("2026-08-02", 6),
                                 m("2026-08-03", 8)]}
        rows = hx.consistency_replay([team], window=2)
        assert [r["played_at"] for r in rows] == ["2026-08-03"]


class TestTheRecordedRows:
    E = {"kickoff": "2026-10-08T19:45:00+00:00", "rank": 1, "lambda_total": 10.4,
         "home": "A", "away": "B", "league_name": "L"}

    def test_it_reads_the_key_the_grader_actually_returns(self):
        # THE ONE THAT FAILED SILENTLY. projection_record.grade returns `actual_total`;
        # the first version read `total` and therefore reported every fixture in the
        # database as ungraded — indistinguishable from a season with no results yet.
        graded = {"actual_total": 11, "error": 0.6, "abs_error": 0.6, "band": "10-11"}
        r = hx.projection_row("2026-10-07", self.E, graded)
        assert r["actual_total"] == 11 and r["settled"] is True
        assert r["error"] == 0.6 and r["band"] == "10-11"

    def test_an_ungraded_fixture_is_pending_not_zero(self):
        r = hx.projection_row("2026-10-07", self.E, {})
        assert r["actual_total"] is None and r["settled"] is False
        assert r["beat_projection"] is None, "unknown is not 'did not beat it'"

    def test_beat_projection_is_plainly_named_and_not_a_bet(self):
        assert hx.projection_row("t", self.E, {"actual_total": 11})["beat_projection"]
        assert not hx.projection_row("t", self.E, {"actual_total": 9})["beat_projection"]

    def test_a_projection_keeps_its_rank_so_the_top_row_is_findable(self):
        assert hx.projection_row("t", self.E, {})["rank"] == 1


class TestProjectionsAreSummarisedAsCalibrationNotAsARecord:
    """A projection is a number about a game, not a bet. A hit rate would need a line,
    and no line was published — so the summary is bias and accuracy."""

    ROWS = [{"week": "2026-W41", "settled": True, "error": 1.0, "abs_error": 1.0,
             "beat_projection": True},
            {"week": "2026-W41", "settled": True, "error": -3.0, "abs_error": 3.0,
             "beat_projection": False},
            {"week": "2026-W41", "settled": False, "error": None, "abs_error": None,
             "beat_projection": None}]

    def test_mean_error_is_signed_so_bias_is_visible(self):
        t = hx.projection_tally(self.ROWS)
        assert t["mean_error"] == -1.0, "the board ran high on balance"

    def test_mean_absolute_error_is_not_cancelled_out_by_the_sign(self):
        assert hx.projection_tally(self.ROWS)["mean_abs_error"] == 2.0

    def test_pending_rows_are_counted_but_never_averaged(self):
        t = hx.projection_tally(self.ROWS)
        assert t["rows"] == 3 and t["settled"] == 2 and t["pending"] == 1

    def test_nothing_settled_has_no_numbers_rather_than_zeroes(self):
        t = hx.projection_tally([{"week": "x", "settled": False, "error": None}])
        assert t["mean_error"] is None and t["over_rate"] is None

    def test_a_streak_row_carries_the_mismatch_it_rested_on(self):
        # opp_conceded, opp_bar and weak_opponent are not recomputable later — the
        # opponent's leakiness moves every time their league plays. If they are not
        # carried through here the record cannot say why a row qualified.
        g = {"kickoff": "2026-10-08", "name": "T", "line": 5, "result": WIN, "value": 7,
             "support": {"opp_conceded": 7.1, "opp_bar": 6.3, "league_avg": 5.2,
                         "weak_opponent": True, "lambda": 6.4}}
        r = hx.streak_row("2026-10-07", g)
        assert (r["opp_conceded"], r["opp_bar"], r["weak_opponent"]) == (7.1, 6.3, True)
        assert r["corners"] == 7 and r["result"] == WIN

    def test_a_streak_row_without_support_does_not_explode(self):
        r = hx.streak_row("t", {"kickoff": "2026-10-08", "name": "T"})
        assert r["opp_conceded"] is None and r["weak_opponent"] is None


class TestPublishedIsNotTheSameAsPresent:
    """The whole board is frozen; only some of it was shown. Counting the board as the
    record counts claims the site never made."""

    ROWS = [{"week": "2026-W41", "qualified": True, "result": WIN},
            {"week": "2026-W41", "qualified": False, "result": LOSS},
            {"week": "2026-W41", "qualified": False, "result": LOSS}]

    def test_the_two_populations_give_different_rates(self):
        published = [r for r in self.ROWS if r["qualified"]]
        assert hx.tally(published)["hit_rate"] == 100.0
        assert hx.tally(self.ROWS)["hit_rate"] == round(100 / 3, 1)


class TestTheWeeklyRollup:
    def test_rows_land_in_their_own_week_oldest_first(self):
        rows = [{"week": "2026-W42", "result": WIN}, {"week": "2026-W40", "result": LOSS},
                {"week": "2026-W41", "result": WIN}]
        assert [w for w, _ in hx.weekly(rows)] == ["2026-W40", "2026-W41", "2026-W42"]

    def test_each_week_keeps_its_own_denominator(self):
        rows = [{"week": "2026-W41", "result": WIN}, {"week": "2026-W41", "result": LOSS},
                {"week": "2026-W42", "result": WIN}]
        by = dict(hx.weekly(rows))
        assert by["2026-W41"]["hit_rate"] == 50.0 and by["2026-W41"]["settled"] == 2
        assert by["2026-W42"]["hit_rate"] == 100.0 and by["2026-W42"]["settled"] == 1


class TestCoverageMakesAGapVisible:
    """A week with no snapshot and a week with nothing on look identical in a table that
    only counts rows, and the first is a hole in the record."""

    def test_every_week_between_the_first_and_last_tag_is_listed(self):
        weeks = hx._weeks_between(["2026-09-28", "2026-10-19"])
        assert weeks[0] == hx.iso_week("2026-09-28")
        assert hx.iso_week("2026-10-12") in weeks
        assert weeks[-1] == hx.iso_week("2026-10-19")

    def test_a_single_day_is_a_single_week(self):
        assert hx._weeks_between(["2026-10-08"]) == ["2026-W41"]

    def test_no_tags_at_all_is_empty_rather_than_a_crash(self):
        assert hx._weeks_between([]) == []


class TestTheCsv:
    def test_it_has_a_header_and_one_line_per_row(self):
        out = hx.to_csv([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
        lines = out.strip().splitlines()
        assert lines[0] == "a,b" and len(lines) == 3

    def test_no_rows_is_empty_rather_than_a_lone_header(self):
        assert hx.to_csv([]) == ""


def test_history_depth_says_why_a_replay_window_may_be_empty():
    """Early in a season almost nobody has twenty games on file, and a replay of zero
    rows must be explained rather than read as nothing having happened."""
    teams = [{"real_matches": [m("2026-08-01", 5)] * n} for n in (4, 12, 25)]
    d = hx.history_depth(teams)
    assert d["teams"] == 3 and d["min"] == 4 and d["max"] == 25 and d["median"] == 12
    assert d["with_20"] == 1 and d["with_10"] == 2
