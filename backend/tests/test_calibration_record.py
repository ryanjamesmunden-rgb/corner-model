"""The calibration record, tested on the parts that decide what a reader concludes.

WHY THESE AND NOT OTHERS. A table like this does not crash when it is wrong — it prints a
confident, plausible, flattering number, and somebody trusts the model on it. The failures
worth pinning are the ones that produce exactly that:

  - An ungraded fixture scored as a miss. That drags the actual rate down and manufactures
    the overconfidence the table exists to detect.
  - A claim with no probability given a default band. There is no honest default; the
    whole subject is the number that was printed before kick-off.
  - A thin band quietly dropped. Then the table is a selection of the bands that filled
    up, which is the same fault as a record that hides its losing months.
  - One denominator instead of two. Claims inside a fixture are correlated, so a table
    reporting only `claims` overstates its own sample by about an order of magnitude.
  - Home and away pooled under one line. They are different bets on the same game.
  - A verdict that reads a residual off a sample too small to carry one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calibration import (  # noqa: E402
    BAND_EDGES, MIN_BAND, TEAM_LINES, MATCH_LINES,
    band_of, band_keys, wilson, claims_for, grade_claim, by_band, by_line,
    by_band_and_line, summarise,
)


# A deterministic stand-in for nb_ge / poisson_ge: probability falls as the line rises.
def fake_team_prob(line, lam):
    return max(0.0, min(1.0, 1.0 - (line - 1) / (2 * lam)))


def fake_match_prob(line, lam):
    return max(0.0, min(1.0, 1.0 - (line - 1) / (2 * lam)))


def entry(fixture="fx1", home=6.0, away=5.0, total=11.0, **kw):
    return {"fixture_id": fixture, "kickoff": "2026-10-01T15:00:00+00:00",
            "league_id": "eng-ch", "lambda_home": home, "lambda_away": away,
            "lambda_total": total, **kw}


def claim(prob, hit, line=5, side="home", market="team", fixture="fx1", source="stored"):
    return {"prob": prob, "hit": hit, "line": line, "side": side, "market": market,
            "fixture_id": fixture, "source": source}


class TestBands:
    def test_the_edges_asked_for_are_edges(self):
        # 60, 65 and 70 are the bands the record was asked to keep.
        for edge in (60.0, 65.0, 70.0):
            assert edge in BAND_EDGES

    def test_a_probability_lands_in_exactly_one_band(self):
        seen = {}
        for p in range(0, 101):
            b = band_of(float(p))
            assert b is not None
            seen.setdefault(b, []).append(p)
        assert set(seen) == set(band_keys())

    def test_the_boundary_belongs_to_the_band_above(self):
        # 65.0 is the start of "65-70%", not the end of "60-65%". Either rule works; an
        # UNSTATED one means two tables built a month apart disagree about one row.
        assert band_of(64.9) == "60-65%"
        assert band_of(65.0) == "65-70%"
        assert band_of(69.9) == "65-70%"
        assert band_of(70.0) == "70-75%"

    def test_no_probability_is_no_band_rather_than_a_default(self):
        assert band_of(None) is None
        assert band_of("") is None
        assert band_of("nonsense") is None

    def test_an_impossible_probability_is_refused(self):
        # A percentage over 100 is a unit bug upstream, and bucketing it would hide it.
        assert band_of(140.0) is None
        assert band_of(-3.0) is None

    def test_the_whole_range_is_covered_low_and_high(self):
        assert band_of(2.0) == "under 25%"
        assert band_of(99.0) == "80%+"


class TestWilson:
    def test_the_interval_can_actually_be_exceeded(self):
        # The textbook interval runs past 100% at these rates, and an interval that
        # cannot be exceeded can never say the promise sits outside it.
        lo, hi = wilson(43, 44)
        assert hi <= 100.0
        assert lo > 0.0

    def test_no_sample_is_the_whole_range(self):
        assert wilson(0, 0) == (0.0, 100.0)


class TestWhatAFixtureClaims:
    def test_every_line_on_both_sides_plus_the_totals(self):
        cs = claims_for(entry(), fake_team_prob, fake_match_prob)
        assert len(cs) == len(TEAM_LINES) * 2 + len(MATCH_LINES)

    def test_home_and_away_stay_apart(self):
        # Different bets on the same game. Pooled, the table averages two claims it can
        # no longer separate.
        cs = claims_for(entry(home=7.0, away=4.0), fake_team_prob, fake_match_prob)
        h = next(c for c in cs if c["side"] == "home" and c["line"] == 5)
        a = next(c for c in cs if c["side"] == "away" and c["line"] == 5)
        assert h["prob"] != a["prob"]

    def test_a_stored_probability_is_used_and_marked_stored(self):
        # The number the site actually published that night IS the record.
        e = entry(probs={"home_5": 71.5})
        c = next(c for c in claims_for(e, fake_team_prob, fake_match_prob)
                 if c["side"] == "home" and c["line"] == 5)
        assert c["prob"] == 71.5
        assert c["source"] == "stored"

    def test_a_missing_one_is_derived_and_marked_derived(self):
        c = next(c for c in claims_for(entry(), fake_team_prob, fake_match_prob)
                 if c["side"] == "home" and c["line"] == 5)
        assert c["source"] == "derived"
        assert c["prob"] == round(fake_team_prob(5, 6.0) * 100, 2)

    def test_stored_and_derived_can_coexist_on_one_fixture(self):
        # A snapshot written as the stored probabilities were being rolled out carries
        # some and not others, and the row has to say which is which per line.
        e = entry(probs={"home_5": 71.5})
        cs = claims_for(e, fake_team_prob, fake_match_prob)
        assert {c["source"] for c in cs} == {"stored", "derived"}

    def test_a_fixture_with_no_lambda_claims_nothing_rather_than_zero(self):
        e = {"fixture_id": "fx9"}
        assert claims_for(e, fake_team_prob, fake_match_prob) == []

    def test_a_side_with_no_lambda_drops_only_that_side(self):
        e = entry()
        e.pop("lambda_away")
        cs = claims_for(e, fake_team_prob, fake_match_prob)
        assert {c["side"] for c in cs} == {"home", "total"}


class TestGrading:
    def test_the_line_is_inclusive_because_that_is_how_it_is_sold(self):
        # "5+ corners" is Over 4.5. Exactly five wins; there is no push.
        c = {"side": "home", "line": 5}
        assert grade_claim(c, {"home_corners": 5}) == 1
        assert grade_claim(c, {"home_corners": 4}) == 0

    def test_each_side_is_graded_against_its_own_corners(self):
        actual = {"home_corners": 8, "away_corners": 2, "total_corners": 10}
        assert grade_claim({"side": "home", "line": 6}, actual) == 1
        assert grade_claim({"side": "away", "line": 6}, actual) == 0
        assert grade_claim({"side": "total", "line": 10}, actual) == 1

    def test_an_ungraded_fixture_is_none_and_never_zero(self):
        # THE ONE THAT MANUFACTURES OVERCONFIDENCE. A result that never synced scored as
        # a miss drags every actual rate below its promise.
        assert grade_claim({"side": "home", "line": 5}, None) is None
        assert grade_claim({"side": "home", "line": 5}, {}) is None
        assert grade_claim({"side": "home", "line": 5}, {"home_corners": None}) is None

    def test_a_boolean_is_not_a_corner_count(self):
        assert grade_claim({"side": "home", "line": 1}, {"home_corners": True}) is None

    def test_zero_corners_is_a_real_result(self):
        # Distinct from missing, and the one a loose truthiness check gets wrong.
        assert grade_claim({"side": "home", "line": 1}, {"home_corners": 0}) == 0


class TestTheTable:
    def test_both_denominators_are_reported(self):
        # Claims inside a fixture are correlated; reporting only `claims` overstates the
        # sample by about an order of magnitude.
        rows = [claim(62.0, 1, line=3, fixture="a"), claim(62.0, 1, line=4, fixture="a"),
                claim(62.0, 0, line=5, fixture="b")]
        band = next(b for b in by_band(rows) if b["band"] == "60-65%")
        assert band["claims"] == 3
        assert band["fixtures"] == 2

    def test_the_promise_is_the_mean_stated_probability_not_the_midpoint(self):
        # The band midpoint is a different and wrong number: a band holding only 60.1%
        # claims promised 60.1, not 62.5.
        rows = [claim(60.1, 1), claim(60.1, 0)]
        band = next(b for b in by_band(rows) if b["band"] == "60-65%")
        assert band["promised"] == 60.1

    def test_the_residual_is_actual_minus_promised(self):
        rows = [claim(70.0, 1) for _ in range(7)] + [claim(70.0, 0) for _ in range(3)]
        band = next(b for b in by_band(rows) if b["band"] == "70-75%")
        assert band["actual"] == 70.0
        assert band["residual"] == 0.0

    def test_an_overconfident_band_shows_a_negative_residual(self):
        rows = [claim(70.0, 1) for _ in range(5)] + [claim(70.0, 0) for _ in range(5)]
        band = next(b for b in by_band(rows) if b["band"] == "70-75%")
        assert band["residual"] == -20.0

    def test_a_thin_band_is_printed_and_marked_not_dropped(self):
        # Dropping it makes the table a selection of the bands that filled up.
        rows = [claim(62.0, 1)]
        bands = by_band(rows)
        assert [b["band"] for b in bands] == band_keys()
        assert next(b for b in bands if b["band"] == "60-65%")["thin"] is True

    def test_an_empty_band_still_has_a_row(self):
        bands = by_band([claim(62.0, 1)])
        empty = next(b for b in bands if b["band"] == "80%+")
        assert empty["claims"] == 0
        assert empty["actual"] is None

    def test_calibrated_means_the_promise_sits_inside_the_interval(self):
        on = [claim(70.0, 1) for _ in range(70)] + [claim(70.0, 0) for _ in range(30)]
        assert next(b for b in by_band(on) if b["band"] == "70-75%")["calibrated"] is True
        off = [claim(70.0, 1) for _ in range(30)] + [claim(70.0, 0) for _ in range(70)]
        assert next(b for b in by_band(off) if b["band"] == "70-75%")["calibrated"] is False

    def test_how_many_rows_were_derived_rides_along(self):
        rows = [claim(62.0, 1, source="derived"), claim(62.0, 1, source="stored")]
        assert next(b for b in by_band(rows) if b["band"] == "60-65%")["derived"] == 1


class TestPerLine:
    def test_team_and_match_lines_are_not_added_together(self):
        # A match total of 8+ is roughly twice a team's 8+. Keyed on the bare line they
        # would merge into one meaningless row.
        rows = [claim(62.0, 1, line=8, market="team"),
                claim(62.0, 0, line=8, market="match", side="total")]
        team = by_line(rows, "team")
        assert len(team) == 1 and team[0]["claims"] == 1
        match = by_line(rows, "match")
        assert len(match) == 1 and match[0]["claims"] == 1

    def test_the_grid_separates_a_level_error_from_a_tail_error(self):
        # Honest at 4+, overconfident at 7+ — the pooled table shows neither, and the two
        # call for different fixes.
        rows = ([claim(70.0, 1, line=4) for _ in range(7)]
                + [claim(70.0, 0, line=4) for _ in range(3)]
                + [claim(70.0, 1, line=7) for _ in range(3)]
                + [claim(70.0, 0, line=7) for _ in range(7)])
        grid = by_band_and_line(rows, "team")
        cells = {c["line"]: c for c in
                 next(g for g in grid if g["band"] == "70-75%")["lines"]}
        assert cells[4]["residual"] == 0.0
        assert cells[7]["residual"] == -40.0


class TestTheVerdict:
    def test_it_refuses_to_conclude_on_a_sample_that_cannot_carry_one(self):
        out = summarise([claim(70.0, 1) for _ in range(3)])
        assert "not enough" in out["verdict"].lower()

    def test_it_says_so_when_the_percentages_run_high(self):
        rows = ([claim(70.0, 1) for _ in range(30)]
                + [claim(70.0, 0) for _ in range(70)])
        out = summarise(rows)
        assert "running high" in out["verdict"].lower()

    def test_it_says_so_when_they_hold_up(self):
        rows = ([claim(70.0, 1) for _ in range(70)]
                + [claim(70.0, 0) for _ in range(30)])
        out = summarise(rows)
        assert "holding up" in out["verdict"].lower()

    def test_ungraded_fixtures_are_counted_and_reported_not_scored(self):
        rows = [claim(70.0, 1) for _ in range(30)] + [claim(70.0, None)]
        out = summarise(rows, ungraded=12)
        assert out["ungraded"] == 12
        assert out["overall"]["claims"] == 30     # the None is not in the denominator

    def test_an_empty_record_does_not_explode(self):
        out = summarise([])
        assert out["overall"]["claims"] == 0
        assert out["overall"]["actual"] is None
        assert "not enough" in out["verdict"].lower()


class TestAgainstASimulatedSeason:
    """End to end on generated matches, which is the only way to check the SIGN.

    A unit test on hand-made claims cannot catch a model whose probabilities are right and
    whose grading is inverted, or bands assigned off by one: both produce a full, orderly,
    plausible table. Here the truth is known by construction, so a calibrated generator
    must come out near zero and a deliberately overconfident one must come out negative.
    """

    @staticmethod
    def _season(rng, dispersion, n=400):
        """Fixtures whose actual corners come from a negative binomial around the lambda.

        `dispersion` is the generator's r. The MODEL always prices with r = 11, so
        lowering the generator's r makes real corners streakier than the model believes —
        which is exactly the overdispersion the comment this was built from warned about,
        and the table has to be able to see it.
        """
        import math as _m
        entries, actuals = [], {}

        def nb_draw(lam, r):
            # Gamma-Poisson mixture: the standard way to draw a negative binomial.
            shape, scale = r, lam / r
            return int(rng.poisson(rng.gamma(shape, scale)))

        for i in range(n):
            lam_h = rng.uniform(3.5, 7.5)
            lam_a = rng.uniform(3.5, 7.5)
            e = {"fixture_id": f"f{i}", "kickoff": "2026-10-01T15:00:00+00:00",
                 "lambda_home": lam_h, "lambda_away": lam_a,
                 "lambda_total": lam_h + lam_a}
            entries.append(e)
            h = nb_draw(lam_h, dispersion)
            a = nb_draw(lam_a, dispersion)
            actuals[e["fixture_id"]] = {"home_corners": h, "away_corners": a,
                                        "total_corners": h + a}
        return entries, actuals

    @staticmethod
    def _run(entries, actuals, model_r=11.0):
        import math as _m

        def nb_pmf(k, lam, r):
            p = r / (r + lam)
            return (_m.exp(_m.lgamma(k + r) - _m.lgamma(r) - _m.lgamma(k + 1))
                    * (p ** r) * ((1 - p) ** k))

        def nb_ge(k, lam, r=model_r):
            if lam <= 0:
                return 0.0
            return max(0.0, min(1.0, 1.0 - sum(nb_pmf(i, lam, r) for i in range(int(k)))))

        def pois_ge(k, lam):
            if k <= 0:
                return 1.0
            cum = sum(_m.exp(-lam) * lam ** i / _m.factorial(i) for i in range(int(k)))
            return max(0.0, min(1.0, 1.0 - cum))

        rows = []
        for e in entries:
            for c in claims_for(e, nb_ge, pois_ge):
                hit = grade_claim(c, actuals[e["fixture_id"]])
                if hit is not None:
                    rows.append({**c, "hit": hit})
        return summarise(rows)

    def test_a_model_matching_reality_comes_out_calibrated(self):
        import numpy as np
        out = self._run(*self._season(np.random.default_rng(7), dispersion=11.0))
        readable = [b for b in out["bands"] if not b["thin"] and b["claims"]]
        assert readable, "the simulated season should fill several bands"
        for b in readable:
            assert abs(b["residual"]) < 6.0, f"{b['band']} drifted: {b['residual']}"

    def test_real_corners_streakier_than_the_model_shows_up_as_overconfidence(self):
        # THE COMMENT'S POINT 2, as a test. The mean is right by construction; only the
        # spread is wrong. A table that could not see this would be useless.
        import numpy as np
        out = self._run(*self._season(np.random.default_rng(7), dispersion=1.5, n=600))
        high = [b for b in out["bands"]
                if not b["thin"] and b["claims"] and b["promised"]
                and b["promised"] >= 65.0]
        assert high, "need a populated high band to read"
        assert all(b["residual"] < 0 for b in high), \
            f"overdispersion should read as overconfidence, got {[b['residual'] for b in high]}"

    def test_overdispersion_reads_as_a_TILT_not_as_a_widening_with_the_line(self):
        """The received wisdom here is backwards, and this is the test that says so.

        measure_calibration.py's docstring says a gap that WIDENS with the line means the
        tail is wrong. It does not: too little assumed spread makes the model overstate
        the LIKELY claims and understate the unlikely ones, so by line the gap shrinks and
        flips sign as the line rises, and by probability band it tilts. Asserting the
        received version first is how this was found.
        """
        import numpy as np
        out = self._run(*self._season(np.random.default_rng(11), dispersion=1.5, n=600))
        per_line = {r["line"]: r for r in out["team_lines"] if r["claims"] > 50}
        assert 3 in per_line and 7 in per_line
        # The LOW line is the badly-missed one, not the high one.
        assert per_line[3]["residual"] < per_line[7]["residual"]
        assert per_line[3]["residual"] < -10.0

    def test_the_shape_is_named_as_overdispersion(self):
        import numpy as np
        out = self._run(*self._season(np.random.default_rng(11), dispersion=1.5, n=600))
        assert out["shape"] == "overdispersion"
        assert "streakier" in (out["shape_note"] or "")

    def test_a_calibrated_season_is_given_no_shape_at_all(self):
        # None is a real answer, and naming a cause off noise is the failure mode.
        import numpy as np
        out = self._run(*self._season(np.random.default_rng(7), dispersion=11.0))
        assert out["shape"] is None


class TestTheShapeDiscriminator:
    """A tilt and a level error need different work, so confusing them is expensive."""

    @staticmethod
    def _bands(pairs):
        # pairs: (promised, actual) per band, 200 claims each so none is thin.
        rows = []
        for i, (promised, actual) in enumerate(pairs):
            hits = round(200 * actual / 100)
            rows += [claim(promised, 1, fixture=f"f{i}-{j}") for j in range(hits)]
            rows += [claim(promised, 0, fixture=f"f{i}-{j}")
                     for j in range(hits, 200)]
        return summarise(rows)

    def test_a_flat_miss_at_every_band_is_a_level_error(self):
        out = self._bands([(20.0, 12.0), (30.0, 22.0), (50.0, 42.0),
                           (62.0, 54.0), (72.0, 64.0), (85.0, 77.0)])
        assert out["shape"] == "level"
        assert "same direction" in out["shape_note"]

    def test_a_tilt_is_overdispersion_even_though_the_average_miss_is_zero(self):
        # THE CASE A SINGLE POOLED RESIDUAL CANNOT SEE. Averaged over every band this
        # model looks perfect; it is wrong at both ends in opposite directions.
        out = self._bands([(20.0, 32.0), (30.0, 38.0), (50.0, 50.0),
                           (62.0, 56.0), (72.0, 60.0), (85.0, 73.0)])
        assert abs(out["overall"]["residual"]) < 3.0
        assert out["shape"] == "overdispersion"

    def test_a_calibrated_table_is_given_no_shape(self):
        out = self._bands([(20.0, 20.0), (30.0, 30.0), (50.0, 50.0),
                           (62.0, 62.0), (72.0, 72.0), (85.0, 85.0)])
        assert out["shape"] is None
        assert out["shape_note"] is None

    def test_too_few_bands_to_see_a_shape_is_no_shape(self):
        out = self._bands([(62.0, 50.0), (72.0, 60.0)])
        assert out["shape"] is None
