"""The counterfactual has to be honest about being a counterfactual.

WHAT THESE GUARD. The headline number — "N more would have landed one line lower" — is
the easiest number on this site to quote misleadingly, because it is true by construction
and says nothing on its own. So the tests are mostly about the things that make it
readable: the same games at every rung, a margin distribution that can tell a timid board
from a well-priced one, and a match total that is never assembled from half a game.

PURE MODULE, SO THESE RUN. ladder.py imports nothing from server, which is the only reason
they execute in an environment where importing server panics the pydantic-core extension.
The duplicated settle rule is cross-checked against server's own at script runtime; see
line_ladder.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ladder import (LOSS, RUNGS, VOID, WIN, by_line, fixture_totals, graded,  # noqa: E402
                    ladder, margin_of, margins, settle_at, shifted, tally,
                    total_ladder)


def row(line, value, direction="over", name="A", opponent="B", subject="team", **kw):
    return {"line": line, "value": value, "direction": direction, "name": name,
            "opponent": opponent, "subject": subject, **kw}


class TestSettling:
    def test_an_over_lands_on_the_line_or_above(self):
        assert settle_at(5, 5) == WIN
        assert settle_at(9, 5) == WIN
        assert settle_at(4, 5) == LOSS

    def test_an_under_voids_on_the_exact_line(self):
        """Matches server.settle_streak_leg. A push is not a win and not a loss, which is
        why every rate here divides by won+lost rather than by row count."""
        assert settle_at(4, 5, "under") == WIN
        assert settle_at(5, 5, "under") == VOID
        assert settle_at(6, 5, "under") == LOSS

    def test_a_missing_value_settles_to_nothing_rather_than_a_loss(self):
        """A game not yet played is not a losing bet, and counting it as one would make
        every rung look worse the more fixtures were pending."""
        assert settle_at(None, 5) is None
        assert settle_at(5, None) is None


class TestShifting:
    def test_an_easier_over_is_a_lower_line(self):
        assert shifted(5, -1) == 4
        assert shifted(5, -2) == 3
        assert shifted(5, 1) == 6

    def test_an_easier_under_is_a_HIGHER_line(self):
        """The offset means the same thing for both directions — negative is easier — so
        a reader comparing the two rungs is comparing like with like."""
        assert shifted(5, -1, "under") == 6
        assert shifted(5, 1, "under") == 4

    def test_the_floor_stops_an_over_sliding_to_nothing(self):
        # 0+ corners is cleared by every game ever played; a 100% row at the bottom of
        # the table would be noise wearing a result's clothes.
        assert shifted(1, -2) == 1
        assert shifted(2, -3, floor=1) == 1


class TestMargins:
    def test_positive_is_good_for_an_over(self):
        assert margin_of(row(5, 9)) == 4

    def test_positive_is_also_good_for_an_under(self):
        """Signed so the distribution can be read without knowing which direction each
        row was — otherwise 'cleared by 4' means two different things in one table."""
        assert margin_of(row(5, 1, "under")) == 4

    def test_a_miss_is_negative_either_way(self):
        assert margin_of(row(5, 3)) == -2
        assert margin_of(row(5, 7, "under")) == -2

    def test_the_distribution_separates_a_timid_board_from_a_tight_one(self):
        """THE NUMBER THE LADDER CANNOT GIVE. Both boards below would report 'one line
        lower wins more'; only this says which was mispriced."""
        timid = [row(4, 9), row(4, 10), row(4, 8), row(5, 11)]
        tight = [row(4, 4), row(4, 5), row(4, 4), row(5, 5)]
        assert margins(timid)["mean_cleared"] > 4
        assert margins(tight)["mean_cleared"] < 1
        assert margins(timid)["comfortable"] == 4
        assert margins(tight)["comfortable"] == 0

    def test_it_counts_the_ones_that_missed_by_exactly_one(self):
        rows = [row(5, 4), row(5, 4), row(5, 2), row(5, 8)]
        assert margins(rows)["by_one"] == 2

    def test_nothing_graded_returns_none_rather_than_a_zero_distribution(self):
        assert margins([row(5, None)]) is None
        assert margins([]) is None


class TestTheLadder:
    def test_a_lower_line_wins_at_least_as_often_always(self):
        """True by construction, and asserting it is how a sign error gets caught."""
        rows = [row(5, v) for v in (2, 4, 5, 6, 9, 11, 3, 7)]
        rungs = {r["offset"]: r for r in ladder(rows)}
        assert rungs[-1]["won"] >= rungs[0]["won"] >= rungs[1]["won"]

    def test_every_rung_is_scored_over_the_same_games(self):
        """THE WHOLE VALIDITY OF THE COMPARISON. A rung that quietly dropped the rows it
        could not settle would look better for being scored on an easier subset."""
        rows = [row(5, 4), row(5, 9), row(6, 6)]
        for r in ladder(rows):
            assert r["settled"] == 3

    def test_pending_rows_are_excluded_from_every_rung_not_just_one(self):
        rows = [row(5, 4), row(5, 9), row(5, None), row(5, None)]
        for r in ladder(rows):
            assert r["rows"] == 2
            assert r["settled"] == 2

    def test_gained_counts_the_extra_winners_against_the_recommended_line(self):
        # 4 and 4 miss 5+; both land at 4+. So one line lower gains exactly two.
        rows = [row(5, 4), row(5, 4), row(5, 9)]
        rungs = {r["offset"]: r for r in ladder(rows)}
        assert rungs[0]["won"] == 1
        assert rungs[-1]["won"] == 3
        assert rungs[-1]["gained"] == 2
        assert rungs[0]["gained"] == 0

    def test_one_line_higher_reports_what_was_left_behind(self):
        rows = [row(4, 9), row(4, 10), row(4, 4)]
        rungs = {r["offset"]: r for r in ladder(rows)}
        assert rungs[1]["won"] == 2          # the 9 and the 10 still clear 5+
        assert rungs[1]["gained"] == -1

    def test_unders_get_easier_in_the_other_direction(self):
        rows = [row(5, 5, "under"), row(5, 6, "under")]
        rungs = {r["offset"]: r for r in ladder(rows)}
        # at 6: a 5 wins, a 6 voids. So one win, no losses.
        assert rungs[-1]["won"] == 1 and rungs[-1]["lost"] == 0

    def test_an_empty_board_produces_rungs_with_no_rate_rather_than_zero(self):
        for r in ladder([]):
            assert r["settled"] == 0
            assert r["rate"] is None


class TestSplitByLine:
    def test_it_separates_a_board_that_is_timid_at_one_line_only(self):
        """Pooled, this board looks mildly timid. Split, 4+ is the whole of it."""
        rows = [row(4, 10), row(4, 11), row(4, 9), row(7, 7), row(7, 8)]
        out = {g["line"]: g for g in by_line(rows)}
        assert out[4]["margins"]["mean_cleared"] >= 6
        assert out[7]["margins"]["mean_cleared"] <= 1

    def test_each_group_reports_its_own_n(self):
        rows = [row(4, 5), row(4, 6), row(7, 8)]
        out = {g["line"]: g for g in by_line(rows)}
        assert out[4]["n"] == 2 and out[7]["n"] == 1

    def test_the_row_dumps_are_left_out_of_the_split(self):
        # by_line is for printing; carrying every settled row per rung per line would be
        # a payload nobody reads and a lot of it.
        for g in by_line([row(4, 5)]):
            assert all("rows_at" not in r for r in g["rungs"])


class TestFixtureTotals:
    def test_two_sides_of_one_game_make_a_total(self):
        rows = [row(5, 11, name="Barnsley", opponent="Cambridge", played_at="2026-10-18"),
                row(5, 11, name="Cambridge", opponent="Barnsley", played_at="2026-10-18")]
        out = fixture_totals(rows)
        assert len(out) == 1
        assert out[0]["total"] == 22
        assert out[0]["both_on_board"] is True

    def test_one_side_alone_has_no_total(self):
        """BOTH SIDES OR NOTHING. One count plus a guess at the other is not a match
        total, and a total line settled against half a game is wrong about half the
        time with nothing downstream able to tell."""
        out = fixture_totals([row(5, 11, name="Barnsley", opponent="Cambridge")])
        assert out[0]["total"] is None
        assert out[0]["both_sides_known"] is False
        assert out[0]["both_on_board"] is False

    def test_a_conceded_row_fills_the_opponents_slot_not_its_own(self):
        """`conceded` measures the OPPONENT's corners. Reading it as the subject team's
        count would invent a total out of one side counted twice."""
        rows = [row(5, 7, name="A", opponent="B", subject="team", played_at="2026-10-18"),
                row(5, 9, name="A", opponent="B", subject="conceded", played_at="2026-10-18")]
        out = fixture_totals(rows)
        assert out[0]["sides"] == {"A": 7, "B": 9}
        assert out[0]["total"] == 16

    def test_one_fixture_is_not_counted_twice_under_two_keys(self):
        rows = [row(5, 11, name="A", opponent="B", fixture_id="f1"),
                row(5, 9, name="B", opponent="A", fixture_id="f1")]
        assert len(fixture_totals(rows)) == 1

    def test_a_match_subject_row_is_not_mistaken_for_a_team_count(self):
        """A match-total row's `value` is already the whole game. Adding it to a team
        count would double one side."""
        rows = [row(18, 22, name="A", opponent="B", subject="match")]
        assert fixture_totals(rows) == []

    def test_totals_come_back_biggest_first(self):
        rows = [row(5, 4, name="A", opponent="B", played_at="2026-10-18"),
                row(5, 4, name="B", opponent="A", played_at="2026-10-18"),
                row(5, 11, name="C", opponent="D", played_at="2026-10-18"),
                row(5, 11, name="D", opponent="C", played_at="2026-10-18")]
        out = fixture_totals(rows)
        assert out[0]["total"] == 22 and out[-1]["total"] == 8


class TestTotalLadder:
    def test_it_reports_a_rate_per_total_line(self):
        totals = [{"total": t} for t in (22, 16, 8, 12)]
        out = {r["line"]: r for r in total_ladder(totals, lines=range(8, 13))}
        assert out[8]["won"] == 4 and out[8]["rate"] == 100.0
        assert out[12]["won"] == 3 and out[12]["rate"] == 75.0

    def test_fixtures_with_no_total_are_excluded(self):
        totals = [{"total": 22}, {"total": None}, {"total": 20}]
        out = total_ladder(totals, lines=range(10, 11))
        assert out[0]["n"] == 2

    def test_no_usable_fixture_returns_nothing_rather_than_a_table_of_zeroes(self):
        assert total_ladder([{"total": None}]) == []
        assert total_ladder([]) == []


class TestTheHelpers:
    def test_graded_keeps_only_rows_that_can_be_settled(self):
        rows = [row(5, 4), row(5, None), row(None, 4)]
        assert graded(rows) == [rows[0]]

    def test_tally_refuses_a_rate_without_a_denominator(self):
        assert tally([])["rate"] is None
        assert tally([{"result": VOID}])["rate"] is None

    def test_tally_keeps_voids_out_of_the_rate(self):
        t = tally([{"result": WIN}, {"result": VOID}, {"result": LOSS}])
        assert t["settled"] == 2 and t["rate"] == 50.0 and t["void"] == 1

    def test_the_rungs_are_ordered_hardest_first(self):
        # The table reads downwards from the line we did not take to the ones we did not
        # need, so +1 comes first and the recommended line sits inside it.
        assert RUNGS[0] == 1 and 0 in RUNGS and RUNGS[-1] == -2


class TestTheDuplicatedSettleRuleMatchesTheRealOne:
    """THE ONE PLACE THIS MODULE CAN GO SILENTLY WRONG.

    ladder.settle_at is a copy of server.settle_streak_leg, kept so this module needs no
    server import and its tests can run where importing server panics. A copy can drift,
    and a drifted settle rule produces a confident, wrong record rather than an error.

    line_ladder.py cross-checks the two over a grid on EVERY run and refuses to print
    anything if they disagree — see check_settle_rule. This test pins the table itself, so
    the rule is also described somewhere that does not need a database to read.
    """

    def test_the_over_table(self):
        # value, line -> expected. An over is won at the line or above, lost below.
        for line in range(0, 12):
            for value in range(0, 20):
                want = WIN if value >= line else LOSS
                assert settle_at(value, line, "over") == want, (value, line)

    def test_the_under_table_including_the_void(self):
        for line in range(0, 12):
            for value in range(0, 20):
                want = WIN if value < line else (VOID if value == line else LOSS)
                assert settle_at(value, line, "under") == want, (value, line)

    def test_an_unknown_direction_is_treated_as_an_over(self):
        """server.settle_streak_leg falls through to the over branch for anything that is
        not exactly "under", so this copy has to do the same or the two disagree on a row
        with a missing direction."""
        assert settle_at(5, 5, "") == WIN
        assert settle_at(4, 5, "sideways") == LOSS
