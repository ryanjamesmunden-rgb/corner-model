"""The form table and the fixture ladder an EV sheet is built from.

WHAT THESE GUARD. The endpoint itself needs a database, so what is pinned here is the
arithmetic underneath it — and that is where a wrong number would survive. A form table
is read by sorting it, so a reader never checks an individual cell: an average taken over
the wrong games, or a run counted from the wrong end, reads exactly like the right answer
and gets staked.

THREE THINGS IN PARTICULAR:

  - a slice must come off the END of the record, in DATE order. The stored order is not
    guaranteed, so "last five" over the stored list is not the last five.
  - REAL matches only. sync_real pads a thin team with gaussian noise around its average,
    so `matches` holds games nobody played; a padded game in a form table is a figure
    that cannot be checked against a scoreline.
  - a HIT COUNT and a RUN are different claims. 9 of the last 10 tolerates a miss; 9 in a
    row does not, and a side can be 9/10 with a run of two.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from server import (SHEET_LINES, _form_block, _hits_and_run,  # noqa: E402
                    api_router, fair_odds, nb_ge)


def team(pairs, home_flags=None, start_day=1, synthetic=0):
    """pairs = [(corners_for, corners_against), ...] oldest first."""
    rms = []
    for i, (cf, ca) in enumerate(pairs):
        rms.append({"date": f"2026-09-{start_day + i:02d}", "corners_for": cf,
                    "corners_against": ca,
                    "home": (home_flags[i] if home_flags else i % 2 == 0)})
    out = {"name": "T", "team_id": "x-1", "league_id": "eng-l1", "real_matches": rms}
    if synthetic:
        # `matches` carries padded games. Nothing here may read it.
        out["matches"] = rms + [{"date": "2026-12-01", "corners_for": 99,
                                 "corners_against": 0, "home": True}] * synthetic
    return out


class TestTheFormSliceComesOffTheEndInDateOrder:
    def test_the_last_five_are_the_five_most_recent(self):
        t = team([(1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7)])
        f = _form_block(t, None, 5)
        assert f["values"] == [7, 6, 5, 4, 3]      # newest first, how a form string reads
        assert f["avg"] == 5.0

    def test_the_stored_order_does_not_decide_the_window(self):
        # The first stored row carries the latest date. A slice off the stored list would
        # miss it and report an average over the wrong five games.
        t = team([(1, 1)] * 6)
        t["real_matches"][0]["date"] = "2026-09-30"
        t["real_matches"][0]["corners_for"] = 20
        f = _form_block(t, None, 5)
        assert 20 in f["values"]

    def test_a_short_record_is_reported_at_its_real_length(self):
        # n is what the average was taken over; games is the whole record. A three-game
        # average labelled as five is the flattering kind of wrong.
        f = _form_block(team([(6, 2), (7, 3), (8, 4)]), None, 5)
        assert f["n"] == 3 and f["games"] == 3 and f["avg"] == 7.0

    def test_padded_games_are_never_read(self):
        t = team([(5, 5)] * 5, synthetic=3)
        f = _form_block(t, None, 5)
        assert f["high"] == 5, "a 99-corner synthetic game reached the form table"
        assert f["avg"] == 5.0

    def test_a_match_with_no_corner_count_is_dropped_not_zeroed(self):
        t = team([(6, 2), (7, 3)])
        t["real_matches"].append({"date": "2026-09-09", "corners_for": None,
                                  "corners_against": None, "home": True})
        f = _form_block(t, None, 5)
        assert f["n"] == 2 and f["avg"] == 6.5

    def test_an_empty_record_has_no_average_rather_than_zero(self):
        f = _form_block({"real_matches": []}, None, 5)
        assert f["avg"] is None and f["n"] == 0


class TestVenueFormIsTakenAtTheVenue:
    def test_home_and_away_are_separated(self):
        # home on the evens: 8, 8, 8 — away on the odds: 2, 2
        t = team([(8, 1), (2, 9), (8, 1), (2, 9), (8, 1)],
                 home_flags=[True, False, True, False, True])
        assert _form_block(t, "home", 5)["avg"] == 8.0
        assert _form_block(t, "away", 5)["avg"] == 2.0

    def test_a_side_with_no_games_at_that_venue_has_no_average(self):
        t = team([(8, 1), (8, 1)], home_flags=[True, True])
        assert _form_block(t, "away", 5)["avg"] is None


class TestAHitCountAndARunAreDifferentClaims:
    def ms(self, vals):
        return [{"corners_for": v} for v in vals]

    def test_nine_of_ten_with_a_short_run_reports_both(self):
        # The miss is the second-most-recent game: 9/10 on the rate, a run of 1.
        vals = [6] * 8 + [2, 6]
        hits, run = _hits_and_run(self.ms(vals), 5)
        assert hits == 9 and run == 1

    def test_a_perfect_window_is_both(self):
        hits, run = _hits_and_run(self.ms([6] * 10), 5)
        assert hits == 10 and run == 10

    def test_a_miss_in_the_last_game_ends_the_run_but_not_the_rate(self):
        hits, run = _hits_and_run(self.ms([9] * 9 + [1]), 5)
        assert hits == 9 and run == 0

    def test_the_line_is_inclusive(self):
        # "5+" means five or more. Exactly five is a hit, not a push.
        hits, run = _hits_and_run(self.ms([5, 5, 5]), 5)
        assert hits == 3 and run == 3

    def test_a_higher_line_is_never_easier(self):
        vals = [3, 9, 6, 7, 5, 8, 4, 6]
        counts = [_hits_and_run(self.ms(vals), L)[0] for L in SHEET_LINES]
        assert counts == sorted(counts, reverse=True)


class TestTheLadderMatchesTheModel:
    def test_the_lines_are_the_ones_asked_for(self):
        assert SHEET_LINES == (5, 6, 7, 8)

    def test_probability_falls_as_the_line_rises(self):
        ps = [nb_ge(L, 6.5) for L in SHEET_LINES]
        assert ps == sorted(ps, reverse=True)

    def test_fair_is_the_reciprocal_the_rest_of_the_site_uses(self):
        p = nb_ge(6, 7.0)
        assert fair_odds(p) == round(1.0 / p, 2)

    def test_a_dead_side_prices_at_nothing_rather_than_dividing_by_zero(self):
        assert nb_ge(5, 0) == 0.0
        assert fair_odds(0.0) is None


class TestTheRouteIsWiredToTheRightFunction:
    def test_the_sheet_path_resolves_to_the_sheet_endpoint(self):
        # The same guard as tests/test_snapshot_routes.py, for the same reason: a
        # decorator stranded on whatever is defined beneath it still registers a route.
        posts = {r.path: r for r in api_router.routes
                 if "GET" in (getattr(r, "methods", None) or set())}
        route = posts.get(api_router.prefix + "/tools/sheet.csv")
        assert route is not None, "the sheet export is not registered"
        assert route.endpoint.__name__ == "tools_sheet_csv"

    @pytest.mark.parametrize("name", ["kind", "days", "window", "min_games", "token"])
    def test_it_takes_the_parameters_the_workflow_sends(self, name):
        route = next(r for r in api_router.routes
                     if getattr(r, "path", "") == api_router.prefix + "/tools/sheet.csv")
        assert name in {p.name for p in route.dependant.query_params}
