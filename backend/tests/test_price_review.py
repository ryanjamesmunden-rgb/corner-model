"""Grading stored prices after the game, and remembering what a line did last time.

THE TRAP THIS FILE IS MOSTLY ABOUT is `both`. "Both teams 4+" is settled against the
WEAKER side's count, not the total and not either team's own — a game finishing 9-2 has
eleven corners and two teams, and only one of them reached four. Grade it off the total and
every both-teams line in the archive reads as a winner.

The second one is quieter: a fixture whose statistics were never fetched has no result. It
is not a loss. Counting it as one is the cheapest possible way to make a record look
different from what happened.
"""
import price_review as pr


def played(hc=6, ac=3, **kw):
    return {"fixture_id": "fx1", "date": "2026-11-21T15:00:00Z", "league_id": "eng-l1",
            "home_name": "Bradford", "away_name": "Barnsley",
            "home_corners": hc, "away_corners": ac,
            "total_corners": None if hc is None or ac is None else hc + ac,
            "corners_known": hc is not None and ac is not None, **kw}


# --- reading a market key --------------------------------------------------------------

class TestKeys:
    def test_the_three_shapes_the_stores_hold(self):
        assert pr.parse_key("home_over_4.5") == ("home", "over", 4.5)
        assert pr.parse_key("total_under_9.5") == ("total", "under", 9.5)
        assert pr.parse_key("both_over_3.5") == ("both", "over", 3.5)

    def test_a_whole_line_is_read_as_a_whole_line(self):
        # total_under_10 is the projection's own spelling and pushes on exactly ten.
        assert pr.parse_key("total_under_10") == ("total", "under", 10.0)

    def test_a_key_it_cannot_read_is_refused_rather_than_guessed(self):
        for bad in ("", None, "home_over", "corners_over_4.5", "home_over_x",
                    "first_half_over_3.5", "home-over-4.5"):
            assert pr.parse_key(bad) is None


# --- which number a line is settled against --------------------------------------------

class TestValue:
    def test_each_side_is_its_own_count(self):
        assert pr.value_for("home", 7, 2) == 7
        assert pr.value_for("away", 7, 2) == 2

    def test_the_total_is_both(self):
        assert pr.value_for("total", 7, 2) == 9

    def test_both_teams_is_the_WEAKER_side(self):
        # THE BUG THIS PREVENTS. 9-2 is eleven corners and a both-teams 4+ LOSER: one side
        # never reached four. Graded off the total it reads as a comfortable winner.
        assert pr.value_for("both", 9, 2) == 2
        assert pr.settle_key("both_over_3.5", 9, 2)["result"] == pr.LOSS
        assert pr.settle_key("total_over_3.5", 9, 2)["result"] == pr.WIN

    def test_both_teams_lands_only_when_both_do(self):
        assert pr.settle_key("both_over_3.5", 4, 4)["result"] == pr.WIN
        assert pr.settle_key("both_over_3.5", 12, 3)["result"] == pr.LOSS

    def test_an_unknown_corner_count_is_not_a_number(self):
        assert pr.value_for("home", None, 3) is None
        assert pr.value_for("total", 5, None) is None


# --- settling --------------------------------------------------------------------------

class TestSettle:
    def test_a_half_line_cannot_push(self):
        assert pr.settle_key("home_over_4.5", 5, 1)["result"] == pr.WIN
        assert pr.settle_key("home_over_4.5", 4, 1)["result"] == pr.LOSS

    def test_a_whole_line_pushes_on_the_number(self):
        assert pr.settle_key("total_under_10", 6, 4)["result"] == pr.VOID
        assert pr.settle_key("total_under_10", 6, 3)["result"] == pr.WIN
        assert pr.settle_key("total_under_10", 7, 4)["result"] == pr.LOSS

    def test_under_counts_the_line_itself_the_right_way(self):
        # Under 9.5 is nine or fewer.
        assert pr.settle_key("total_under_9.5", 5, 4)["result"] == pr.WIN
        assert pr.settle_key("total_under_9.5", 5, 5)["result"] == pr.LOSS

    def test_a_game_with_no_statistics_has_no_result(self):
        # Not a loss. The record must not move because a stats call failed.
        assert pr.settle_key("home_over_4.5", None, None) is None

    def test_an_unreadable_key_settles_to_nothing(self):
        assert pr.settle_key("first_half_over_3.5", 6, 3) is None


# --- one fixture reviewed ---------------------------------------------------------------

class TestReview:
    ODDS = {"home_over_4.5": 1.80, "away_over_4.5": 2.20,
            "total_over_9.5": 1.91, "both_over_3.5": 2.50}
    MODEL = {"home_over_4.5": {"prob": 68.0, "fair_odds": 1.47, "ev": 22.4},
             "away_over_4.5": {"prob": 40.0, "fair_odds": 2.50, "ev": -12.0},
             "total_over_9.5": {"prob": 60.0, "fair_odds": 1.67, "ev": 14.6},
             "both_over_3.5": {"prob": 35.0, "fair_odds": 2.86, "ev": -12.5}}

    def review(self, hc=6, ac=3):
        return pr.review_fixture(played(hc, ac), self.ODDS, self.MODEL)

    def test_every_stored_line_comes_back_winners_and_losers(self):
        rv = self.review()
        assert rv["priced"] == 4
        assert {ln["key"] for ln in rv["lines"]} == set(self.ODDS)

    def test_it_settles_each_one_against_the_right_number(self):
        # 6-3: home 4+ yes, away 4+ no, total 9+ yes (9 is not > 9.5 — so no), both no.
        got = {ln["key"]: ln["result"] for ln in self.review()["lines"]}
        assert got["home_over_4.5"] == pr.WIN
        assert got["away_over_4.5"] == pr.LOSS
        assert got["total_over_9.5"] == pr.LOSS      # exactly nine is under 9.5
        assert got["both_over_3.5"] == pr.LOSS

    def test_the_ev_plus_lines_are_counted_on_their_own(self):
        # The whole ladder includes rungs nobody would back, so its hit rate describes the
        # ladder rather than the model.
        rv = self.review()
        assert rv["ev_plus"] == 2                     # home 4+ and total 9.5
        assert rv["ev_plus_landed"] == 1              # only home 4+ came in
        assert rv["ev_plus_profit"] == round(0.80 - 1.0, 4)

    def test_profit_is_flat_stake_so_it_matches_the_record(self):
        rv = self.review(hc=7, ac=5)                  # everything lands
        assert rv["landed"] == 4
        assert rv["profit"] == round(0.80 + 1.20 + 0.91 + 1.50, 4)

    def test_a_fixture_without_corners_reviews_to_nothing_gradeable(self):
        rv = pr.review_fixture(played(None, None), self.ODDS, self.MODEL)
        assert rv["lines"] == [] and rv["priced"] == 0
        assert rv["corners_known"] is False

    def test_a_fixture_nobody_priced_is_still_a_fixture(self):
        rv = pr.review_fixture(played(), {}, {})
        assert rv["priced"] == 0 and rv["home_name"] == "Bradford"

    def test_a_line_with_no_model_row_still_settles(self):
        # Prices outlive the ladder that produced them; a key the model no longer makes
        # must still grade, with no EV rather than a zero one.
        rv = pr.review_fixture(played(), {"home_over_4.5": 1.8}, {})
        assert rv["lines"][0]["result"] == pr.WIN
        assert rv["lines"][0]["ev"] is None


# --- the week ----------------------------------------------------------------------------

class TestWeek:
    def week(self):
        odds = {"home_over_4.5": 1.80, "total_over_9.5": 2.10}
        model = {"home_over_4.5": {"prob": 68.0, "ev": 22.4},
                 "total_over_9.5": {"prob": 55.0, "ev": 15.5}}
        return [pr.review_fixture(played(7, 4, fixture_id="a"), odds, model),
                pr.review_fixture(played(2, 1, fixture_id="b"), odds, model),
                pr.review_fixture(played(None, None, fixture_id="c"), odds, model)]

    def test_the_tally_separates_what_was_graded_from_what_is_waiting(self):
        t = pr.tally(self.week())
        assert t["fixtures"] == 3 and t["graded"] == 2 and t["awaiting_corners"] == 1

    def test_the_ev_plus_rate_is_the_scoreboard(self):
        # Four +EV lines over two graded games; the 7-4 game lands both, the 2-1 neither.
        t = pr.tally(self.week())
        assert t["ev_plus"] == 4 and t["ev_plus_landed"] == 2
        assert t["ev_plus_rate"] == 50.0

    def test_a_week_with_nothing_settled_has_no_rate_rather_than_zero(self):
        t = pr.tally([pr.review_fixture(played(None, None), {"home_over_4.5": 1.8},
                                        {"home_over_4.5": {"ev": 5.0}})])
        assert t["ev_plus_rate"] is None
        assert t["graded"] == 0

    def test_nothing_at_all_is_an_empty_week_not_a_crash(self):
        assert pr.tally([])["fixtures"] == 0
        assert pr.best_landed([]) == []

    def test_the_best_landed_are_ranked_by_edge_not_by_price(self):
        # "Was the model right where it most disagreed with the book", not "what paid most".
        odds = {"home_over_4.5": 1.30, "total_over_9.5": 6.00}
        model = {"home_over_4.5": {"ev": 40.0}, "total_over_9.5": {"ev": 4.0}}
        got = pr.best_landed([pr.review_fixture(played(9, 6), odds, model)])
        assert [r["key"] for r in got] == ["home_over_4.5", "total_over_9.5"]

    def test_only_winners_reach_the_best_landed_list(self):
        odds = {"home_over_4.5": 1.80}
        model = {"home_over_4.5": {"ev": 30.0}}
        assert pr.best_landed([pr.review_fixture(played(2, 1), odds, model)]) == []


# --- what the line did last time ----------------------------------------------------------

class TestLastTime:
    def games(self):
        # Newest first, as the endpoint hands them over.
        return [
            {"fixture_id": "g3", "date": "2026-11-21", "home_name": "Bradford",
             "away_name": "Wigan", "home_corners": 7, "away_corners": 2,
             "odds": {"home_over_4.5": 1.62}},
            {"fixture_id": "g2", "date": "2026-11-14", "home_name": "Bradford",
             "away_name": "Lincoln", "home_corners": 3, "away_corners": 5,
             "odds": {"home_over_4.5": 1.75}},
        ]

    def test_it_finds_the_most_recent_priced_instance(self):
        got = pr.last_time("home_over_4.5", self.games())
        assert got["fixture_id"] == "g3"
        assert got["result"] == pr.WIN and got["book_odds"] == 1.62
        assert got["profit"] == round(1.62 - 1.0, 4)

    def test_a_miss_is_reported_as_readily_as_a_win(self):
        got = pr.last_time("home_over_4.5", self.games()[1:])
        assert got["result"] == pr.LOSS and got["profit"] == -1.0

    def test_a_game_with_no_price_for_that_key_is_skipped_not_graded(self):
        # "It landed" with no price attached answers half the question and invites the
        # reader to supply the other half from memory.
        games = self.games()
        games[0]["odds"] = {"total_over_9.5": 1.9}
        assert pr.last_time("home_over_4.5", games)["fixture_id"] == "g2"

    def test_a_game_with_no_corner_count_is_skipped_too(self):
        games = self.games()
        games[0]["home_corners"] = None
        assert pr.last_time("home_over_4.5", games)["fixture_id"] == "g2"

    def test_no_history_at_all_is_None_rather_than_an_empty_claim(self):
        assert pr.last_time("home_over_4.5", []) is None
        assert pr.last_time("home_over_4.5", None) is None

    def test_it_answers_about_the_key_it_was_asked_about(self):
        # home_over_4.5 and away_over_4.5 are different bets; a team is not always at home.
        games = self.games()
        assert pr.last_time("away_over_4.5", games) is None
