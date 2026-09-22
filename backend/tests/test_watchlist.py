"""The watchlist for when football comes back.

WHAT THESE GUARD. This list is read three weeks before anything on it kicks off, with no
prices anywhere near it, which makes its failure modes quieter than a card's:

  - Ranking by streak. A run is one result from ending, and more rounds get played before
    the restart — planning a three-week watchlist around current runs is planning around
    the most perishable number on the board. The order has to come from the mismatch.
  - A window that silently misses the restart and reports "nothing" rather than "look
    again". An empty answer and a wrong window are indistinguishable without the histogram.
  - A fixture with eight games behind it presented like one with sixty. At this range the
    newly promoted side is exactly the row that looks most exciting.
  - Anything that reads as a set of selections. Nothing here is priced; that is the premise.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watchlist import (  # noqa: E402
    THIN_GAMES, best_angle, day_of, histogram, in_window, rank, split_by_sample, thin,
)


def angle(team, prob=70.0, line=5, team_for=7.2, opp_conceded=6.4):
    return {"kind": "mismatch", "team": team, "label": f"{line}+ corners", "line": line,
            "prob": prob, "fair_odds": round(100 / prob, 2),
            "team_for": team_for, "opp_conceded": opp_conceded}


def fixture(fid, date, home="Arsenal", away="Chelsea", edge=1.3, angles=None,
            home_games=20, away_games=20):
    return {"fixture_id": fid, "date": date, "home": home, "away": away,
            "league_id": "eng-pl", "league_name": "Premier League",
            "lambda_total": 11.4, "league_avg_total": 10.0, "corner_edge": edge,
            "home_games": home_games, "away_games": away_games,
            "angles": angles if angles is not None else [angle(home)]}


def rows(*fx):
    return {f["fixture_id"]: f for f in fx}


class TestTheWindow:
    def test_only_fixtures_inside_it(self):
        r = rows(fixture(1, "2026-10-17T14:00:00Z"),
                 fixture(2, "2026-09-26T14:00:00Z"),
                 fixture(3, "2026-11-20T14:00:00Z"))
        got = [f["fixture_id"] for f in in_window(r, "2026-10-12", "2026-10-26")]
        assert got == [1]

    def test_the_window_is_inclusive_at_both_ends(self):
        r = rows(fixture(1, "2026-10-12T14:00:00Z"), fixture(2, "2026-10-26T22:30:00Z"))
        assert len(in_window(r, "2026-10-12", "2026-10-26")) == 2

    def test_a_kickoff_is_placed_by_its_date_not_its_time(self):
        assert day_of("2026-10-17T23:30:00Z") == "2026-10-17"
        assert day_of(None) == ""

    def test_the_histogram_shows_the_gap(self):
        # An empty answer and a wrong window look identical without this — it is what
        # makes a mis-set window correctable in one re-run rather than guessed at twice.
        h = histogram(rows(fixture(1, "2026-10-03T14:00:00Z"),
                           fixture(2, "2026-10-03T16:00:00Z"),
                           fixture(3, "2026-10-17T14:00:00Z")))
        assert h["2026-10-03"] == 2
        assert h["2026-10-17"] == 1
        assert "2026-10-10" not in h          # the break


class TestTheOrder:
    def test_strongest_projection_first(self):
        r = [fixture(1, "2026-10-17T14:00:00Z", edge=1.1),
             fixture(2, "2026-10-17T14:00:00Z", edge=1.6),
             fixture(3, "2026-10-17T14:00:00Z", edge=1.3)]
        assert [f["fixture_id"] for f in rank(r)] == [2, 3, 1]

    def test_a_fixture_with_no_mismatch_is_left_off(self):
        # The list exists to name mismatches. A high total with no side projecting
        # unusually is a game, not a watch.
        r = [fixture(1, "2026-10-17T14:00:00Z", edge=2.0, angles=[]),
             fixture(2, "2026-10-17T14:00:00Z", edge=1.1)]
        assert [f["fixture_id"] for f in rank(r)] == [2]

    def test_a_streak_cannot_reorder_the_list(self):
        # The whole design decision, pinned. A run is one result from ending and more
        # rounds get played before the restart; ranking on it plans around the most
        # perishable number on the board.
        weak = fixture(1, "2026-10-17T14:00:00Z", edge=1.1,
                       angles=[{**angle("Arsenal"), "kind": "streak", "streak_len": 12}])
        strong = fixture(2, "2026-10-17T14:00:00Z", edge=1.6)
        assert [f["fixture_id"] for f in rank([weak, strong])] == [2]

    def test_the_strongest_side_of_a_fixture_is_the_one_named(self):
        f = fixture(1, "2026-10-17T14:00:00Z",
                    angles=[angle("Arsenal", prob=61.0), angle("Chelsea", prob=74.0)])
        assert best_angle(f)["team"] == "Chelsea"

    def test_a_fixture_with_no_angles_has_no_best(self):
        assert best_angle(fixture(1, "2026-10-17T14:00:00Z", angles=[])) is None

    def test_a_streak_angle_is_not_mistaken_for_a_mismatch(self):
        f = fixture(1, "2026-10-17T14:00:00Z",
                    angles=[{**angle("Arsenal"), "kind": "streak"}])
        assert best_angle(f) is None


class TestThinRows:
    def test_a_side_with_few_games_is_marked(self):
        # It projects as confidently as any other row and means considerably less.
        assert thin(fixture(1, "2026-10-17T14:00:00Z", home_games=THIN_GAMES - 1)) is True
        assert thin(fixture(1, "2026-10-17T14:00:00Z", away_games=THIN_GAMES - 1)) is True

    def test_a_well_sampled_fixture_is_not(self):
        assert thin(fixture(1, "2026-10-17T14:00:00Z")) is False

    def test_a_thin_row_is_kept_rather_than_dropped(self):
        # At this range the newly promoted side is often the eye-catching row, and
        # hiding it would leave the reader wondering why a game they expected is absent.
        r = [fixture(1, "2026-10-17T14:00:00Z", edge=1.9, home_games=3)]
        assert len(rank(r)) == 1

    def test_a_thin_row_cannot_outrank_a_well_sampled_one(self):
        # THE REASON THIS SECTION EXISTS. A five-game average is extreme by construction,
        # so thin rows do not merely appear in the ranking — they lead it. The first real
        # run put four in the top ten and pushed the usable fixtures off the end.
        rows = [fixture(1, "2026-10-17T14:00:00Z", edge=1.9, home_games=3),
                fixture(2, "2026-10-17T14:00:00Z", edge=1.2)]
        solid, thin_rows = split_by_sample(rows)
        assert [f["fixture_id"] for f in solid] == [2]
        assert [f["fixture_id"] for f in thin_rows] == [1]

    def test_both_sections_stay_ranked_within_themselves(self):
        rows = [fixture(1, "2026-10-17T14:00:00Z", edge=1.1),
                fixture(2, "2026-10-17T14:00:00Z", edge=1.6),
                fixture(3, "2026-10-17T14:00:00Z", edge=1.9, home_games=3),
                fixture(4, "2026-10-17T14:00:00Z", edge=1.4, home_games=2)]
        solid, thin_rows = split_by_sample(rows)
        assert [f["fixture_id"] for f in solid] == [2, 1]
        assert [f["fixture_id"] for f in thin_rows] == [3, 4]

    def test_a_fixture_with_no_mismatch_is_in_neither_section(self):
        solid, thin_rows = split_by_sample(
            [fixture(1, "2026-10-17T14:00:00Z", edge=2.0, angles=[])])
        assert solid == [] and thin_rows == []

    def test_the_bar_is_ten_games(self):
        # Eight let through a side claiming 12.0 conceded per away game. Stated here so a
        # later change to the constant has to come past this test and its reason.
        assert THIN_GAMES == 10
