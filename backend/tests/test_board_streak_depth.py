"""How strong a streak is, and how much season it sits inside, now reach the board.

THREE THINGS WERE INVISIBLE AND EACH FAILED QUIETLY.

The window. Every streak chip came from one scan — five of five — so a side that had
cleared its line in nine of its last ten arrived looking exactly like a side that had
cleared it in five straight, and the stronger claim could not be told from the weaker one.

The denominator. `hits` rode on the row and the fraction it belonged to did not, so the
board could say "4" and nothing about whether that was four of five or four of twelve.

The history. A run inside a side's only five games on file is its whole record pointed at
itself. It was scored and coloured identically to form inside a full season.

None of these raise. They produce a board that looks right and is quietly telling you less
than it appears to.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def streak(hits=5, of=5, run=4, games=20, kind="over_team", line=5):
    return {"kind": kind, "team": "Cercle Brugge", "line": line, "hits": hits,
            "settled": of, "window": of, "voids": 0, "streak_len": run, "games": games}


def fixture(edge=1.2, strong=0, angles=0, date="2026-09-19T14:00:00Z"):
    return {"fixture_id": f"fx{edge}{strong}{angles}", "date": date,
            "corner_edge": edge, "strong_angles": strong, "angle_count": angles}


class TestTheBoardScansMoreThanOneWindow:
    def test_a_long_window_is_scanned_at_all(self):
        # Nine of ten is the claim the old board could not express: it ran one grid, at
        # five of five, so this row simply never existed.
        assert any(w == 10 for *_rest, w, _h in server.STREAK_GRIDS), \
            "no ten-game grid — a 9/10 run cannot reach the board"

    def test_the_short_window_tolerates_one_miss(self):
        # 5 of 5 refused to show a run that survived a blip, which is still a run.
        short = [(d, s, w, h) for d, s, _l, w, h in server.STREAK_GRIDS if w == 5]
        assert short and all(h == 4 for *_x, h in short), \
            "the five-game grids should accept four hits, not demand five"

    def test_the_long_window_is_only_run_on_the_grids_anyone_bets(self):
        # Each grid is a full pass over every team. The long window earns its cost on a
        # team's own corners; two more scans for the rarest chips on the board does not.
        long_subjects = {s for _d, s, _l, w, _h in server.STREAK_GRIDS if w == 10}
        assert long_subjects == {"team"}

    def test_both_windows_cover_over_and_under(self):
        long_dirs = {d for d, _s, _l, w, _h in server.STREAK_GRIDS if w == 10}
        assert long_dirs == {"over", "under"}

    def test_the_board_reads_the_table_rather_than_a_literal(self):
        # A window hardcoded in the loop is a window nothing can test.
        import inspect
        src = inspect.getsource(server._fixture_board)
        assert "STREAK_GRIDS" in src
        assert "window=window" in src and "min_hits=min_hits" in src

    def test_one_team_appearing_in_both_windows_is_not_two_chips(self):
        # dedupe_angles keeps the best angle per team per quantity, so a side qualifying on
        # both scans shows the better claim rather than arguing with itself.
        five = streak(hits=5, of=5, run=5)
        ten = streak(hits=9, of=10, run=9)
        kept = server.dedupe_angles([five, ten])
        assert len(kept) == 1
        assert kept[0]["settled"] == 10, "the longer, stronger run should survive"


class TestTheChipCarriesItsDenominator:
    def test_the_window_and_the_settled_count_ride_on_the_angle(self):
        import inspect
        src = inspect.getsource(server._fixture_board)
        for field in ('"window":', '"settled":', '"games":'):
            assert field in src, f"{field} never reaches the row, so the chip cannot show it"

    def test_the_detail_still_spells_the_fraction_out(self):
        import inspect
        src = inspect.getsource(server._fixture_board)
        assert "{s['hits']}/{settled}" in src


class TestARunNeedsASeasonToSitInside:
    def test_five_of_five_from_a_five_game_side_is_not_strong(self):
        # It is not a run within a season, it IS the season — and the board was colouring
        # the two identically.
        assert server.angle_is_strong(streak(games=5)) is False

    def test_the_same_run_inside_a_full_season_is(self):
        assert server.angle_is_strong(streak(games=20)) is True

    def test_the_bar_is_the_one_the_rest_of_the_board_uses(self):
        # One number meaning one thing: the fixture's own context hurdle, the mismatch
        # bar, and this are the same, so they cannot drift into separate opinions.
        assert server.BOARD_MIN_STREAK_GAMES == server.BOARD_MIN_MISMATCH_GAMES
        assert server.angle_is_strong(streak(games=server.BOARD_MIN_STREAK_GAMES)) is True
        assert server.angle_is_strong(streak(games=server.BOARD_MIN_STREAK_GAMES - 1)) is False

    def test_a_short_run_is_still_not_strong_however_long_the_season(self):
        # The sample bar is an ADDITIONAL hurdle, not a replacement for the run.
        assert server.angle_is_strong(streak(run=1, games=40)) is False

    def test_an_angle_with_no_recorded_history_is_not_retroactively_demoted(self):
        # `games` did not exist before this. Treating its absence as zero would mark every
        # cached row weak until the next rebuild, which reads as the board breaking.
        a = streak()
        a.pop("games")
        assert server.angle_is_strong(a) is True

    def test_a_mismatch_is_judged_on_its_own_bar_not_this_one(self):
        # A mismatch has no run at all — see BOARD_MIN_MISMATCH_GAMES.
        mm = {"kind": "mismatch", "real_samples": 12, "streak_len": 0}
        assert server.angle_is_strong(mm) is True


class TestSeveralAnglesMakeAGameWorthOpening:
    def test_more_strong_angles_outranks_a_bigger_projection(self):
        # The old order was (corner_edge, angle_count), so two sides both carrying live
        # runs lost to a fixture projecting 0.01 higher and holding one.
        busy = fixture(edge=1.10, strong=3, angles=4)
        quiet = fixture(edge=1.40, strong=1, angles=1)
        assert server.fixture_rank(busy) > server.fixture_rank(quiet)

    def test_the_projection_still_orders_within_a_tier(self):
        big = fixture(edge=1.40, strong=2)
        small = fixture(edge=1.05, strong=2)
        assert server.fixture_rank(big) > server.fixture_rank(small)

    def test_weak_angles_do_not_buy_a_higher_place(self):
        # Counting every angle would reward a fixture for accumulating chips that each
        # failed the evidence bar, which is the opposite of the point.
        padded = fixture(edge=1.2, strong=1, angles=6)
        lean = fixture(edge=1.2, strong=1, angles=1)
        assert server.fixture_rank(padded) > server.fixture_rank(lean)
        proven = fixture(edge=1.2, strong=2, angles=2)
        assert server.fixture_rank(proven) > server.fixture_rank(padded)

    def test_a_missing_count_does_not_raise(self):
        assert server.fixture_rank({}) == (0, 0, 0)

    def test_the_day_grouping_uses_the_stated_rank(self):
        rows = [fixture(edge=1.5, strong=1, angles=1), fixture(edge=1.1, strong=3, angles=3)]
        day = server.board_days(rows, per_day=1)[0]
        assert day["fixtures"][0]["strong_angles"] == 3

    def test_the_cap_still_bites_before_the_kickoff_reorder(self):
        # Each day is read back in kickoff order, so the rank has to be applied first or
        # the cap drops whichever game happens to kick off last.
        rows = [fixture(edge=1.1, strong=1, date="2026-09-19T12:00:00Z"),
                fixture(edge=1.1, strong=5, date="2026-09-19T20:00:00Z")]
        day = server.board_days(rows, per_day=1)[0]
        assert day["fixtures"][0]["strong_angles"] == 5
        assert day["considered"] == 2

    def test_the_ordering_is_documented_as_stated_rather_than_measured(self):
        """Four candidate rankings on the chase board were replayed walk-forward and every
        one came out flat. Nobody should read this one as a finding."""
        import inspect
        doc = inspect.getdoc(server.fixture_rank)
        assert "STATED rule" in doc
        assert "NOT A CLAIM" in doc and "has not been measured" in doc


def test_the_thin_history_bar_agrees_across_the_stack():
    """The backend refuses to call such an angle strong; the frontend flags it.

    If they disagree, the board shows a chip marked thin that it scored as solid, or a
    solid-looking chip it quietly refused to count — and either way the colour and the
    caveat are describing different rules.
    """
    import re
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    js = open(os.path.join(repo, "frontend/src/lib/angleTone.js")).read()
    m = re.search(r"THIN_HISTORY\s*=\s*(\d+)", js)
    assert m, "angleTone.js no longer declares THIN_HISTORY"
    assert int(m.group(1)) == server.BOARD_MIN_STREAK_GAMES, (
        f"angleTone.js says {m.group(1)}, server says {server.BOARD_MIN_STREAK_GAMES} — "
        "the chip would flag a different set of angles than the board demotes")
