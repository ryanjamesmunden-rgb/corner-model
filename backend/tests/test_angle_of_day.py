"""The angle of the day must be allowed to say there isn't one.

EVERY TEST HERE GUARDS THE SAME THING FROM A DIFFERENT SIDE: that the panel publishes what
the rule produced, and nothing else. The failure mode is not a crash. It is a page that
quietly always has five rows on it — because someone relaxed the bar on a quiet Tuesday,
or topped the list up from tomorrow, or let the results tab pick which kind of angle to
lead with. Each of those is one line of plausible code, none of them raises, and the result
is a site that recommends bets nobody would have made.

The other half is the record. A percentage off eight settled games reads as a track record
and is barely more than the gap between seven and eight, so the floor under it is pinned
here and cross-checked against the frontend's copy.
"""
import os
import re
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angle_of_day as aod  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def row(name="Boro", kickoff="2026-09-15T18:45:00Z", prob=70.0, weak=True, run=6, **kw):
    """A board row that clears every bar unless a test says otherwise."""
    return {"name": name, "league_id": "eng-ch",
            "next_fixture": {"date": kickoff, "opponent": "Stoke"},
            "support": {"run": run, "prob": prob, "weak_opponent": weak,
                        "opp_conceded": 7.1, "league_avg": 5.4, "opp_bar": 5.94,
                        "opp_fh_rate": 62},
            **kw}


def entry(name="Boro", kickoff="2026-09-15T18:45:00Z", **kw):
    """A frozen snapshot entry — kick-off flat, not nested. Both shapes must work."""
    return {"name": name, "kickoff": kickoff, **kw}


class TestTheDayIsALondonDay:
    def test_a_utc_evening_game_is_today(self):
        assert aod.london_day("2026-09-15T18:45:00Z") == "2026-09-15"

    def test_a_late_kickoff_past_midnight_utc_is_still_the_same_london_day(self):
        # 23:30 UTC in September is 00:30 the next morning in London — which is TOMORROW
        # to a reader. Getting this backwards puts a game on the wrong day's panel.
        assert aod.london_day("2026-09-15T23:30:00Z") == "2026-09-16"

    def test_a_winter_kickoff_uses_gmt_not_bst(self):
        # No offset in January, so UTC and London agree. The zone is applied, not assumed.
        assert aod.london_day("2026-01-15T23:30:00Z") == "2026-01-15"

    def test_an_unreadable_date_is_not_guessed_at(self):
        assert aod.london_day("not a date") is None
        assert aod.london_day(None) is None

    def test_both_row_shapes_carry_a_kickoff(self):
        assert aod.kickoff_of(row()) == "2026-09-15T18:45:00Z"
        assert aod.kickoff_of(entry()) == "2026-09-15T18:45:00Z"
        assert aod.kickoff_of({}) is None


class TestAThinDayStaysThin:
    def test_fewer_qualifiers_than_the_cap_yields_fewer(self):
        two = [row("A"), row("B")]
        assert len(aod.shortlist(two, "2026-09-15", count=5)) == 2

    def test_nothing_qualifying_yields_nothing(self):
        assert aod.shortlist([], "2026-09-15") == []

    def test_tomorrows_games_do_not_top_up_today(self):
        # The single most tempting line of code in this feature: the page looks bare, so
        # reach into tomorrow. That publishes an angle on a game whose price and team news
        # are both a day from settling, under a heading that says "today".
        today = [row("A")]
        tomorrow = [row("B", kickoff="2026-09-16T18:45:00Z")]
        out = aod.shortlist(today + tomorrow, "2026-09-15", count=5)
        assert [r["name"] for r in out] == ["A"]

    def test_the_cap_is_a_ceiling(self):
        many = [row(str(i)) for i in range(20)]
        assert len(aod.shortlist(many, "2026-09-15", count=5)) == 5

    def test_the_most_likely_to_land_leads(self):
        # The stated order, and the direct answer to "pick the ones more likely to land".
        rows = [row("middling", prob=66.0), row("best", prob=78.0), row("thin", prob=61.0)]
        assert [r["name"] for r in aod.shortlist(rows, "2026-09-15", count=3)] == \
            ["best", "middling", "thin"]


class TestTheRunHasToBeARun:
    """The bar that was missing entirely.

    The fixture bars ask whether the opponent is leaky and whether the model rates it.
    Neither asks the first question anyone would: how long has this actually been going? So
    a team two games into a run could clear both and be published as a streak.
    """

    def test_a_two_game_run_is_not_a_streak_however_good_the_fixture(self):
        assert aod.qualifies(row(run=2, weak=True, prob=85.0)) is False

    def test_the_floor_is_five(self):
        assert aod.MIN_RUN == 5
        assert aod.qualifies(row(run=4)) is False
        assert aod.qualifies(row(run=5)) is True

    def test_a_long_enough_run_qualifies_on_its_own(self):
        # At STRONG_RUN the run IS the evidence. The fixture bars need an opponent with
        # enough history to have an average; where there is none they cannot certify
        # anything, and requiring them would throw away the strongest streaks on the board
        # exactly when there is nothing else to judge by.
        assert aod.qualifies(row(run=aod.STRONG_RUN, weak=False, prob=None)) is True
        assert aod.qualifies(row(run=12, weak=False, prob=30.0)) is True

    def test_just_short_of_the_long_route_still_needs_the_fixture(self):
        assert aod.qualifies(row(run=aod.STRONG_RUN - 1, weak=False)) is False
        assert aod.qualifies(row(run=aod.STRONG_RUN - 1, prob=40.0)) is False
        assert aod.qualifies(row(run=aod.STRONG_RUN - 1, weak=True, prob=70.0)) is True

    def test_a_row_with_no_run_recorded_does_not_pass(self):
        assert aod.qualifies({"support": {"weak_opponent": True, "prob": 90.0}}) is False

    def test_each_route_names_itself(self):
        # So a frozen row records WHICH argument let it through. "10 in a row" and "6 in a
        # row against a defence conceding 7.1" are different claims, and a record that
        # cannot tell them apart cannot say which kind of pick has been working.
        assert aod.qualifying_route(row(run=12, weak=False)) == aod.ROUTE_LONG_RUN
        assert aod.qualifying_route(row(run=6, weak=True, prob=70.0)) == aod.ROUTE_CORROBORATED
        assert aod.qualifying_route(row(run=3)) is None

    def test_the_long_route_is_tested_first(self):
        """A twelve-game streak must never be failed for want of an opponent average —
        which is the whole reason the route exists."""
        no_fixture_data = {"support": {"run": 12}}
        assert aod.qualifying_route(no_fixture_data) == aod.ROUTE_LONG_RUN

    def test_a_row_the_model_cannot_price_sorts_last_rather_than_first(self):
        # The order is the model's confidence, and a fixture it cannot assess has none to
        # offer. The run breaks the tie beneath, so those rows are at least ordered sanely
        # among themselves.
        priced = row("priced", run=11, prob=64.0)
        unpriced_long = row("unpriced-long", run=14, prob=None, weak=False)
        unpriced_short = row("unpriced-short", run=10, prob=None, weak=False)
        out = aod.shortlist([unpriced_short, unpriced_long, priced], "2026-09-15", count=3)
        assert [r["name"] for r in out] == ["priced", "unpriced-long", "unpriced-short"]

    def test_the_top_of_the_useful_range_is_stated(self):
        """So nobody reads MIN_RUN as a target to tune. A side that has cleared its line ten
        straight is telling you what it is; the eleventh does not change the call."""
        assert aod.STRONG_RUN == 10
        assert aod.STRONG_RUN > aod.MIN_RUN

    def test_the_run_is_the_live_one_not_the_windows_hit_count(self):
        # A 4-of-5 whose most recent game was the miss is a broken streak wearing a good
        # record, and the hit count cannot tell the two apart.
        s = aod.support_for({"streak": {"length": 7},
                             "projection": {"opp_conceded": 7.0, "prob": 70.0}}, 5.0)
        assert s["run"] == 7

    def test_a_row_with_no_streak_block_reports_zero_rather_than_raising(self):
        s = aod.support_for({"projection": {"opp_conceded": 7.0, "prob": 70.0}}, 5.0)
        assert s["run"] == 0


class TestTheFixtureHasToBackTheStreakUp:
    """The change that stops eight rows appearing on a Tuesday.

    A streak says a team keeps clearing a line. It says nothing about who they play next,
    which is the half that decides whether the run continues — so on a quiet midweek the
    board was simply serving whatever was left, and eight rows read as eight things worth
    backing when it was eight rows.
    """

    def test_a_streak_against_a_mean_defence_does_not_qualify(self):
        assert aod.qualifies(row(weak=False)) is False

    def test_a_streak_the_model_rates_below_the_floor_does_not(self):
        assert aod.qualifies(row(prob=aod.MIN_PROB - 0.1)) is False

    def test_the_floor_is_a_boundary(self):
        assert aod.qualifies(row(prob=aod.MIN_PROB)) is True

    def test_both_bars_are_required_not_either(self):
        # Either-or would let a leaky-opponent fixture through on a coin-flip probability,
        # which is most of what the panel is meant to stop publishing.
        assert aod.qualifies(row(prob=80.0, weak=False)) is False
        assert aod.qualifies(row(prob=40.0, weak=True)) is False

    def test_a_row_the_model_could_not_price_fails_rather_than_passing(self):
        # No opponent history, no projection. Passing on the strength of the streak alone
        # is exactly the old behaviour, and the streak was never the part in doubt.
        assert aod.qualifies({"support": {"weak_opponent": True, "prob": None}}) is False
        assert aod.qualifies({}) is False

    def test_a_weak_opponent_is_measured_against_that_leagues_own_average(self):
        # 6.0 conceded is leaky in a 5.0 league and ordinary in a 6.5 one. A flat threshold
        # would quietly publish every fixture in the high-corner leagues and none anywhere else.
        proj = {"projection": {"opp_conceded": 6.0, "prob": 70.0}}
        assert aod.support_for(proj, league_avg=5.0)["weak_opponent"] is True
        assert aod.support_for(proj, league_avg=6.5)["weak_opponent"] is False

    def test_the_margin_is_the_mismatch_boards_own(self):
        # One definition of "weak", shared, so the two boards cannot drift into separate
        # opinions about the same fixture.
        assert aod.MISMATCH_EDGE == 1.1
        s = aod.support_for({"projection": {"opp_conceded": 5.5, "prob": 70.0}}, 5.0)
        assert s["opp_bar"] == 5.5 and s["weak_opponent"] is True

    def test_a_league_with_no_average_cannot_certify_a_weak_opponent(self):
        s = aod.support_for({"projection": {"opp_conceded": 9.0, "prob": 90.0}}, None)
        assert s["weak_opponent"] is False

    def test_the_first_half_rate_is_carried_but_gates_nothing(self):
        """The half of the request that the repo's own measurements refuse.

        Five tests have failed to find an effect from the opponent's first-half scoring —
        `no_opp_fh` scored +0.03 against a RANDOM control that came out flat. It rides on
        the row so a reader can see it; it must never decide anything.
        """
        assert aod.qualifies(row(**{"opp_fh_rate": 10})) is True
        assert aod.qualifies(row(**{"opp_fh_rate": 90})) is True
        s = aod.support_for({"projection": {"opp_conceded": 7.0, "prob": 70.0},
                             "opp_fh_rate": 62}, 5.0)
        assert s["opp_fh_rate"] == 62

    def test_ordering_ignores_the_first_half_rate(self):
        low = row("low-fh", prob=75.0, **{"opp_fh_rate": 5})
        high = row("high-fh", prob=70.0, **{"opp_fh_rate": 95})
        assert [r["name"] for r in aod.shortlist([high, low], "2026-09-15", count=2)] == \
            ["low-fh", "high-fh"]


class TestAGameThatHasStartedIsNotAnAngle:
    NOW = "2026-09-15T15:00:00Z"

    def test_a_finished_lunchtime_game_is_dropped(self):
        # The board is cached and the day is not. At 20:00 the morning's scan still lists
        # the 12:30 kick-off, and offering it is offering a bet that cannot be placed on a
        # result the reader may already know.
        started = [row("A", kickoff="2026-09-15T12:30:00Z")]
        assert aod.upcoming(started, self.NOW) == []

    def test_a_later_game_survives(self):
        later = [row("A", kickoff="2026-09-15T18:45:00Z")]
        assert len(aod.upcoming(later, self.NOW)) == 1

    def test_a_row_with_no_kickoff_is_dropped_rather_than_kept(self):
        assert aod.upcoming([{"name": "A"}], self.NOW) == []

    def test_kick_off_exactly_now_still_counts(self):
        assert len(aod.upcoming([row("A", kickoff=self.NOW)], self.NOW)) == 1


class TestTheRecordGradesWhatWasPublished:
    def test_the_slice_matches_what_the_panel_shows(self):
        # A snapshot holds 25; the panel shows 5. Grading all 25 and printing it beside a
        # list of 5 quotes one thing's record next to another thing.
        entries = [entry(str(i)) for i in range(25)]
        assert [e["name"] for e in aod.published(entries, 5)] == ["0", "1", "2", "3", "4"]

    def test_rank_one_is_its_own_claim(self):
        entries = [entry("top"), entry("second")]
        assert [e["name"] for e in aod.published(entries, 1)] == ["top"]

    def test_stored_order_is_the_order_and_no_result_is_consulted(self):
        # Reordering here — by anything, including how the row turned out — would be
        # choosing the record after the fact, which is the one thing snapshots exist to
        # prevent.
        entries = [entry("a", result="loss"), entry("b", result="win")]
        assert [e["name"] for e in aod.published(entries, 1)] == ["a"]

    def test_a_short_snapshot_is_not_padded(self):
        assert len(aod.published([entry("a")], 5)) == 1

    def test_no_entries_is_not_an_error(self):
        assert aod.published(None, 5) == []


class TestWhatTheRecordMayBeStatedAs:
    def test_a_small_sample_may_not_show_a_percentage(self):
        # Seven of eight is 87.5%, which reads as a track record and is one game from 75%.
        g = aod.gate({"landed": 7, "missed": 1, "settled": 8, "hit_rate": 87.5})
        assert g["show_rate"] is False
        assert g["landed"] == 7 and g["settled"] == 8

    def test_a_sample_at_the_floor_may(self):
        g = aod.gate({"landed": 15, "missed": 5, "settled": 20, "hit_rate": 75.0})
        assert g["show_rate"] is True

    def test_nothing_settled_is_not_zero_percent(self):
        # "Nothing has settled" and "everything missed" are different facts and a panel
        # that prints 0% for the first is lying about the second.
        g = aod.gate({"landed": 0, "missed": 0, "settled": 0, "hit_rate": None})
        assert g["hit_rate"] is None
        assert g["show_rate"] is False

    def test_an_absent_tally_does_not_raise(self):
        assert aod.gate(None)["settled"] == 0

    def test_either_spelling_of_the_void_count_is_read(self):
        # _tally says "voided"; other call sites have said "void". Reading only one would
        # silently drop pushes from the panel.
        assert aod.gate({"voided": 2})["voided"] == 2
        assert aod.gate({"void": 3})["voided"] == 3

    def test_the_floor_agrees_with_the_frontend(self):
        """Two places decide whether a rate may be shown. They must not disagree.

        A disagreement here is not a style problem: it is the site showing a percentage in
        one panel and withholding it in another off the same record, which reads as one of
        them being broken.
        """
        js = open(os.path.join(REPO, "frontend/src/lib/record.js")).read()
        m = re.search(r"MIN_SAMPLE\s*=\s*(\d+)", js)
        assert m, "record.js no longer declares MIN_SAMPLE"
        assert int(m.group(1)) == aod.MIN_SAMPLE, (
            f"record.js says {m.group(1)}, angle_of_day says {aod.MIN_SAMPLE} — the site "
            "would show a rate in one panel and withhold it in another")


class TestADeadDaySaysWhy:
    def test_a_quiet_calendar_and_a_strict_bar_are_different_facts(self):
        assert aod.state([], fixtures_today=0)["reason"] == aod.DEAD_NO_FIXTURES
        assert aod.state([], fixtures_today=40)["reason"] == aod.DEAD_NO_QUALIFIER

    def test_stale_data_beats_both(self):
        # Publishing off old form is worse than publishing nothing, and it is worse in a
        # way the reader cannot see — so it is reported ahead of everything else.
        s = aod.state([], fixtures_today=0, stale=True)
        assert s["reason"] == aod.DEAD_STALE

    def test_stale_data_suppresses_a_day_that_would_otherwise_have_angles(self):
        s = aod.state([row("A")], fixtures_today=40, stale=True)
        assert s["dead"] is True

    def test_a_live_day_is_not_dead(self):
        s = aod.state([row("A")], fixtures_today=40)
        assert s["dead"] is False and s["reason"] is None

    def test_every_reason_carries_words_a_reader_can_read(self):
        for reason in (aod.DEAD_STALE, aod.DEAD_NO_FIXTURES, aod.DEAD_NO_QUALIFIER):
            assert len(aod.DEAD_REASONS[reason]) > 40


class TestTheRuleIsStatedNotDiscovered:
    def test_the_rule_is_named_for_what_it_does(self):
        assert aod.RULE == "long_runs_or_corroborated_streaks"

    def test_the_module_records_why_the_record_is_not_the_selector(self):
        """So nobody re-introduces "lead with whatever has been landing" without seeing
        that it was considered and rejected, and why."""
        src = open(aod.__file__).read()
        assert "EVIDENCE, NEVER THE SELECTOR" in src
        assert "+7.9" in src and "+7.5" in src, \
            "the falsified-ranking result is the argument — it has to stay next to the rule"

    def test_the_streak_bar_still_belongs_to_the_board(self):
        src = open(aod.__file__).read()
        assert "min_hits" not in src.replace("`min_hits`", ""), \
            "the streak bar belongs to the board's own call, not to the panel — a " \
            "min_hits here would be the panel lowering it to fill itself"

    def test_the_falsified_opponent_term_is_recorded_as_not_a_gate(self):
        """Five measurements found no effect. It is carried as context and gates nothing —
        and the reason has to stay next to the rule, or it comes back."""
        src = open(aod.__file__).read()
        assert "CONTEXT, NEVER A GATE" in src
        assert "measured five times" in src

    def test_the_endpoint_does_not_order_angles_by_the_record(self):
        import inspect

        import server
        src = inspect.getsource(server.angles_today)
        body = src[src.index('"""', src.index('"""') + 3):]
        assert "_angle_record" in body, "the record is still shown"
        # It appears once, in the returned payload — never before `angles` is built.
        assert body.index("angles = ") < body.index("_angle_record"), \
            "the angles are being built after the record is read, which is how the record " \
            "starts choosing them"
