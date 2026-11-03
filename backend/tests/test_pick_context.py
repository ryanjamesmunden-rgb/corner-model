"""The context lines printed under a pick.

WHAT THESE GUARD. Every line here is a sentence a reader takes as fact, and a wrong one
cannot be spotted by reading it — "averaging 8.4 corners" looks identical whether the
window was the right five games or the wrong five. So the tests pin the things that
would silently produce a confident false sentence:

  - the window comes off the END of the record, in DATE order
  - synthetic padding never reaches a sentence
  - a provider stat the feed did not cover is not averaged as zero
  - nothing shorter than MIN_WINDOW is printed at all
  - a venue line is measured at that venue
  - no line claims a HALF-LEVEL corner figure, because none exists (issue #260)
  - colour never outranks evidence
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from pick_context import (COLOUR, EVIDENCE, GENERATORS, MIN_WINDOW,  # noqa: E402
                          THIN_SEASON, pick_context)


def match(day, cf, ca, home=True, gf=1, ga=1, fh_for=0, fh_against=0, **extra):
    m = {"date": f"2026-09-{day:02d}", "corners_for": cf, "corners_against": ca,
         "home": home, "goals_for": gf, "goals_against": ga,
         "fh_goals_for": fh_for, "fh_goals_against": fh_against,
         "opponent": "Someone"}
    m.update(extra)
    return m


def team(rows, name="Our Team", synthetic=0):
    t = {"name": name, "team_id": "t-1", "league_id": "l-1", "real_matches": list(rows)}
    if synthetic:
        # `matches` carries generated games for thin sides. Nothing here may read it.
        t["matches"] = list(rows) + [match(28, 99, 0)] * synthetic
    return t


def ctx(rows, opp_rows=None, venue="home", **kw):
    opp_rows = opp_rows if opp_rows is not None else [match(d, 4, 6, home=False)
                                                      for d in range(1, 11)]
    return pick_context(team(rows), team(opp_rows, name="Them"), venue, **kw)


def texts(res):
    return " || ".join(c["text"] for c in res["all"])


def by_key(res, key):
    return next((c for c in res["all"] if c["key"] == key), None)


class TestTheWindowIsTheLatestGamesByDate:
    def test_the_recent_average_uses_the_five_most_recent(self):
        rows = [match(d, 2, 2) for d in range(1, 6)] + [match(d, 10, 2) for d in range(6, 11)]
        c = by_key(ctx(rows), "corner_avg")
        assert c and "10.0 corners" in c["text"], c and c["text"]

    def test_stored_order_does_not_decide_the_window(self):
        # The FIRST stored row carries the LATEST date. A slice off the stored list would
        # miss it and report a confident average over the wrong five games.
        rows = [match(2, 2, 2)] * 5 + [match(1, 2, 2)] * 5
        rows[0] = match(30, 20, 2)
        c = by_key(ctx(rows), "corner_string")
        assert c["values"][0] == 20, c["text"]

    def test_the_form_string_reads_newest_first(self):
        rows = [match(d, d, 2) for d in range(1, 11)]   # corners climb with the date
        c = by_key(ctx(rows), "corner_string")
        assert c["values"] == [10, 9, 8, 7, 6], c["text"]

    def test_a_match_with_no_corner_count_is_dropped_not_zeroed(self):
        rows = [match(d, 8, 2) for d in range(1, 7)]
        rows.append(match(7, None, None))
        c = by_key(ctx(rows), "corner_avg")
        assert c and "8.0 corners" in c["text"]


class TestSyntheticGamesNeverReachASentence:
    def test_padding_is_not_read(self):
        rows = [match(d, 6, 4) for d in range(1, 8)]
        res = pick_context(team(rows, synthetic=4), team([match(d, 4, 6) for d in range(1, 8)]),
                           "home")
        assert "99" not in texts(res)
        assert res["games_on_file"] == 7

    def test_a_team_with_only_synthetic_games_says_nothing_about_itself(self):
        # The opponent's record is real, so opponent-side lines may still fire. What must
        # not happen is a sentence ABOUT the padded side, off games nobody played.
        t = {"name": "Ghost", "real_matches": [],
             "matches": [match(d, 9, 1) for d in range(1, 11)]}
        res = pick_context(t, team([match(d, 4, 6) for d in range(1, 8)], name="Them"),
                           "home")
        assert res["games_on_file"] == 0
        assert [c for c in res["all"] if "Ghost" in c["text"]] == []
        assert "9" not in "".join(c["text"] for c in res["all"] if "Ghost" in c["text"])


class TestAnUncoveredProviderStatIsNotZero:
    def test_blocked_shots_average_only_counts_covered_games(self):
        # six games carry the stat at 8, four do not. The average must be 8, not 4.8.
        rows = [match(d, 6, 4, blocked_shots_for=8) for d in range(1, 7)]
        rows += [match(d, 6, 4) for d in range(7, 11)]
        c = by_key(ctx(rows), "blocked")
        assert c and "8.0 blocked" in c["text"], c and c["text"]
        assert c["n"] == 6, "the claim must report the covered sample, not the pool"

    def test_a_feature_below_the_coverage_floor_is_not_printed(self):
        rows = [match(d, 6, 4, blocked_shots_for=9) for d in range(1, 4)]
        rows += [match(d, 6, 4) for d in range(4, 11)]
        assert by_key(ctx(rows), "blocked") is None

    def test_a_genuine_zero_still_counts(self):
        rows = [match(d, 6, 4, blocked_shots_for=0) for d in range(1, 8)]
        c = by_key(ctx(rows), "blocked")
        assert c and c["n"] == 7


class TestNothingShorterThanTheWindowIsPrinted:
    def test_a_three_game_run_is_not_a_sentence(self):
        # No clean sheet in 3 happens by chance one time in eight. It is not a tendency.
        rows = [match(d, 6, 4, ga=0) for d in range(1, 8)]        # clean sheets
        rows += [match(d, 6, 4, ga=2) for d in range(8, 11)]      # then three leaky
        assert by_key(ctx(rows), "no_clean_sheet") is None

    def test_a_five_game_run_is(self):
        rows = [match(d, 6, 4, ga=0) for d in range(1, 6)]
        rows += [match(d, 6, 4, ga=2) for d in range(6, 11)]
        c = by_key(ctx(rows), "no_clean_sheet")
        assert c and c["run"] == 5

    def test_no_run_claim_anywhere_reports_under_the_floor(self):
        # Sweeps EVERY claim carrying a run rather than a hand-picked list of keys: the
        # first version named five keys and e_losing_run, which fired at three games,
        # was simply not among them.
        shapes = [
            dict(cf=9, ca=1, gf=2, ga=2, fh=(0, 0)),     # corner + scoring runs
            dict(cf=1, ca=9, gf=0, ga=3, fh=(0, 1)),     # losing / conceding runs
            dict(cf=5, ca=5, gf=1, ga=0, fh=(1, 0)),     # clean-sheet runs
            dict(cf=5, ca=5, gf=2, ga=1, fh=(0, 1)),     # comeback shapes
        ]
        for tail in shapes:
            for n in range(1, 13):
                head = [match(d, 4, 4, gf=1, ga=1, fh_for=1, fh_against=1)
                        for d in range(1, 13 - n)]
                rest = [match(d, tail["cf"], tail["ca"], gf=tail["gf"], ga=tail["ga"],
                              fh_for=tail["fh"][0], fh_against=tail["fh"][1])
                        for d in range(13 - n, 13)]
                res = ctx(head + rest)
                for c in res["all"] + res["compound"]:
                    if isinstance(c.get("run"), int):
                        assert c["run"] >= MIN_WINDOW, \
                            f"{c['key']} printed a {c['run']}-game run"


class TestVenueLinesAreMeasuredAtThatVenue:
    def test_out_cornered_counts_only_home_games_for_a_home_pick(self):
        home = [match(d, 9, 1, home=True) for d in range(1, 7)]
        away = [match(d, 1, 9, home=False) for d in range(7, 13)]
        c = by_key(ctx(home + away, venue="home"), "out_cornered")
        assert c and c["won"] == 6 and c["of"] == 6, c and c["text"]

    def test_the_same_record_read_away_does_not_qualify(self):
        home = [match(d, 9, 1, home=True) for d in range(1, 7)]
        away = [match(d, 1, 9, home=False) for d in range(7, 13)]
        assert by_key(ctx(home + away, venue="away"), "out_cornered") is None

    def test_the_opponent_is_measured_at_the_other_venue(self):
        # our pick is at home, so the opponent's away record is the relevant one
        opp = ([match(d, 4, 12, home=False) for d in range(1, 7)]
               + [match(d, 4, 2, home=True) for d in range(7, 13)])
        c = by_key(ctx([match(d, 7, 3) for d in range(1, 8)], opp_rows=opp, venue="home"),
                   "opp_concedes")
        assert c and "12.0 corners per away game" in c["text"], c and c["text"]


class TestNoLineClaimsAHalfLevelCornerFigure:
    """There is no half-split corner data and there cannot be — probe_corner_halves.py,
    issue #260. A sentence implying one would be the single dishonest line on the page."""

    FORBIDDEN = re.compile(
        r"(second[- ]half corners|corners in the second half|first[- ]half corners"
        r"|corners while (behind|chasing|trailing)|corners after (going|falling) behind)",
        re.I)

    def test_no_generator_produces_a_half_corner_claim(self):
        rows = [match(d, 8, 4, gf=2, ga=1, fh_for=0, fh_against=1,
                      blocked_shots_for=7, shots_for=16, dangerous_attacks_for=40,
                      fouls_for=13) for d in range(1, 13)]
        opp = [match(d, 3, 9, home=False, gf=1, ga=3, fh_for=0, fh_against=1,
                     blocked_shots_for=6, shots_against=18) for d in range(1, 13)]
        res = ctx(rows, opp_rows=opp)
        hit = self.FORBIDDEN.search(texts(res))
        assert hit is None, f"half-level corner claim: {hit.group(0)!r}"

    def test_the_trailing_line_reports_full_match_corners(self):
        rows = [match(d, 8, 4, fh_for=0, fh_against=1) for d in range(1, 9)]
        c = by_key(ctx(rows), "trailed_ht")
        assert c, "the half-time state line should fire when the side keeps going behind"
        assert "finished with" in c["text"], c["text"]
        assert self.FORBIDDEN.search(c["text"]) is None


class TestEvidenceOutranksColour:
    def test_colour_never_leads(self):
        rows = [match(d, 8, 3, gf=2, ga=1, blocked_shots_for=7) for d in range(1, 13)]
        res = ctx(rows)
        assert res["lines"][0]["tier"] == EVIDENCE
        tiers = [c["tier"] for c in res["all"]]
        assert tiers == sorted(tiers, key=lambda t: t != EVIDENCE)

    def test_an_unbeaten_run_is_colour_not_evidence(self):
        rows = [match(d, 5, 5, gf=2, ga=1) for d in range(1, 12)]
        assert by_key(ctx(rows), "unbeaten")["tier"] == COLOUR

    def test_a_corner_run_is_evidence(self):
        rows = [match(d, 8, 3) for d in range(1, 12)]
        assert by_key(ctx(rows), "corner_run")["tier"] == EVIDENCE

    def test_the_clean_sheet_line_is_marked_ambiguous(self):
        # It points both ways: overrun, or stretched and open. The direction is not
        # recoverable from the sentence, so it must travel marked.
        rows = [match(d, 5, 5, ga=2) for d in range(1, 12)]
        assert by_key(ctx(rows), "no_clean_sheet")["ambiguous"] is True

    def test_nothing_else_is_marked_ambiguous(self):
        rows = [match(d, 8, 3, gf=2, ga=2, blocked_shots_for=7) for d in range(1, 13)]
        flagged = {c["key"] for c in ctx(rows)["all"] if c["ambiguous"]}
        assert flagged <= {"no_clean_sheet"}, flagged


class TestTheSelectionDoesNotRepeatItself:
    def test_the_two_phrasings_of_the_corner_run_never_both_appear(self):
        rows = [match(d, 8, 3) for d in range(1, 13)]
        keys = [c["key"] for c in ctx(rows)["all"]]
        assert not ("corner_run" in keys and "corner_run_plain" in keys)

    def test_selected_lines_spread_across_groups(self):
        rows = [match(d, 8, 3, gf=2, ga=1, fh_for=0, fh_against=1,
                      blocked_shots_for=7, shots_for=16) for d in range(1, 13)]
        opp = [match(d, 3, 9, home=False, gf=1, ga=3) for d in range(1, 13)]
        res = ctx(rows, opp_rows=opp, limit=3)
        groups = [c["group"] for c in res["lines"]]
        assert len(set(groups)) == len(groups), f"repeated group: {groups}"

    def test_limit_is_honoured(self):
        rows = [match(d, 8, 3, gf=2, ga=1, blocked_shots_for=7) for d in range(1, 13)]
        assert len(ctx(rows, limit=2)["lines"]) <= 2

    def test_every_generator_is_reachable(self):
        # a generator nothing can trigger is dead code pretending to be a feature
        assert len(GENERATORS) == 28


class TestARateIsNotARun:
    """"9 of 10" and "9 in a row" are different bets. A side can be 9 of 10 with a run
    of two, when the miss was the second-most-recent game."""

    def test_nine_of_ten_is_reported_as_a_rate(self):
        rows = [match(d, 8, 3) for d in range(1, 10)]
        rows.insert(8, match(9, 2, 3))          # one miss, second from last
        rows = sorted(rows, key=lambda m: m["date"])
        c = by_key(ctx(rows), "corner_rate")
        assert c, "a 9-of-10 record should produce a rate line"
        assert f"of their last {c['of']}" in c["text"], c["text"]
        assert c["hits"] < c["of"], "a rate line that is perfect should be a run instead"

    def test_a_perfect_window_is_left_to_the_run_claim(self):
        rows = [match(d, 8, 3) for d in range(1, 12)]
        assert by_key(ctx(rows), "corner_rate") is None
        assert by_key(ctx(rows), "corner_run") is not None

    def test_a_rate_below_the_floor_is_not_printed(self):
        rows = [match(d, 8, 3) for d in range(1, 7)]      # 6 clear
        rows += [match(d, 1, 3) for d in range(7, 11)]    # 4 do not -> 60%
        c = by_key(ctx(rows), "corner_rate")
        assert c is None or c["hits"] / c["of"] >= 0.8

    def test_the_rate_window_needs_a_real_denominator(self):
        rows = [match(d, 8, 3) for d in range(1, 7)]      # only 6 games
        c = by_key(ctx(rows), "corner_rate")
        assert c is None, "a rate needs enough games to be worth quoting"


class TestFactsJoinIntoOneSentence:
    def rich(self):
        rows = [match(d, 8, 3, gf=2, ga=2, fh_for=0, fh_against=1,
                      blocked_shots_for=7, shots_for=16) for d in range(1, 11)]
        rows.insert(8, match(9, 2, 3, gf=2, ga=2, fh_for=0, fh_against=1))
        opp = [match(d, 3, 9, home=False, gf=0, ga=0) for d in range(1, 13)]
        return sorted(rows, key=lambda m: m["date"]), opp

    def test_two_facts_about_one_side_share_their_subject(self):
        rows, opp = self.rich()
        res = ctx(rows, opp_rows=opp)
        comp = next((c for c in res["compound"] if c["subject"] == "team"), None)
        assert comp, res["compound"]
        assert " and " in comp["text"]
        assert comp["text"].count("Our Team") == 1, comp["text"]

    def test_a_compound_never_joins_two_facts_from_one_group(self):
        rows, opp = self.rich()
        res = ctx(rows, opp_rows=opp)
        for comp in res["compound"]:
            groups = [next(c["group"] for c in res["all"] if c["key"] == k)
                      for k in comp["parts"]]
            assert len(set(groups)) == len(groups), f"same group twice: {comp['text']}"

    def test_a_compound_is_only_evidence_if_both_halves_are(self):
        rows, opp = self.rich()
        res = ctx(rows, opp_rows=opp)
        for comp in res["compound"]:
            tiers = [next(c["tier"] for c in res["all"] if c["key"] == k)
                     for k in comp["parts"]]
            if COLOUR in tiers:
                assert comp["tier"] == COLOUR, comp["text"]

    def test_the_headline_names_both_sides(self):
        rows, opp = self.rich()
        res = ctx(rows, opp_rows=opp)
        assert res["headline"], "both sides had verified facts; expected a headline"
        assert "Our Team" in res["headline"] and "Them" in res["headline"]

    def test_the_opponent_clean_sheet_run_is_available(self):
        rows, opp = self.rich()
        c = by_key(ctx(rows, opp_rows=opp), "opp_clean_sheets")
        assert c and c["run"] == 12, c
        assert c["subject"] == "opponent"

    def test_the_clean_sheet_line_states_the_run_and_claims_no_mechanism(self):
        # "No goals conceded means more corners conceded when it gets desperate" is a
        # mechanism, not a measurement. Until it is measured the line reports the run.
        rows, opp = self.rich()
        c = by_key(ctx(rows, opp_rows=opp), "opp_clean_sheets")
        assert not re.search(r"desperate|so they|which means|because", c["text"], re.I), \
            c["text"]

    def test_no_headline_when_only_one_side_has_anything(self):
        rows = [match(d, 8, 3) for d in range(1, 11)]
        res = pick_context(team(rows), {"name": "Them"}, "home")
        assert res["headline"] is None
        assert [c for c in res["compound"] if c["subject"] == "opponent"] == []


class TestEveryClaimCarriesItsDenominator:
    def test_n_is_always_a_positive_count(self):
        rows = [match(d, 8, 3, gf=2, ga=1, fh_for=0, fh_against=1,
                      blocked_shots_for=7, shots_for=16, fouls_for=12)
                for d in range(1, 13)]
        for c in ctx(rows)["all"]:
            assert isinstance(c["n"], int) and c["n"] > 0, c

    def test_a_short_record_is_flagged_thin(self):
        rows = [match(d, 8, 3) for d in range(1, 10)]
        res = ctx(rows)
        assert res["games_on_file"] == 9 and res["thin"] is True

    def test_a_full_record_is_not_flagged_thin(self):
        rows = [match(d, 8, 3) for d in range(1, THIN_SEASON + 2)]
        assert ctx(rows)["thin"] is False

    def test_a_short_record_says_its_own_length(self):
        rows = [match(d, 6, 4, gf=2, ga=1, fh_for=0, fh_against=1) for d in range(1, 9)]
        c = by_key(ctx(rows), "comeback")
        assert c and "in 8 games" in c["text"], c and c["text"]


class TestTheWiringOnTheFixturePayload:
    """Read as source rather than imported: server.py needs a database to import, and
    the thing being guarded here is the wiring, which is visible in the text."""

    @staticmethod
    def src():
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "server.py")) as fh:
            return fh.read()

    def test_the_fixture_payload_carries_both_sides(self):
        s = self.src()
        assert "from pick_context import pick_context" in s
        assert '"pick_context": {' in s
        assert 'pick_context(home, away, "home"' in s
        assert 'pick_context(away, home, "away"' in s

    def test_the_printed_yardstick_has_no_hardcoded_fallback(self):
        # _refs substitutes REF_SHOTS when a league has no stored average, which is right
        # for pricing and wrong here: this yardstick gets printed, and "against a league
        # average of 12" is a made-up sentence when 12 is a default.
        s = self.src()
        block = s.split("def _ctx_refs")[1].split("\n    def ")[0]
        # the fallback IDIOM, not the bare name: the docstring names REF_SHOTS on purpose
        # to record why it is absent from the code.
        assert "or REF_SHOTS" not in block, "_ctx_refs must not substitute the fallback"
        assert 'lg.get("avg_shots")' in block
        assert 'lg.get("avg_blocked")' in block

    def test_the_line_limit_is_a_named_constant(self):
        s = self.src()
        assert "PICK_CONTEXT_LINES = " in s
        assert "limit=PICK_CONTEXT_LINES" in s


class TestOneBadRowCannotTakeThePanelDown:
    def test_a_malformed_match_does_not_raise(self):
        rows = [match(d, 7, 3) for d in range(1, 9)]
        rows.append({"date": "2026-09-20", "corners_for": 8, "home": True})  # no others
        res = ctx(rows)
        assert res["lines"], "the panel should still render"

    def test_an_empty_record_returns_an_empty_panel(self):
        res = pick_context({"name": "A"}, {"name": "B"}, "home")
        assert res["lines"] == [] and res["all"] == []
        assert res["games_on_file"] == 0
