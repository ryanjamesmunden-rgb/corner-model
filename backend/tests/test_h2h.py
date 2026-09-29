"""Previous meetings between two sides, read out of the results cache.

WHAT THESE GUARD, in the order the mistakes would actually be made:

  - ORIENTATION. Every number is re-stated from the CURRENT fixture's home side, so a
    meeting where they were the visitors has to come back flipped. Get this wrong and the
    panel silently reports the opponent's corners as yours — the numbers all look
    plausible, which is why nothing would catch it.
  - THE VENUE AXIS IS SHARED. In a league table "home" is a different set of games for
    every team. In a head-to-head there is one pairing, so the home side's home meetings
    ARE the away side's away meetings. "Unbeaten in 3 away" has to name the games that
    side were actually the visitors in.
  - AN UNGRADED MEETING STOPS A RUN. Older cache rows can carry corners and no score. A
    run that steps over one is a claim about a match nobody checked, printed in the same
    type as one that was checked.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import h2h  # noqa: E402

HOME, AWAY = 42, 49  # provider team ids for the two sides of the fixture being viewed


def doc(date, host=HOME, hg=1, ag=0, hc=6, ac=4, league="eng-pl"):
    """One db.fixture_stats row. `host` is whoever was at home in THAT match."""
    guest = AWAY if host == HOME else HOME
    return {"date": date, "league_id": league, "home_id": host, "away_id": guest,
            "home_goals": hg, "away_goals": ag, "home_corners": hc, "away_corners": ac}


class TestOrientation:
    def test_a_meeting_at_home_is_reported_as_played(self):
        r = h2h.meeting_row(doc("2026-01-01", host=HOME, hg=2, ag=1, hc=7, ac=3), HOME)
        assert r["venue"] == "home"
        assert (r["goals_home_team"], r["goals_away_team"]) == (2, 1)
        assert (r["corners_home_team"], r["corners_away_team"]) == (7, 3)
        assert r["result"] == "home_team"

    def test_a_meeting_away_comes_back_flipped(self):
        # THE LOAD-BEARING CASE. The stored row says home 2-1 and 7-3 on corners, but the
        # side we are reporting for was the VISITOR, so every number must invert.
        r = h2h.meeting_row(doc("2026-01-01", host=AWAY, hg=2, ag=1, hc=7, ac=3), HOME)
        assert r["venue"] == "away"
        assert (r["goals_home_team"], r["goals_away_team"]) == (1, 2)
        assert (r["corners_home_team"], r["corners_away_team"]) == (3, 7)
        assert r["result"] == "away_team"

    def test_a_draw_is_a_draw_from_either_end(self):
        a = h2h.meeting_row(doc("2026-01-01", host=HOME, hg=1, ag=1), HOME)
        b = h2h.meeting_row(doc("2026-01-01", host=AWAY, hg=1, ag=1), HOME)
        assert a["result"] == b["result"] == "draw"

    def test_the_total_is_the_sum_of_both_ends(self):
        r = h2h.meeting_row(doc("2026-01-01", hc=7, ac=4), HOME)
        assert r["total_corners"] == 11

    def test_newest_meeting_first(self):
        rows = h2h.meetings([doc("2024-05-01"), doc("2026-02-01"), doc("2025-03-01")], HOME)
        assert [r["date"] for r in rows] == ["2026-02-01", "2025-03-01", "2024-05-01"]

    def test_the_list_is_capped(self):
        rows = h2h.meetings([doc(f"202{i}-01-01") for i in range(9)], HOME, limit=3)
        assert len(rows) == 3


class TestAMissingScore:
    def test_a_meeting_with_no_goals_is_not_graded(self):
        d = doc("2026-01-01")
        d["home_goals"] = d["away_goals"] = None
        r = h2h.meeting_row(d, HOME)
        assert r["graded"] is False and r["result"] is None
        # Corners survive: the sync refuses to store a fixture without them.
        assert r["total_corners"] == 10

    def test_an_ungraded_meeting_stops_a_run_rather_than_being_skipped(self):
        # THE ONE THAT MATTERS. Two wins, then a match with no score on file, then more
        # wins. Skipping the blank would print "unbeaten in 5" over a game nobody checked.
        blank = doc("2026-02-01")
        blank["home_goals"] = blank["away_goals"] = None
        rows = h2h.meetings([doc("2026-04-01"), doc("2026-03-01"), blank,
                             doc("2026-01-01"), doc("2025-12-01")], HOME)
        assert h2h.unbeaten_run(rows, "home_team") == 2

    def test_the_record_counts_only_graded_meetings_and_says_so(self):
        blank = doc("2026-02-01")
        blank["home_goals"] = blank["away_goals"] = None
        rec = h2h.build(h2h_docs := [doc("2026-03-01"), blank], HOME, "A", "B")["record"]
        assert h2h_docs  # the fixture list was not consumed
        assert rec["played"] == 1 and rec["ungraded"] == 1


class TestUnbeatenRuns:
    def test_a_loss_ends_it(self):
        rows = h2h.meetings([doc("2026-03-01", hg=1, ag=1),      # draw
                             doc("2026-02-01", hg=2, ag=0),      # win
                             doc("2026-01-01", hg=0, ag=3)],     # loss
                            HOME)
        assert h2h.unbeaten_run(rows, "home_team") == 2

    def test_the_most_recent_result_is_where_it_starts(self):
        rows = h2h.meetings([doc("2026-03-01", hg=0, ag=1),      # lost the last one
                             doc("2026-02-01", hg=2, ag=0)], HOME)
        assert h2h.unbeaten_run(rows, "home_team") == 0

    def test_the_other_side_reads_the_same_matches_the_other_way(self):
        rows = h2h.meetings([doc("2026-02-01", hg=3, ag=0)], HOME)
        assert h2h.unbeaten_run(rows, "home_team") == 1
        assert h2h.unbeaten_run(rows, "away_team") == 0

    def test_home_meetings_are_the_ones_this_side_hosted(self):
        rows = h2h.meetings([doc("2026-03-01", host=AWAY, hg=4, ag=0),   # thrashed away
                             doc("2026-02-01", host=HOME, hg=2, ag=0),   # won at home
                             doc("2026-01-01", host=HOME, hg=1, ag=0)],  # won at home
                            HOME)
        assert h2h.unbeaten_run(rows, "home_team") == 0                  # the away loss is latest
        assert h2h.unbeaten_run(rows, "home_team", venue="home") == 2

    def test_the_two_sides_share_one_venue_axis(self):
        """THE SPLIT THAT IS NOT LIKE THE LEAGUE TABLE'S.

        One pairing, so the home side's home meetings are the away side's away meetings.
        Both must point at the same matches from opposite ends."""
        rows = h2h.meetings([doc("2026-02-01", host=HOME, hg=2, ag=0)], HOME)
        assert h2h._venue_for("home_team", "home") == "home"
        assert h2h._venue_for("away_team", "away") == "home"
        assert h2h.unbeaten_run(rows, "home_team", venue="home") == 1
        assert h2h.unbeaten_run(rows, "away_team", venue="home") == 0

    def test_overall_ignores_venue_entirely(self):
        assert h2h._venue_for("home_team", "overall") is None
        assert h2h._venue_for("away_team", "overall") is None

    def test_a_run_shorter_than_the_floor_is_not_printed(self):
        rows = h2h.meetings([doc("2026-02-01", hg=1, ag=0), doc("2026-01-01", hg=1, ag=0)], HOME)
        assert h2h.runs_for(rows, "home_team") == []

    def test_a_run_that_clears_the_floor_carries_what_it_was_out_of(self):
        rows = h2h.meetings([doc(f"2026-0{i}-01", hg=1, ag=0) for i in range(1, 5)], HOME)
        runs = h2h.runs_for(rows, "home_team")
        assert runs[0]["split"] == "overall"
        assert runs[0]["run"] == 4 and runs[0]["played"] == 4

    def test_the_longest_run_is_listed_first(self):
        rows = h2h.meetings([doc("2026-04-01", host=HOME, hg=1, ag=0),
                             doc("2026-03-01", host=AWAY, hg=0, ag=1),
                             doc("2026-02-01", host=HOME, hg=1, ag=0),
                             doc("2026-01-01", host=HOME, hg=2, ag=0)], HOME)
        runs = h2h.runs_for(rows, "home_team")
        assert [r["run"] for r in runs] == sorted([r["run"] for r in runs], reverse=True)


class TestCornerTotals:
    def test_the_averages_travel_with_their_count(self):
        rows = h2h.meetings([doc("2026-02-01", hc=7, ac=4), doc("2026-01-01", hc=5, ac=4)], HOME)
        c = h2h.corner_totals(rows)
        assert c["played"] == 2
        assert c["avg_total"] == 10.0
        assert c["avg_home_team"] == 6.0 and c["avg_away_team"] == 4.0
        assert c["highest"] == 11 and c["lowest"] == 9

    def test_an_away_meeting_is_averaged_from_the_right_end(self):
        rows = h2h.meetings([doc("2026-01-01", host=AWAY, hc=9, ac=2)], HOME)
        c = h2h.corner_totals(rows)
        assert c["avg_home_team"] == 2.0 and c["avg_away_team"] == 9.0

    def test_no_meetings_means_no_numbers_rather_than_zeroes(self):
        # Zero would render as "0.0 corners a game between these two", which is a
        # measurement. There isn't one.
        assert h2h.corner_totals([]) is None


class TestThePayload:
    def test_an_empty_history_still_explains_itself(self):
        out = h2h.build([], HOME, "Arsenal", "Chelsea")
        assert out["meetings"] == [] and out["corners"] is None
        assert out["record"]["played"] == 0
        # The panel must not be able to say "first ever meeting" off the back of this.
        assert "as far as this site has been syncing" in out["window"]

    def test_both_sides_get_their_runs(self):
        out = h2h.build([doc(f"2026-0{i}-01", hg=1, ag=0) for i in range(1, 5)],
                        HOME, "Arsenal", "Chelsea")
        assert out["unbeaten"]["home_team"][0]["run"] == 4
        assert out["unbeaten"]["away_team"] == []
        assert out["home_name"] == "Arsenal" and out["away_name"] == "Chelsea"

    def test_the_competition_rides_on_each_row(self):
        # A 1-1 in a league game and a 1-1 in a second leg are different facts.
        out = h2h.build([doc("2026-01-01", league="ucl")], HOME, "A", "B")
        assert out["meetings"][0]["league_id"] == "ucl"


class TestTheQuery:
    def test_it_matches_the_pairing_both_ways_round(self):
        q = h2h.query(HOME, AWAY)
        assert q == {"$or": [{"home_id": HOME, "away_id": AWAY},
                             {"home_id": AWAY, "away_id": HOME}]}

    def test_a_synthesized_fixture_has_no_query_rather_than_a_loose_one(self):
        """A fixture with no provider team id must SKIP the lookup. A filter built from a
        None would be `{home_id: None}` — which matches nothing useful and, on the wrong
        day, everything."""
        assert h2h.query(None, AWAY) is None
        assert h2h.query(HOME, "eng-pl-49") is None

    def test_a_string_id_is_refused_because_the_cache_is_keyed_by_int(self):
        # The same type trap that left nineteen bets pending: Mongo's match is
        # type-strict, so "42" never equals 42 and the panel would come back empty with
        # no error anywhere.
        assert h2h.query("42", "49") is None
