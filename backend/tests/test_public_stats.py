"""The stats are public. The model's opinion is not.

WHAT CHANGED AND WHY IT NEEDS GUARDING. The split used to be how many ROWS a reader got:
three signed out, six signed in, the rest with the numbers stripped. It is now which
COLUMNS: everybody sees every row, and only a member sees the probability, the fair price,
the edge and the tier.

The old shape gave away the wrong half. Three fully readable rows are the three best spots
on the board — priced, with an edge attached — going out free every day, while the other
forty teams' RECORDS, which cost nothing to show, were the part held back.

AND THE FIXTURE PAGE WAS WORSE THAN THE BOARDS. `fixture_detail` took `user` as a dependency
and never read it, so a signed-out visitor got the complete model for any fixture: every
market's probability, fair odds, EV and tier. The boards were being trimmed to three rows
while a URL one click away handed over the priced angle on the same games.

WHAT THESE GUARD:

  - Every row reaches a signed-out reader. A regression to a row cap is a silent loss of
    the thing that does the selling.
  - No model number reaches a non-member, on a board row OR a fixture. One field slipping
    back into a payload is invisible from the UI and is the whole product.
  - The curve goes with the numbers. A probability mass function is the percentages drawn,
    so leaving it would be a lock with the key beside it.
  - A member still gets everything. A gate that also blocks the paying reader is worse than
    no gate.
  - What describes WHAT HAPPENED stays public — the streaks, the records, the form.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_corner_model")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

SIGNED_OUT = {"user_id": server.PUBLIC_USER_ID}
SIGNED_IN = {"user_id": "u1"}
MEMBER = {"user_id": "u2", "member": True}


class Res:
    """Just enough of a Response to collect the headers _preview writes."""

    def __init__(self):
        self.headers = {}


def rows(n):
    return [{"name": f"T{i}", "line": 4, "prob": 70.0 + i, "fair_odds": 1.4,
             "ev": 3.2, "tier": "strong", "streak": {"length": 9},
             "projection": {"prob": 70.0, "fair_odds": 1.4, "games": 20},
             "angles": [{"kind": "mismatch", "prob": 66.0, "label": "5+ corners"}]}
            for i in range(n)]


class TestEveryRowIsPublic:
    def test_a_signed_out_reader_gets_the_whole_board(self):
        out = server._preview(rows(40), SIGNED_OUT, Res())
        assert len(out) == 40, "the board was trimmed — the rows are what does the selling"

    def test_and_so_does_a_signed_in_one(self):
        # There is nothing left for an account alone to unlock on a board, so the two are
        # deliberately the same. An account still buys saved fixtures, slips and the group.
        assert len(server._preview(rows(40), SIGNED_IN, Res())) == 40

    def test_the_readable_count_is_reported_as_zero_rather_than_omitted(self):
        # The strip under the board reads these. A missing header makes it invent copy.
        res = Res()
        server._preview(rows(40), SIGNED_OUT, res)
        assert res.headers["X-Total-Rows"] == "40"
        assert res.headers["X-Readable-Rows"] == "0"
        assert res.headers["X-Preview"] == "true"

    def test_a_member_is_not_previewed_at_all(self):
        res = Res()
        out = server._preview(rows(40), MEMBER, res)
        assert res.headers["X-Preview"] == "false"
        assert all("blurred" not in r for r in out)


class TestNoModelNumberReachesANonMember:
    def test_every_blurred_field_is_gone_from_a_row(self):
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            for field in server.BLURRED_FIELDS:
                assert field not in r, f"{field} survived the blur"
            assert r["blurred"] is True

    def test_it_reaches_into_the_nested_places_too(self):
        # A probability hiding under `projection` is the same giveaway as one at the top.
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            assert "prob" not in r["projection"]
            assert "fair_odds" not in r["projection"]
            assert all("prob" not in a for a in r["angles"])

    def test_what_happened_is_left_alone(self):
        # The point of the change: the record is public. If this starts failing, the board
        # has become a wall again by another route.
        out = server._preview(rows(3), SIGNED_OUT, Res())
        for r in out:
            assert r["name"]
            assert r["line"] == 4
            assert r["streak"]["length"] == 9
            assert r["projection"]["games"] == 20

    def test_a_member_keeps_every_number(self):
        out = server._preview(rows(3), MEMBER, Res())
        for r in out:
            assert r["prob"] is not None
            assert r["ev"] == 3.2
            assert r["tier"] == "strong"


def model():
    return {"markets": [{"key": "home_over_4.5", "label": "Over 4.5", "line": 4.5,
                         "group": "home", "prob": 71.5, "fair_odds": 1.4, "ev": 2.1,
                         "tier": "strong", "book_odds": 1.5}],
            "lambdas": {"home": 5.4, "away": 4.1, "total": 9.5},
            "distribution": {"total": [{"k": 9, "p": 0.1}]},
            "recent": [{"won": 6}]}


class TestTheFixturePageWithholdsTheSameThings:
    def test_no_market_number_survives(self):
        out = server._blur_model(model())
        m = out["markets"][0]
        for field in ("prob", "fair_odds", "ev", "tier", "book_odds"):
            assert field not in m, f"{field} survived on a market"

    def test_the_market_still_exists_and_is_labelled(self):
        # A shorter table would read as a thinner model rather than a withheld one, and the
        # reader would not know there was anything to buy.
        m = server._blur_model(model())["markets"][0]
        assert m["label"] == "Over 4.5"
        assert m["line"] == 4.5
        assert m["group"] == "home"

    def test_the_curve_goes_with_the_numbers(self):
        # A pmf is the percentages drawn. Leaving it while stripping the column would be a
        # lock with the key beside it.
        out = server._blur_model(model())
        assert "distribution" not in out
        assert "lambdas" not in out

    def test_it_says_it_is_blurred_so_the_page_can_draw_a_lock(self):
        # Without this the page cannot tell "withheld" from "no price typed yet", and a
        # locked board looks like an empty one.
        assert server._blur_model(model())["blurred"] is True

    def test_everything_describing_what_happened_stays(self):
        assert server._blur_model(model())["recent"] == [{"won": 6}]

    def test_junk_is_returned_unchanged_rather_than_crashing(self):
        assert server._blur_model(None) is None
        assert server._blur_model("nope") == "nope"


class TestTheGateIsOnTheServer:
    def test_the_fixture_endpoint_actually_reads_the_user(self):
        # THE REGRESSION GUARD. `user` was a declared dependency that nothing used, which is
        # exactly why the leak was invisible: the signature looked gated.
        import inspect
        src = inspect.getsource(server.fixture_detail)
        assert "_blur_model" in src, \
            "fixture_detail no longer withholds the model — every visitor gets the " \
            "priced angle on every fixture"
        assert 'user.get("member")' in src

    def test_the_value_board_stays_a_hard_wall(self):
        # It is not a board of records with numbers on top; it IS the numbers, ranked. A
        # blurred version of it would be an empty screen, so it stays require_member.
        import inspect
        src = inspect.getsource(server.value_board)
        assert "require_member" in inspect.signature(server.value_board).parameters \
            or "require_member" in src
